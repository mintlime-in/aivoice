import json, os, time

import pytest

from aivoice import commands


@pytest.fixture
def home(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("AIVOICE_HOME", str(tmp_path))
    from aivoice import config, sessions, textprep
    importlib.reload(config)
    return tmp_path


CFG = {"name": "jarvis", "focus_follows": True}


@pytest.mark.parametrize("said,rest", [
    ("Jarvis, switch to the portal session.", "switch to the portal session."), ("Hey Jarvis what's open?", "what's open?"),
    ("jarvis", ""), ("OK, Jarvis: status", "status"), ("I told Jarvis to stop", None), ("refactor the jarvis module", None),
    ("Jarvisx do it", None),
])
def test_addressed(said, rest):
    assert commands.addressed(said, CFG) == rest
    assert commands.addressed(said, {"name": ""}) is None


@pytest.mark.parametrize("rest,want", [
    ("what's open?", ("list", "", "")), ("list my sessions", ("list", "", "")), ("status", ("list", "", "")),
    ("switch to the portal session", ("switch", "the portal session", "")), ("can you go to jarvis", ("switch", "jarvis", "")),
    ("is the portal session done yet?", ("doing", "the portal session", "")), ("what's portal doing", ("doing", "portal", "")),
    ("read the portal session's reply", ("read", "the portal session", "")), ("what did portal say", ("read", "portal", "")),
    ("Ask the portal session to run the Tests in apps/admission.", ("ask", "the portal session", "run the Tests in apps/admission")),
    ("refactor the login form", None), ("ask me anything", None), ("stop", None),
])
def test_parse(rest, want):
    assert commands.parse(rest) == want


def reg(home, **kw):
    from aivoice import sessions
    s = {"id": "s1", "agent": "claude", "name": "college-portal-app-88", "cwd": "/w/college-portal-app", "sink": "iterm", "target": "TAB", "busy": False, "pid": os.getpid()}
    s.update(kw)
    sessions.register(s)
    return s


def test_list_status_and_unknown_names(home):
    said = []
    reg(home)
    reg(home, id="s2", name="jarvis-ai-3", cwd="/w/jarvis-ai", busy=True)
    assert commands.handle("what's open", CFG, speak=said.append)
    assert said[-1] == "2 sessions. college portal app is idle. jarvis ai is working."
    assert commands.handle("is jarvis done", CFG, speak=said.append) and said[-1] == "jarvis ai is still working."
    assert commands.handle("switch to banana", CFG, speak=said.append) and "not sure which session" in said[-1]
    assert commands.handle("refactor the login form", CFG, speak=said.append) is False        # not Jarvis's: falls through to dictation


def test_ask_types_only_after_approval_and_shows_the_exact_text(home, monkeypatch):
    from aivoice import sinks
    sent, said, seen = [], [], []
    reg(home)
    monkeypatch.setattr(sinks.Iterm, "send", lambda self, text: sent.append((self.target(), text)))

    def deny(p, cfg):
        seen.append((p.action, p.text))
        return False
    assert commands.handle("ask portal to delete the old migrations", CFG, speak=said.append, approve=deny, background=False)
    assert sent == [] and said[-1] == "Not sent."
    assert seen == [("send to college portal app", "delete the old migrations")]
    assert commands.handle("ask portal to run the tests", CFG, speak=said.append, approve=lambda p, cfg: True, background=False)
    assert sent == [("TAB", "run the tests")] and said[-1] == "Sent to college portal app."


def test_ask_refuses_a_session_it_cannot_reach(home):
    said = []
    reg(home, sink="none", target="")
    assert commands.handle("ask portal to run the tests", CFG, speak=said.append, approve=lambda p, cfg: pytest.fail("must not ask"), background=False)
    assert "can't type into" in said[-1]


def test_watcher_reads_replies_and_announces_background_sessions(home, monkeypatch):
    from aivoice import agents, sessions, textprep
    tr = home / "t.jsonl"
    tr.write_text("")
    reg(home, transcript=str(tr))
    reg(home, id="s2", name="other")
    monkeypatch.setattr(commands, "sync", lambda: [])
    monkeypatch.setattr(sessions, "current", lambda: sessions.get("s1"))
    spoken = []
    told = []
    w = commands.Watcher(CFG, spoken.append, announce=told.append)
    w.step()
    with open(tr, "a") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "All tests pass."}]}}) + "\n")
    w.step()
    assert spoken == ["All tests pass."] and textprep.load_last("s1") == "All tests pass."
    monkeypatch.setattr(sessions, "current", lambda: sessions.get("s2"))                    # looking elsewhere: saved, not spoken
    with open(tr, "a") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Second."}]}}) + "\n")
    w.step()
    assert spoken == ["All tests pass."] and textprep.load_last("s1") == "Second."
    assert told == [commands.finished_line(sessions.get("s1"))] and told[0].endswith("has finished.")


