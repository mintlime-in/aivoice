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


def test_a_short_reply_is_spoken_at_once_without_the_summary_model(monkeypatch):
    from aivoice import listener, tts_client
    said = []
    monkeypatch.setattr(tts_client, "speak", lambda text, voice="": said.append(text))
    monkeypatch.setattr(listener, "use_llm", lambda: True)
    monkeypatch.setattr(listener, "_llm_brief", lambda raw: said.append("<summary model>"))
    listener.speak_raw("It's 7:45 PM IST on Saturday, November 14, 2026.", "brief")
    assert said == ["It's 7:45 PM IST on Saturday, November 14, 2026."]
    said.clear()
    listener.speak_raw("A long reply. " * 60, "brief")
    import time; time.sleep(0.05)
    assert said == ["<summary model>"]


def test_the_first_piece_of_speech_is_short_so_the_voice_starts_sooner():
    from aivoice.textprep import chunks
    assert chunks("It's 7:45 PM IST on Saturday, November 14, 2026.") == ["It's 7:45 PM IST on Saturday,", "November 14, 2026."]
    assert chunks("Done. All 42 tests pass. The build is green.") == ["Done.", "All 42 tests pass. The build is green."]
    long = "First. " + "A sentence of medium length here. " * 12
    out = chunks(long)
    assert out[0] == "First." and all(len(c) <= 280 for c in out) and " ".join(out).split() == long.split()
