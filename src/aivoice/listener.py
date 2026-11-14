"""Hands-free, fully local voice input.

mic -> volume VAD -> local Whisper (mlx-whisper or faster-whisper) -> spoken commands handled here,
everything else sent to the session you are looking at. No audio and no text leaves the machine; the Whisper
model is downloaded once and then cached.
"""
import collections, os, queue, re, threading, time

import numpy as np
import sounddevice as sd

from . import aec, config, intent, commands, log, wake, llm, platform_, sessions, sinks, stt, textprep, tts_client, vad

SR = 16000
BLOCK = vad.BLOCK               # 512 samples = 32 ms (what Silero expects)
MIN_SPEECH = 0.4                 # s; shorter blips are ignored
MAX_UTT = 30.0                   # s
PRE_ROLL = 0.3                   # s kept before speech onset
TTS_TAIL = 0.6                   # s to stay deaf after the voice stops talking

CFG = {}


def tts_until():
    """Time at which the voice expects to be silent (written by the TTS daemon)."""
    try:
        return float(config.read_state("speaking_until", "0") or 0)
    except ValueError:
        return 0.0


def load_glossary():
    words = []
    try:
        with open(config.path("glossary.txt")) as fh:
            words = [w.strip() for w in fh if w.strip() and not w.startswith("#")]
    except OSError:
        pass
    for name in [(CFG.get("name") or "").strip().capitalize()] + (list(wake.TOOLS) if CFG.get("wake") == "tool" else []):
        if name and name.lower() not in [w.lower() for w in words]:
            words.insert(0, name)                        # so Whisper spells the names the way we match them
    return ("Terms that may come up: " + ", ".join(words) + ".")[:600] if words else None


# ---------- spoken commands (handled locally: the AI never sees them, zero tokens) ----------
def use_llm():
    s = CFG.get("summarizer", "auto")
    return s == "llm" or (s == "auto" and llm.usable(CFG))


def _llm_brief(raw):
    if not llm.loaded():
        tts_client.speak("One moment.")
    try:
        tts_client.speak(llm.summarize(raw, CFG))
    except Exception as e:
        log.line("PROBLEM", f"the local model could not summarize ({e}); reading the simple summary instead")
        tts_client.speak(textprep.speak_text(raw, "brief"))


def speak_raw(raw, kind):
    how, text = textprep.reading(raw, kind, use_llm())
    if how == "summarize":
        threading.Thread(target=_llm_brief, args=(text,), daemon=True).start()
    else:
        tts_client.speak(text)


def speak_last(kind, key, back=0):
    """Read the last reply (back=0) or an earlier one (back=1: the one before that)."""
    raw = ""
    s = sessions.get(key)
    if s and s.get("transcript"):
        from . import agents
        rs = agents.claude_replies(s["transcript"], back + 2)
        raw = rs[-1 - back] if len(rs) > back else ""
        if back and not raw:
            tts_client.speak("There is no earlier reply.")
            return
    raw = raw or textprep.load_last(key) or textprep.load_last(key.split(":")[-1])
    if raw:
        speak_raw(raw, kind)
    else:
        tts_client.speak("I have nothing to read yet.")


HELP_SPOKEN = ("I read your AI's replies aloud. Say stop to quiet me, interrupt to stop the AI, read it all for the whole reply, "
               "summarize that for a short one, or read everything from now on to change the default. Anything else goes to the AI.")


STATE = {}


COMMAND_WORDS = {"stop": "silence the voice", "interrupt": "silence the voice and press Escape in the AI",
                 "full": "read the whole last reply", "brief": "read a summary of the last reply",
                 "clip_full": "read the clipboard", "clip_brief": "summarize the clipboard", "help": "say what you can say",
                 "mode_full": "from now on read whole replies", "mode_brief": "from now on read summaries"}


def voice_command(text, sink, key):
    """Handle the sentence if it is for us. Returns the text to forward to the AI, or None when it was handled here."""
    kind, val = intent.interpret(text, CFG)
    if kind == "forward":
        if val != text:
            log.line("NOTE", f"tidied up to {log.q(val)}")
        return val
    c = val
    log.line("COMMAND", f"{log.q(text)} = {COMMAND_WORDS.get(c, c)}; not sent to the AI")
    if c == "stop":
        tts_client.stop()
    elif c == "interrupt":
        tts_client.stop()
        sink.interrupt()
    elif c in ("full", "brief"):
        speak_last(c, key, 1 if commands._PREV.search(text) else 0)
    elif c in ("clip_full", "clip_brief"):
        raw = platform_.clipboard()
        if raw.strip():
            textprep.save_last("clipboard", raw)
            speak_raw(raw, "full" if c == "clip_full" else "brief")
        else:
            tts_client.speak("The clipboard is empty.")
    elif c == "help":
        tts_client.speak(HELP_SPOKEN)
    elif c in ("mode_full", "mode_brief"):
        m = c.split("_")[1]
        textprep.set_mode(m)
        tts_client.speak("Okay, I'll read everything." if m == "full" else "Okay, summaries only.")
    return None