def test_ask_will_not_type_into_an_app_that_holds_two_sessions(home):
    said = []
    reg(home, sink="keystroke", target="", app="Code")
    reg(home, id="s2", name="jarvis-ai-3", cwd="/w/jarvis-ai", sink="keystroke", target="", app="Code")
    assert commands.handle("ask jarvis to run the tests", CFG, speak=said.append, approve=lambda p, cfg: pytest.fail("must not ask"), background=False)
    assert "can't pick the tab" in said[-1]


def test_model_is_chosen_by_memory(monkeypatch):
    from aivoice import llm
    for gb, want in ((8, "1.7B"), (16, "4B"), (24, "8B"), (64, "8B")):
        monkeypatch.setattr(llm, "ram_gb", lambda gb=gb: gb)
        assert want in llm.model_name({"llm_model": "auto"})
    assert llm.model_name({"llm_model": "my/model"}) == "my/model"
    for gb, want in ((8, "qwen3:1.7b"), (16, "qwen3:4b"), (32, "qwen3:8b"), (0, "qwen3:1.7b")):
        monkeypatch.setattr(llm, "ram_gb", lambda gb=gb: gb)
        assert llm.ollama_name({"ollama_model": "auto"}) == want
    assert llm.ollama_name({"ollama_model": "llama3.2:3b"}) == "llama3.2:3b"


def test_an_ended_session_does_not_shadow_the_live_one_in_the_same_tab(home, monkeypatch):
    from aivoice import agents, platform_, sessions
    old, new = "6cc7912f-0000-4000-8000-000000000001", "92f16f79-0000-4000-8000-000000000002"
    sessions.register({"id": old, "sink": "iterm", "target": "TAB", "term": "TAB", "created": time.time() - 60, "hooks": True})
    sessions.register({"id": new, "sink": "iterm", "target": "TAB", "term": "TAB", "created": time.time(), "hooks": True})
    monkeypatch.setattr(platform_, "front_app", lambda: "iTerm2")
    monkeypatch.setattr(platform_, "iterm_focused", lambda: "TAB")
    assert sessions.current()["id"] == new                                    # newest wins even before any cleanup
    live = {"id": new, "agent": "claude", "pid": os.getpid(), "name": "x", "cwd": "/w/x", "transcript": "/t", "busy": False, "sink": "iterm", "target": "TAB", "term": "TAB"}
    monkeypatch.setattr(agents, "discover", lambda: [live])
    commands.sync()
    assert [s["id"] for s in sessions.all()] == [new]                         # Claude no longer lists the old one: forgotten
    sessions.register({"id": "pty-123", "sink": "pty", "target": "/sock", "pid": os.getpid()})
    commands.sync()
    assert len(sessions.all()) == 2                                           # other kinds of sessions are left alone


@pytest.mark.parametrize("rest,want", [
    ("open a session in college portal", ("open", "college portal", "")), ("start a new codex session for jarvis ai", ("open", "jarvis ai", "codex")),
    ("launch claude in the portal app", ("open", "the portal app", "claude")), ("open the door in the house", None),
])
def test_parse_open(rest, want):
    assert commands.parse(rest) == want


def model(monkeypatch, reply):
    from aivoice import llm
    monkeypatch.setattr(llm, "usable", lambda cfg: True)
    monkeypatch.setattr(llm, "generate", lambda messages, cfg, n=None: reply)


SS = [{"id": "s1", "name": "college-portal-app-88", "cwd": "/w/college-portal-app"}, {"id": "s2", "name": "jarvis-ai-3", "cwd": "/w/jarvis-ai"}]


