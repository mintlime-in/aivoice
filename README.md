# aivoice

**Hands-free voice for the AI tools you already use.** Talk to Claude Code, Codex, Cursor or any AI tool, and hear its replies.
Speech recognition ([Whisper](https://github.com/openai/whisper)) and the voice ([Kokoro](https://github.com/hexgrad/kokoro)) run on
your own machine: your audio never leaves it.

aivoice is not an assistant. It does not chat or answer on its own: what you say goes to your AI tool, and what the tool replies is
read back to you. The only things it handles itself are voice controls ("stop", "read it all") and moving between your sessions.

- **Talk to the tool by name.** *"Claude, run the tests"*, *"Hey ChatGPT, ..."*, *"Codex, ..."*. Only what starts with the name of
  the tool in front is typed into it, so talking to someone in the room never reaches your AI. For 30 seconds after, follow-ups need no
  name. "Stop", "read it all" and "Computer, ..." work without it. `wake = "off"` sends everything you say.
- **Hear the answer your way.** Brief by default. Say *"read it all"* for the whole reply, *"summarize that"* for a summary.
- **The tool says what to say.** `aivoice setup` offers to ask Claude Code (and Codex, Gemini CLI) to end each reply with a short
  line starting with 🔊, meant to be heard. aivoice reads that line: no summary step, no local model needed. Without it, short replies
  are read as they are and long ones are summarized here.
- **Several sessions.** Only the session in front speaks; the others say "<session> has finished." and keep their reply for later.
- **Move between sessions by voice.** *"Computer, what's open?"*, *"Computer, switch to the portal session"*.
- **Nothing is installed into your tools.** It finds Claude Code sessions by itself and reads their replies from Claude's own transcripts.
- **Nothing is typed behind your back.** Anything aivoice would type on its own, rather than your dictation, needs your click on an approval window.
- **Talk over it.** Start speaking and it stops and listens, also on speakers with the optional echo cancellation.

## Which tools work

| Tool | Your voice in | Replies read back | How |
|---|---|---|---|
| Claude Code (terminal) | yes | yes, automatically | found by itself; iTerm2 and tmux reach the exact tab, other terminals and editors work through their window |
| Any terminal AI tool (Codex CLI, Gemini CLI, aider, ollama ...) | yes | yes | start it as `aivoice run -- codex` |
| Anything that prints its answer | no | yes | `some-tool \| aivoice speak` |
| Desktop and browser apps (Claude desktop, ChatGPT, Cursor chat ...) | yes, typed into the window in front | only what you copy ("read the clipboard") | `keystroke` sink |

Automatic read-back for Codex, Cursor and the Claude desktop app is not built yet: see the [roadmap](ROADMAP.md).

> **Status: early, not released.** Developed and tested on macOS with Apple Silicon. Linux, Intel Macs and Windows are supported by
> design and the portable logic is unit-tested on all three in CI, but the audio path has not been exercised there yet.

## Install

**1. The engine.** Any machine with Python 3.10 to 3.13 (not 3.14 yet):

```bash
pipx install --python python3.12 aivoice      # brew install pipx   (or: pip install pipx)
aivoice setup                                 # one-time download: voice ~330 MB + Whisper model ~1.6 GB
aivoice doctor                                # checks microphone, speakers and models
```

No pipx? From a clone, `./install.sh` does the same with a private virtual environment:

```bash
git clone https://github.com/mintlime-in/aivoice && cd aivoice && ./install.sh
```

**2. Start it:** `aivoice on`. It finds running Claude Code sessions by itself, in any terminal or app. In iTerm2 and tmux it reaches the exact tab or pane; in any
other app on macOS (Terminal, VS Code, Warp, Ghostty ...) it works through that app's window; elsewhere it types into the window in front. `aivoice off` stops it.

**Start at login:** `aivoice login on`. It writes one per-user file (a LaunchAgent on macOS, an autostart entry
on Linux, a Startup script on Windows) and respects `aivoice off`. `aivoice login off` removes it. Written and tested as a file;
not yet verified across a real logout and login.

**Optional: echo cancellation**, so you can interrupt the voice when it plays through speakers (headphones do not need it):
`pipx inject aivoice aec-audio-processing` (or `pip install 'aivoice[aec]'`; Python 3.11+). It builds a small C++ library, so macOS needs the
Xcode Command Line Tools and Linux a compiler; Windows has a prebuilt wheel. Without it everything still works, with a weaker interruption check.

**Permissions (macOS):** allow the microphone for your terminal app the first time. Controlling iTerm2 or typing into other apps
asks for *Automation* / *Accessibility* access. **Linux:** `sudo apt install libportaudio2`. For the `keystroke` sink on Linux or
Windows also `pip install 'aivoice[keys]'`.

## Using it

Just talk. Say **"stop"** to silence the voice and **"interrupt"** to stop the AI's current turn.

| Say | Does (handled locally, never sent to the AI) |
|---|---|
| "read it all" / "read everything" | reads the whole last reply |
| "summarize that" / "give me the summary" | reads a short version (uses the local LLM if you have one) |
| "read everything from now on" / "summaries only from now on" | sets the default for every reply |
| "read the clipboard" / "summarize the clipboard" | reads what you copied (for apps aivoice cannot read) |
| "stop" | silences the voice |
| "interrupt" / "cancel that" | silences it and presses Escape in the AI |

You do not need the exact words: "read me the whole thing", "say it all", "give me the short version" also work, with no model.
With the optional local LLM, other short requests ("I'd like to hear everything it said") are understood too.
Anything that names something else, like "summarize the auth file", goes to the AI as normal.

```bash
aivoice off        # stop everything and keep it off
aivoice on         # turn it back on
aivoice status     # what is running, which sessions, which model
```
`AIVOICE_DISABLE=1` keeps voice off for a single session.

### Commands for sessions

Start a sentence with the name (`name` in the config, default "computer"):

| Say | Does |
|---|---|
| "Computer, what's open?" | lists your sessions and whether each is working or idle |
| "Computer, switch to the portal session" | brings that tab or pane to the front (iTerm2, tmux) |
| "Computer, is the portal session done?" | working or finished |
| "Computer, read the portal session's reply" | reads that session's last reply |
| "Computer, ask the portal session to run the tests" | shows an approval window with the exact text, then types it there |
| "Computer, open a session in the portal project" | finds the folder, shows an approval window with the command and path, then opens a new tab running your tool (`open_cmd`, default `claude`; "start a codex session in ..." picks another) |

With a local model, looser wording works too ("have the portal one rebuild the image"). The model only fills in a form; code checks that
the session is one you named and that the message is made of your own words.

Sessions are matched by project folder or session name. If two match equally, or none, aivoice says so and does nothing.
What you dictate to the session in front is typed as you said it. Everything else that would type somewhere needs your approval:
a window with **Approve** / **Cancel** (Cancel is the default, no answer means no). Every proposal and decision is written to
`~/.aivoice/audit.log`. `approval = "voice"` allows a spoken "yes" instead: weaker, because anyone who can be heard can say it.

### Several sessions

Your speech goes to **the session you are looking at** (the iTerm tab in front, or the desktop app in front), and only that session
reads its reply aloud. When a background session finishes, aivoice says only "<session> has finished." and saves the reply, so
"read it all" works once you switch to it. `announce = false` keeps it silent.

## Other tools in detail

| You want | Use |
|---|---|
| Read any command's output aloud | `some-agent ... \| aivoice speak` |
| Any interactive CLI | `aivoice run -- aider` (voice in and out; macOS, Linux, WSL) |
| A desktop or browser chat window | speech is typed into the focused window (`keystroke` sink); copy a reply and say "read the clipboard" |
| Talk to a local model directly | `aivoice on --sink llm` (needs the optional LLM) |

Where your speech goes is called a *sink*: `iterm`, `tmux`, `keystroke` (types into whatever has focus, so mind where the cursor is),
`pty`, `exec`, `llm`, `stdout`.

## Optional local LLM

Nothing needs it. It never answers you itself: it only understands loosely worded voice controls and writes summaries. When one is available, "summarize that" uses it instead of the rule-based summary.

- **Apple Silicon:** `pipx inject aivoice mlx-lm` (or `pip install 'aivoice[llm]'`), then `aivoice setup --llm`.
  Qwen3-4B, 2.3 GB, loaded on demand and unloaded after five idle minutes. `llm_model = "auto"` picks a size by memory
  (1.7B under 12 GB, 4B under 22 GB, 8B above); any MLX model name works.
- **Windows, Linux, Intel Macs:** `aivoice setup --llm`. It installs llama.cpp into aivoice itself (a prebuilt package, nothing to
  compile), fetches a Qwen3 model sized to your memory (1.7B, 4B or 8B) and checks that it answers. If that fails on your machine it
  falls back to [Ollama](https://ollama.com) and offers to install it with your system's installer; nothing is installed without a
  typed yes. Run on a Mac only so far; not yet verified on a real Windows or Linux machine.
- **Any other local server** that speaks the OpenAI chat API (llama.cpp, LM Studio, vLLM, Jan): set `llm_url`, e.g.
  `llm_url = "http://127.0.0.1:8080/v1"` (and `llm_api_model` if the server wants a model name). A key, if needed, is read from the
  `AIVOICE_LLM_KEY` environment variable. Keep the address on `127.0.0.1`: a server elsewhere receives what you say.

### The local model between you and the AI (`frontend`)

The local model can only pick from a fixed list of actions, and everything spoken back comes from fixed text, so it cannot make up an answer. If it is unsure, slow (`frontend_timeout`, 6 s), unavailable or answers in
a wrong format, your sentence goes to the AI exactly as you said it. At `assistant` level a cleaned-up sentence is used only if it stays
close to what you said, and the listener log shows `(cleaned up: ...)` or `(command: ...)` for every decision.
Each sentence waits for the model first (about a second on a 3 to 4B model), so `commands` limits this to short sentences.

## Configuration

`~/.aivoice/config.toml` (see the [example](https://github.com/mintlime-in/aivoice/blob/main/examples/config.toml)) and
`~/.aivoice/glossary.txt` (names Whisper should recognise: project names, libraries, people). Any key can be overridden with
`AIVOICE_<KEY>`.

| Key | Default | Use |
|---|---|---|
| `end_silence`, `end_silence_short` | 1.1, 0.6 | how long a pause ends a sentence (raise to 1.5 to 2 if you speak slowly or pause to think), and the shorter wait after a one-word command |
| `wake_word` | none | e.g. `"hey claude"`: ignore everything until you say it, then stay awake for `wake_window` seconds |
| `stt_model` | big (large-v3-turbo) | on a slow CPU set a smaller one such as `"small.en"` |
| `vad` | silero | `silero` (neural speech detector, recommended) or `volume` (plain loudness gate) |
| `echo_cancel`, `aec_delay_ms` | auto, 150 | echo cancellation when installed; the speaker-to-microphone delay of your machine (150 fits a MacBook Pro) |
| `barge_ratio` | 2.2 | only without echo cancellation: how much louder than the echo you must be to interrupt |
| `name` | computer | the word that addresses aivoice itself (session commands); `""` turns that off |
| `open_cmd`, `project_dirs` | claude, common folders | what "open a session" starts, and where your projects live |
| `discover` | true | find agent sessions and read their replies |
| `approval` | dialog | `dialog` (click to approve) or `voice` (say yes; weaker) |
| `frontend` | commands | `off`: exact phrases only. `commands`: loose wording, plus the local LLM for short unusual requests. `assistant`: the local LLM sees every sentence, of any length: it can run a command or forward your sentence lightly cleaned of dictation slips |
| `mode` | brief | `brief` or `full` |
| `voice`, `speed` | af_bella, 1.05 | Kokoro voice and speed |

## Privacy

The microphone feeds a local volume detector and a local Whisper model. The only network use is the one-time model download (GitHub
releases and Hugging Face). There is no telemetry. The microphone is open while it runs: `touch ~/.aivoice/.paused` pauses
it and `aivoice off` ends it. The voice daemon listens on `127.0.0.1` only and requires a secret token that changes on every start.

## Troubleshooting

| Symptom | Try |
|---|---|
| Nothing happens when I talk | `aivoice status`, then read `~/.aivoice/listener.log`. A line `(ignored, start with 'hey claude')` means a wake word is set. |
| No sound | check the system volume is not muted; `aivoice doctor` checks the speakers; log: `~/.aivoice/tts.log` |
| Typing by voice works but replies are silent | `aivoice status` should list the session; if it does not, aivoice has not found it (see Known limits). A session you are not looking at only announces that it finished. |
| The voice interrupts itself | install the echo cancellation extra, or raise `barge_ratio` (try 3), or use headphones |
| It does not notice me talking over it | install the echo cancellation extra (speakers feed the voice back into the mic), or use headphones; tune `aec_delay_ms` |
| It picks up other people talking nearby | set a `wake_word`. Fans, keyboards and music are already ignored by the speech detector. |
| `pipx` or install fails on Python 3.14 | pass `--python python3.12`; 3.14 is not supported yet |
| First start is slow | the Whisper model loads on every start (about ten seconds); it stays loaded while a session is open |

## Known limits

- Without the echo cancellation extra, interrupting on laptop speakers relies on a loudness heuristic that can miss you. Headphones are always reliable.
- With it, the first second or so of an interruption can be clipped, and `aec_delay_ms` is tuned on one MacBook Pro; other machines may need a different value.
- The speech detector separates speech from noise, not one speaker from another: use a `wake_word` if people talk near you.
- `aivoice run` needs a Unix pseudo-terminal (macOS, Linux, WSL). Full-screen terminal UIs redraw constantly, so its output is noisy to read aloud.
- Finding sessions reads Claude Code's own session list and transcripts. These are internal files and may change with a Claude Code update. Other agents use `run` or a pipe.
- Picking one tab among several needs iTerm2 or tmux. In other apps aivoice can bring the app to the front, and types into a session that is not in front only when it is the only session in that app.
- Reading replies aloud needs a transcript (Claude Code), a pipe, `run` or the clipboard. Chat apps in a window expose none, so there is no automatic
  read-back there yet.

## How it works

```
 mic -> Whisper (local) -> spoken command? -- yes --> handled here, the AI never sees it
                                  | no
                                  v
                   the session you are looking at -> your AI

 your AI's reply -> transcript / pipe / run / clipboard -> brief or full -> Kokoro voice (local) -> speakers
```

More in the [architecture notes](https://github.com/mintlime-in/aivoice/blob/main/docs/ARCHITECTURE.md) and the
[roadmap](https://github.com/mintlime-in/aivoice/blob/main/ROADMAP.md).

## Contributing

```bash
git clone https://github.com/mintlime-in/aivoice && cd aivoice
pip install -e '.[dev]' && pytest
```
Issues and pull requests are welcome, especially reports from Linux, Windows and Intel Macs.

## License

[MIT](https://github.com/mintlime-in/aivoice/blob/main/LICENSE)
