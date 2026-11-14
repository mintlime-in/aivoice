"""One short instruction, added to an AI tool's own global instructions file, asking it to end every reply with a line
meant to be heard. aivoice reads that line instead of summarizing the reply itself: no local model, no delay, and the
tool knows best what mattered. The block is marked so it can be found and removed again; nothing else in the file changes."""
import os, re

START, END = "<!-- aivoice: spoken line -->", "<!-- /aivoice -->"
TEXT = """## Spoken line
The person may be listening to your replies instead of reading them. End every reply with one final line that starts with
🔊 followed by one or two short, plain sentences saying what matters: the outcome, or the question you need answered.
Write it to be heard: no markdown, code, file paths, URLs or lists. Leave it out only when the whole reply is one short sentence."""
BLOCK = f"{START}\n{TEXT}\n{END}\n"

# tool -> its global instructions file (only offered when the tool's folder exists on this machine)
TOOLS = {"Claude Code": "~/.claude/CLAUDE.md", "Codex": "~/.codex/AGENTS.md", "Gemini CLI": "~/.gemini/GEMINI.md"}


def installed_tools():
    return {name: os.path.expanduser(p) for name, p in TOOLS.items() if os.path.isdir(os.path.dirname(os.path.expanduser(p)))}


def present(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return START in fh.read()
    except OSError:
        return False


def add(path):
    """Append the block (once). Returns True if the file changed."""
    if present(path):
        return False
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(old + ("\n" if old and not old.endswith("\n") else "") + ("\n" if old.strip() else "") + BLOCK)
    return True


def remove(path):
    """Take the block out again, leaving the rest of the file as it was. Returns True if the file changed."""
    if not present(path):
        return False
    with open(path, encoding="utf-8") as fh:
        old = fh.read()
    new = re.sub(r"\n?\n?" + re.escape(START) + r".*?" + re.escape(END) + r"\n?", "\n", old, flags=re.S)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new.rstrip("\n") + "\n" if new.strip() else "")
    return True