def route(cfg, default_sink):
    """Which session gets this sentence: the one you are looking at, else the default sink."""
    sess = sessions.current() if cfg.get("focus_follows", True) or len(sessions.all()) == 1 else None
    if sess and sess.get("sink") not in ("", "none", None):
        return sinks.for_session(cfg, sess), sess["id"], f"{sess.get('name') or sess['id'][:8]} via {sess['sink']}"
    if sess:                                               # known session in a terminal we cannot address: type into the front window
        return default_sink, sess["id"], f"{sess.get('name') or sess['id'][:8]} via default sink {cfg['sink']}"
    key = default_sink.target() or "default"
    return default_sink, key, f"default sink {cfg['sink']}"


def main():
    cfg = config.load()
    CFG.update(cfg)
    default_sink = sinks.get(cfg)
    glossary = load_glossary()
    end_silence, min_thr = float(cfg["end_silence"]), float(cfg["min_threshold"])

    log.line("START", f"loading speech to text ({stt.model_name(cfg)}, {stt.backend_name(cfg)}); the first start downloads it")
    tr = stt.Transcriber(cfg)
    tts_client.ensure_server()
    if cfg.get("discover", True):
        commands.Watcher(cfg, lambda raw: speak_raw(raw, textprep.get_mode()),
                       announce=lambda line: tts_client.speak(line)).start()
        log.line("START", "finding AI sessions by itself; their replies are read from their transcripts")

    q = queue.Queue()
    def on_audio(indata, frames, tinfo, status):
        # the wall-clock time this block was captured, from the audio device's own clock (not when we get round to it)
        q.put((indata[:, 0].copy(), time.time() - (tinfo.currentTime - tinfo.inputBufferAdcTime)))

    with sd.InputStream(samplerate=SR, channels=1, blocksize=BLOCK, dtype="float32", callback=on_audio):
        while time.time() < tts_until() + 0.5:           # never calibrate on our own voice
            time.sleep(0.2)
        while not q.empty():
            q.get()
        noise = [float(np.sqrt(np.mean(q.get()[0] ** 2))) for _ in range(66)]       # ~2 s
        floor = float(np.percentile(noise, 30))                     # ignore bursts (keys, a passing voice)
        thr = min(max(min_thr, floor * 5.0), float(cfg["max_threshold"]))
        how = (f"say {cfg['wake_word']!r} first" if cfg["wake_word"] else "start with the tool's name, e.g. \"Claude, ...\""
               if cfg.get("wake", "tool") == "tool" else "everything you say is sent")
        log.line("START", f"listening: {how}. Summaries: {'local model' if use_llm() else 'simple rules'}. Say \"stop\" to silence the voice")

        recent = collections.deque(maxlen=int(2.0 * SR / BLOCK))      # ~2 s of the latest audio
        seg = vad.Segmenter(start=float(cfg["vad_start"]), end=float(cfg["vad_end"]), end_silence=end_silence,
                            min_speech=MIN_SPEECH, pre_roll=PRE_ROLL, max_utt=MAX_UTT, end_silence_short=float(cfg.get("end_silence_short", end_silence)))
        detector = vad.make(cfg, thr)
        ec = aec.make(cfg)
        timeline = aec.RefTimeline() if ec else None
        log.line("START", f"voice detection: {detector.name}; echo cancellation: {'on' if ec else 'off (talking over the voice is less reliable)'}; "
                          f"background noise level {thr:.3f}")
        deaf_until = 0.0
        paused = config.path(".paused")
        barge_in, ratio = bool(cfg["barge_in"]), float(cfg["barge_ratio"])
        smooth, echo_win, hot = 0.0, collections.deque(), 0
        last_on, learn_until, was_on = 0.0, 0.0, False
        wake_words = (cfg.get("wake_word") or "").lower().split()
        wake_rx = re.compile(r"^[\W_]*" + r"[\W_]+".join(map(re.escape, wake_words)) + r"[\W_]*", re.I) if wake_words else None
        wake_window, awake_until = float(cfg["wake_window"]), 0.0
        tool_gate = wake.Gate(cfg["wake_window"]) if cfg.get("wake", "tool") == "tool" and not wake_rx else None

        while True:
            blk, t_cap = q.get()
            now = time.time()
            if ec:                                               # remove our own voice from what the mic heard
                timeline.poll()
                blk = ec.process(blk, timeline.block(t_cap, len(blk)))
            recent.append(blk)
            rms = float(np.sqrt(np.mean(blk ** 2)))
            p = detector.prob(blk)                               # speech probability of this block
            smooth = 0.7 * smooth + 0.3 * rms                    # ~90 ms level envelope
            on = now < tts_until() + 0.25                        # the voice is (about to be) talking

            if on:
                if now - last_on > 1.0:                          # a new spoken reply starts: relearn the echo
                    echo_win.clear(); hot = 0; learn_until = now + 0.4
                last_on = now
            elif was_on and not seg.active:
                deaf_until = now + TTS_TAIL                      # let the room tail die out
            was_on = on

            is_paused = os.path.exists(paused)
            if is_paused:
                deaf_until = now + TTS_TAIL

            if on and not seg.active:
                if not barge_in:
                    deaf_until = now + TTS_TAIL
                else:
                    if ec:                                       # echo is gone: speech-like sound left over is you
                        echo = 0.0
                        hot = hot + 1 if (p >= 0.6 and rms > 0.008) else 0
                    else:
                        while echo_win and now - echo_win[0][0] > 1.5:
                            echo_win.popleft()
                        echo = max((v for _, v in echo_win), default=0.0)
                        limit = max(thr, echo * ratio)
                        if now < learn_until:
                            echo_win.append((now, smooth)); hot = 0
                        else:
                            # clearly louder than the echo AND speech-like (a door slam or a key click is not you)
                            hot = hot + 1 if (smooth > limit and p >= 0.5) else 0
                            if smooth <= limit:
                                echo_win.append((now, smooth))
                    if hot >= 8:                                 # ~0.25 s: you are talking over the voice
                        tts_client.stop()
                        log.line("STOPPED", "you talked over the voice, so it stopped and is listening")
                        hot, deaf_until = 0, 0.0
                        seg.start_from(list(recent)[-45:])           # keep ~1.4 s from before we noticed: your first words
                    else:
                        continue

            if now < deaf_until:
                seg.reset(); detector.reset(); recent.clear()
                while q.qsize() > 50:
                    q.get()
                continue

            audio = seg.push(blk, p)
            late = None
            if audio is None:
                fr = STATE.get("fragment")
                if not fr or seg.active or time.time() - fr[1] < 3.5:
                    continue
                late, audio = STATE.pop("fragment")[0], []       # you never finished the sentence: take what you said

            t0 = time.time()
            if late is None:
                text, confident = tr.transcribe(audio, glossary)
                if not confident:
                    log.line("IGNORED", f"{log.q(text)} ({len(audio)/SR:.1f} s): probably noise, not speech")
                    continue                                     # likely a hallucination on noise
                if textprep.noise(text):
                    if text.strip():
                        log.line("IGNORED", f"{log.q(text)}: a filler or what speech to text writes on silence")
                    continue
                fr = STATE.pop("fragment", None)
                if fr and time.time() - fr[1] < 12:              # the rest of a sentence you paused in
                    text = fr[0] + " " + text
                if commands.dangling(text):
                    STATE["fragment"] = (re.sub(r"[.\u2026\s]+$", "", text), time.time())
                    log.line("HEARD", f"{log.q(text)}  (sounds unfinished; waiting for the rest)")
                    continue
            else:
                text = late
            log.line("HEARD", f"{log.q(text)}  ({len(audio)/SR:.1f} s of speech, text in {time.time()-t0:.1f} s)" if len(audio) else log.q(text))
            if wake_rx:
                m = wake_rx.match(text)
                if m:
                    text = text[m.end():].strip()
                    awake_until = time.time() + wake_window
                    if not text:
                        log.line("NOTE", "wake word heard; listening")
                        continue
                elif time.time() > awake_until:
                    log.line("NOT SENT", f"{log.q(text)}: start with {cfg['wake_word']!r} to send it")
                    continue                                     # not for me: ignore room chatter
                else:
                    awake_until = time.time() + wake_window

            rest = commands.addressed(text, cfg)
            if rest is not None:
                log.line("COMMAND", f"for aivoice itself: {log.q(rest)}")
                if not rest:
                    tts_client.speak("Yes?")
                    continue
                if commands.handle(rest, cfg, say_reply=lambda raw: speak_raw(raw, "brief")):
                    continue
                text = rest                                      # not one of the assistant's own commands: treat it like any sentence
            sink, key, where = route(cfg, default_sink)
            if tool_gate and not (textprep.classify(text) or intent.loose(text)):   # voice controls never need a name
                tool = wake.tool_for(sessions.get(key), platform_.front_app())
                if tool:
                    verdict, val = tool_gate.check(text, tool, key, time.time())
                    if verdict == "ignore":
                        log.line("NOT SENT", f"{log.q(text)}: start with \"{tool}, ...\" to send it to {where}")
                        continue
                    if verdict == "other":
                        log.line("NOT SENT", f"{log.q(text)}: you named {val}, but the session in front is {tool} ({where})")
                        tts_client.speak(f"That's {tool} in front, not {val}.")
                        continue
                    text = val
                    if not text:
                        log.line("NOTE", f"{tool} heard; say what to send")
                        continue
            fwd = voice_command(text, sink, key)
            if fwd is None:
                continue
            sink.send(fwd)
            log.line("SENT", f"to {where}: {log.q(fwd)}")
            if sessions.get(key):
                commands.spoke_to(key)                           # its answer is read even if you look away while it works
            while not q.empty():
                q.get()


def run():
    try:
        main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
