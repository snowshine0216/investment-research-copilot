import importlib
import inspect
import pytest

# (runner_module, runner_attr, gate_command)
WIRED = [
    ("irc.commands.memo_cmd", "run_memo", "memo"),
    ("irc.commands.opportunity_cmd", "run_opportunity", "opportunity"),
    ("irc.commands.ask_cmd", "run_ask", "ask"),
    ("irc.commands.decision_cmd", "run_decision", "decision"),
]

# Every paid runner must call the gate. eval-funds / narrative gate AFTER their
# arg-validation guards (db/quarter, narrative lookup), so a dynamic call can't
# reach the gate without heavy fixtures — guard them statically instead. This
# catches a gate accidentally dropped from any runner.
ALL_GATED = WIRED + [
    ("irc.commands.fund_eval_cmd", "run_eval_funds", "eval-funds"),
    ("irc.commands.narrative_cmd", "run_narrative", "narrative"),
]


@pytest.mark.parametrize("mod_name, attr, command", ALL_GATED)
def test_runner_source_invokes_preflight_gate(mod_name, attr, command):
    mod = importlib.import_module(mod_name)
    src = inspect.getsource(getattr(mod, attr))
    assert f'preflight_gate(repo_root, "{command}")' in src, (
        f"{attr} no longer calls preflight_gate(repo_root, {command!r})"
    )


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
