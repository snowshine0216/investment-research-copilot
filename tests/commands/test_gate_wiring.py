import importlib
import pytest

# (runner_module, runner_attr, gate_command)
WIRED = [
    ("irc.commands.memo_cmd", "run_memo", "memo"),
    ("irc.commands.opportunity_cmd", "run_opportunity", "opportunity"),
    ("irc.commands.ask_cmd", "run_ask", "ask"),
    ("irc.commands.decision_cmd", "run_decision", "decision"),
]


@pytest.mark.parametrize("mod_name, attr, command", WIRED)
def test_runner_stops_when_gate_blocks(monkeypatch, mod_name, attr, command):
    mod = importlib.import_module(mod_name)
    seen = {}
    def fake_gate(repo_root, cmd, **kw):
        seen["command"] = cmd
        return 5
    monkeypatch.setattr("irc.commands.spend_cmd.preflight_gate", fake_gate)
    runner = getattr(mod, attr)
    # ask takes a question kwarg; others take repo_root only
    kwargs = {"question": "x"} if attr == "run_ask" else {}
    rc = runner(repo_root=".", **kwargs)
    assert rc == 5
    assert seen["command"] == command
