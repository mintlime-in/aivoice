import pytest
from aivoice import textprep as t


@pytest.mark.parametrize("phrase,kind", [
    ("Read it all.", "full"), ("read everything", "full"), ("Can you read it all out loud?", "full"),
    ("summarize that", "brief"), ("Give me the summary.", "brief"), ("TL;DR", "brief"),
    ("Stop.", "stop"), ("Interrupt", "interrupt"), ("cancel that", "interrupt"),
    ("read everything from now on", "mode_full"), ("Summaries only from now on", "mode_brief"),
    ("read the clipboard", "clip_full"), ("Summarize the clipboard.", "clip_brief"), ("summarize what I copied", "clip_brief"),
    ("summarize the auth file", None), ("read the file src/app.ts", None), ("fix the bug", None),
])
def test_classify(phrase, kind):
    assert t.classify(phrase) == kind


RAW = """## Result
I changed `speak_hook.sh` so it only speaks for sessions you enabled, and it keeps the full reply on disk so you can ask for it later.

- first detail about the filter
- second detail about the modes

```bash
ls -la
```

| a | b |
|---|---|

There is more I could do, such as a headphone mode. Want me to start with the glossary?"""


def test_full_skips_code_tables_and_reads_lists():
    full = t.full_text(t.blocks(RAW))
    assert "ls -la" not in full and "|" not in full and "```" not in full
    assert "first detail about the filter." in full
    assert "speak hook.sh" in full            # snake_case and inline code read as words


def test_brief_keeps_lead_and_question():
    brief = t.brief_text(t.blocks(RAW))
    assert brief.startswith("I changed")
    assert "Want me to start with the glossary?" in brief


def test_cue_when_much_is_left_out():
    raw = "Here is the plan. " + "\n".join(f"- step {i}: do the thing number {i} carefully" for i in range(15))
    assert t.brief_text(t.blocks(raw)).endswith("Details are on screen.")


def test_short_reply_is_read_whole():
    assert t.brief_text(t.blocks("Done. All set.")) == "Done. All set."


def test_links_and_urls():
    out = t.full_text(t.blocks("See [the docs](https://x.com/a) or https://y.com now."))
    assert out == "See the docs or now."


def test_how_a_reply_is_read():
    from aivoice import textprep
    short = "It's 7:45 PM IST on Saturday, November 14, 2026."
    assert textprep.reading(short, "brief", True) == ("say", short)                     # short: no summary step
    long = "A long reply. " * 60
    assert textprep.reading(long, "brief", True) == ("summarize", long)
    assert textprep.reading(long, "brief", False)[0] == "say"
    assert textprep.reading(long + "\n\n🔊 Done, nothing failed.", "brief", True) == ("say", "Done, nothing failed.")
    assert textprep.reading(long, "full", True)[0] == "say"

def test_the_first_piece_of_speech_is_short_so_the_voice_starts_sooner():
    from aivoice.textprep import chunks
    assert chunks("It's 7:45 PM IST on Saturday, November 14, 2026.") == ["It's 7:45 PM IST on Saturday,", "November 14, 2026."]
    assert chunks("Done. All 42 tests pass. The build is green.") == ["Done.", "All 42 tests pass. The build is green."]
    long = "First. " + "A sentence of medium length here. " * 12
    out = chunks(long)
    assert out[0] == "First." and all(len(c) <= 280 for c in out) and " ".join(out).split() == long.split()


def test_the_tools_own_spoken_line_is_read_and_kept_out_of_the_full_reading():
    from aivoice import textprep
    raw = "I changed `cli.py` and ran the tests.\n\n```bash\npytest -q\n```\n\n🔊 All tests pass, and the help text is shorter now."
    assert textprep.voice_line(raw)[0] == "All tests pass, and the help text is shorter now."
    assert textprep.speak_text(raw, "brief") == "All tests pass, and the help text is shorter now."
    full = textprep.speak_text(raw, "full")
    assert "cli" in full and "🔊" not in full and "All tests pass" not in full
    assert textprep.voice_line("**🔊 Done.**")[0] == "Done." and textprep.voice_line("> 🔊️: Ready for review.")[0] == "Ready for review."
    assert textprep.voice_line("No line here.") == ("", "No line here.")


def test_instruction_block_is_added_once_and_removed_cleanly(tmp_path):
    from aivoice import instructions
    f = tmp_path / "CLAUDE.md"
    f.write_text("# my rules\n- be brief\n")
    assert instructions.add(str(f)) and not instructions.add(str(f))
    assert f.read_text(encoding="utf-8").count(instructions.START) == 1 and "🔊" in f.read_text(encoding="utf-8") and f.read_text(encoding="utf-8").startswith("# my rules\n- be brief\n")
    assert instructions.remove(str(f)) and f.read_text(encoding="utf-8") == "# my rules\n- be brief\n" and not instructions.remove(str(f))
    g = tmp_path / "new" / "AGENTS.md"
    g.parent.mkdir()
    assert instructions.add(str(g)) and g.read_text(encoding="utf-8") == instructions.BLOCK


def test_setup_asks_before_touching_a_tools_instructions(tmp_path, monkeypatch):
    from aivoice import cli, instructions
    f = tmp_path / ".claude" / "CLAUDE.md"
    f.parent.mkdir()
    monkeypatch.setattr(instructions, "TOOLS", {"Claude Code": str(f)})
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    cli._setup_spoken_line(ask=lambda q: "n")
    assert not f.exists()
    cli._setup_spoken_line(ask=lambda q: "")
    assert instructions.present(str(f))
    cli._setup_spoken_line(ask=lambda q: "no")
    assert not instructions.present(str(f))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    cli._setup_spoken_line(ask=lambda q: "y")
    assert not instructions.present(str(f))


def test_setup_offers_the_aivoice_command_and_only_removes_its_own_file(tmp_path, monkeypatch):
    from aivoice import cli, instructions
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    cli._setup_command(ask=lambda q: "n")
    assert not instructions.has_skill()
    cli._setup_command(ask=lambda q: "")
    text = open(instructions.skill_file(), encoding="utf-8").read()
    assert "disable-model-invocation: true" in text and "$ARGUMENTS" in text and "aivoice off" in text
    cli._setup_command(ask=lambda q: "no")
    assert not (tmp_path / ".claude" / "skills" / "aivoice").exists()
    other = tmp_path / ".claude" / "skills" / "aivoice" / "SKILL.md"
    other.parent.mkdir(parents=True); other.write_text("---\nname: something-else\n---\nmine\n")
    instructions.remove_skill()
    assert other.exists()                                                              # not ours: left alone