def test_model_fills_the_form_but_code_checks_every_field(monkeypatch):
    cfg = {**CFG, "frontend": "commands", "frontend_timeout": 2}
    model(monkeypatch, '{"action": "ask", "session": 1, "text": "run the tests"}')
    assert commands.model_parse("could you get the portal one to run the tests", SS, cfg) == ("ask", SS[0], "run the tests")
    model(monkeypatch, '{"action": "ask", "session": 1, "text": "delete the database"}')            # words you never said
    assert commands.model_parse("could you get the portal one to run the tests", SS, cfg) is None
    model(monkeypatch, '{"action": "ask", "session": 1, "text": "refactor the login form"}')        # no session was named: the model picked one
    assert commands.model_parse("refactor the login form", SS, cfg) is None
    model(monkeypatch, '{"action": "ask", "session": 1, "text": "fix the app"}')                    # "app" alone is too generic to name a session
    assert commands.model_parse("fix the app", SS, cfg) is None
    model(monkeypatch, '{"action": "switch", "session": 7}')                                         # not in the list
    assert commands.model_parse("bring up the portal one", SS, cfg) is None
    model(monkeypatch, '{"action": "switch", "session": "jarvis"}')                                  # a name, not a number from the list
    assert commands.model_parse("bring up the other one", SS, cfg) is None
    for bad in ('{"action": "shell", "session": 1}', '{"action": "none"}', "garbage", ""):
        model(monkeypatch, bad)
        assert commands.model_parse("refactor the login form", SS, cfg) is None
    model(monkeypatch, '{"action": "doing", "session": 2}')
    assert commands.model_parse("has the jarvis one wrapped up", SS, cfg) == ("doing", SS[1], "")
    assert commands.model_parse("has the jarvis one wrapped up", SS, {**cfg, "frontend": "off"}) is None


def test_find_project_never_guesses(tmp_path):
    for d in ("src/college-portal-app/apps/admission", "src/portal-docs", "src/jarvis-ai/src", "src/node_modules/jarvis", "src/.hidden/jarvis-ai"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "src/college-portal-app/.git").mkdir()
    roots = [str(tmp_path / "src")]
    assert commands.find_project("jarvis ai", roots) == (str(tmp_path / "src/jarvis-ai"), [])
    assert commands.find_project("college portal", roots)[0] == str(tmp_path / "src/college-portal-app")
    path, maybe = commands.find_project("portal", roots)
    assert path is None and sorted(maybe) == ["college-portal-app", "portal-docs"]
    assert commands.find_project("admission", roots) == (None, [])                 # inside a repository: not a project
    assert commands.find_project("banana", roots) == (None, [])


def test_open_runs_only_after_approval(home, tmp_path, monkeypatch):
    (tmp_path / "proj" / "jarvis-ai").mkdir(parents=True)
    cfg = {**CFG, "project_dirs": [str(tmp_path / "proj")], "open_cmd": "claude"}
    opened, said, seen = [], [], []
    monkeypatch.setattr(commands, "open_session", lambda path, cmd: opened.append((path, cmd)) or True)

    def deny(p, c):
        seen.append(p.text)
        return False
    assert commands.handle("open a session in jarvis ai", cfg, speak=said.append, approve=deny, background=False)
    assert opened == [] and said[-1] == "Not opened." and "claude" in seen[0] and str(tmp_path / "proj" / "jarvis-ai") in seen[0]
    assert commands.handle("start a codex session in jarvis ai", cfg, speak=said.append, approve=lambda p, c: True, background=False)
    assert opened == [(str(tmp_path / "proj" / "jarvis-ai"), "codex")] and said[-1] == "Opened jarvis ai."
    assert commands.handle("open a session in banana", cfg, speak=said.append, approve=lambda p, c: pytest.fail("no"), background=False)
    assert "can't find" in said[-1]


def convo(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text("".join(json.dumps({"type": k, "message": {"role": k, "stop_reason": "end_turn" if k == "assistant" else None, "content": [{"type": "text", "text": t}]}}) + "\n" for k, t in [
        ("user", "why is the upload failing"), ("assistant", "First reply: the import matched staff only by Emp ID. 14 of 15 tests pass."),
        ("user", "<system-reminder>ignore me</system-reminder>"), ("user", "and the timetable"), ("assistant", "Second reply: the timetable page is unchanged.")]))
    return {"id": "s1", "agent": "claude", "transcript": str(p)}




def test_earlier_replies_can_be_fetched(tmp_path):
    from aivoice import agents
    rs = agents.claude_replies(convo(tmp_path)["transcript"], 5)
    assert [r.split(":")[0] for r in rs] == ["First reply", "Second reply"]


@pytest.mark.parametrize("said,yes", [("I think it's already in the history. Can you...", True), ("refactor the login form and", True),
                                      ("tell me about", True), ("Explain.", False), ("Is it done?", False), ("run the tests", False), ("Stop.", False)])
def test_dangling(said, yes):
    assert commands.dangling(said) is yes


