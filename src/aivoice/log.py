"""listener.log, written to be read by a person: one line per event, the time, a fixed-width label, then plain words.

    20:41:30  HEARD      "Claude, what's the time now?"  (1.6 s of speech, text in 0.6 s)
    20:41:30  SENT       to aivoice-5e (iTerm): "what's the time now?"
    20:41:40  REPLY      from aivoice-5e, 48 characters: reading it aloud
"""
import time

LABELS = ("START", "HEARD", "SENT", "NOT SENT", "COMMAND", "REPLY", "IGNORED", "STOPPED", "PROBLEM", "NOTE")
_W = max(map(len, LABELS)) + 1


def line(label, text):
    print(f"{time.strftime('%H:%M:%S')}  {label:<{_W}} {text}", flush=True)


def q(text):
    """Quote what was said, shortened for one line."""
    t = " ".join(str(text).split())
    return f'"{t[:157]}..."' if len(t) > 160 else f'"{t}"'
