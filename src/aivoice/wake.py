"""Talk to a tool by its name: "Claude, run the tests", "Hey ChatGPT, ...". Speech that does not start with the name of the
tool you are sending to is not sent, so talking to someone in the room never ends up in your AI tool. After you use the
name you stay "awake" for a short while, so a follow-up sentence needs no name.

Voice controls ("stop", "read it all") and session commands ("Computer, ...") work without a tool's name."""
import re

# the name to say -> ways Whisper tends to write it
TOOLS = {
    "Claude": ("claude", "claud", "cloud", "clyde", "clod"),
    "Codex": ("codex", "codecs", "code x"),
    "ChatGPT": ("chatgpt", "chat gpt", "chat g p t", "chat gbt"),
    "Gemini": ("gemini",),
    "Copilot": ("copilot", "co-pilot", "co pilot"),
    "Cursor": ("cursor",),
}
_PREFIX = r"^\W*(?:(?:hey|hi|ok|okay|yo|so)\W+)?"


def _rx(aliases):
    return re.compile(_PREFIX + r"(?:" + "|".join(re.escape(a).replace(r"\ ", r"\W*") for a in aliases) + r")\b[\s,.!?:;-]*(.*)$", re.I | re.S)


_RX = {name: _rx(aliases) for name, aliases in TOOLS.items()}


def tool_for(session, front_app=""):
    """The tool a sentence would go to: from the session's agent, the command it runs, or the app in front. "" if unknown."""
    hints = []
    if session:
        hints += [session.get("agent") or "", session.get("app") or "", session.get("cmd") or "", session.get("name") or ""]
    hints.append(front_app or "")
    for h in hints:
        low = h.lower()
        for name, aliases in TOOLS.items():
            if any(re.search(r"\b" + re.escape(a) + r"\b", low) for a in aliases if " " not in a):
                return name
    return ""


def addressed_to(text):
    """-> (tool name, the rest of the sentence) when the sentence starts with a tool's name, else None."""
    for name, rx in _RX.items():
        m = rx.match(text.strip())
        if m:
            return name, m.group(1).strip()
    return None


class Gate:
    """Decides whether a sentence is sent to the tool. One per listener."""

    def __init__(self, window=30.0):
        self.window, self.awake = float(window), {}           # target key -> awake until

    def check(self, text, tool, key, now):
        """-> ("send", text) | ("other", tool name said) | ("ignore", "")."""
        hit = addressed_to(text)
        if hit and tool and hit[0] != tool:
            return "other", hit[0]
        if hit:
            self.awake = {key: now + self.window}
            return "send", hit[1]
        if self.awake.get(key, 0) > now:
            self.awake[key] = now + self.window
            return "send", text
        return "ignore", ""
