import pytest

from aivoice import wake


@pytest.mark.parametrize("said,want", [
    ("Claude, run the tests.", ("Claude", "run the tests.")), ("Hey Claude what's failing?", ("Claude", "what's failing?")),
    ("Hey Cloud, check the build", ("Claude", "check the build")), ("OK ChatGPT: write a haiku", ("ChatGPT", "write a haiku")),
    ("Hey chat GPT, summarize this", ("ChatGPT", "summarize this")), ("Codex, fix it", ("Codex", "fix it")),
    ("I told Claude about it", None), ("cloudy today, isn't it", None), ("run the tests", None),
])
def test_addressed_to(said, want):
    assert wake.addressed_to(said) == want


def test_tool_for_a_session_or_the_app_in_front():
    assert wake.tool_for({"agent": "claude", "sink": "iterm"}) == "Claude"
    assert wake.tool_for({"sink": "pty", "cmd": "codex"}) == "Codex"
    assert wake.tool_for(None, "ChatGPT") == "ChatGPT"
    assert wake.tool_for(None, "Claude") == "Claude" and wake.tool_for(None, "Cursor") == "Cursor"
    assert wake.tool_for(None, "Finder") == ""


def test_gate_sends_only_what_is_addressed_then_stays_awake_briefly():
    g = wake.Gate(window=30)
    assert g.check("so what do you think about lunch", "Claude", "tab1", 0) == ("ignore", "")       # room chatter
    assert g.check("Claude, run the tests", "Claude", "tab1", 10) == ("send", "run the tests")
    assert g.check("and the linter too", "Claude", "tab1", 20) == ("send", "and the linter too")     # follow-up, no name
    assert g.check("anything at all", "Claude", "tab1", 60) == ("ignore", "")                         # window over
    assert g.check("Hey Codex, do it", "Claude", "tab1", 61) == ("other", "Codex")                    # wrong tool in front
    g.check("Claude, hello", "Claude", "tab1", 70)
    assert g.check("follow-up", "Claude", "tab2", 75) == ("ignore", "")                               # awake is per tab
    assert g.check("Claude", "Claude", "tab1", 80) == ("send", "")                                    # just the name: wakes it
