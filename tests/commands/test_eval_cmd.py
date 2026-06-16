from __future__ import annotations
from pathlib import Path
from click.testing import CliRunner
from irc.cli import main
from irc.commands.init_cmd import run_init


def test_eval_architecture_only(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "architecture", "--repo-root", str(tmp_path)])
    assert r.exit_code in (0, 1, 2)  # PASS/WARN/FAIL all valid; FAIL when outputs/ absent


def test_eval_unknown_stage_errors(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "ghost", "--repo-root", str(tmp_path)])
    assert r.exit_code != 0


def test_run_eval_all_prints_summary(tmp_path, capsys):
    # No inputs anywhere → every active stage should FAIL (rc=2).
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage=None, all_stages=True)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert rc == 2
    # Summary line must enumerate per-stage status.
    assert "eval summary:" in out.lower(), f"no summary in: {out!r}"
    assert "fail" in out.lower(), f"no FAIL in: {out!r}"


def test_eval_inactive_news_returns_inactive_message(tmp_path, capsys):
    """Direct invocation of news (inactive_legacy) must emit a clear
    inactive-stage message, not a misleading missing-input report.

    Item: AUTODEV-LOOP/items/002-spec.md
    """
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage="news", all_stages=False)
    captured = capsys.readouterr()
    out = (captured.out + captured.err).lower()
    assert rc == 2
    assert "inactive" in out
    assert "news" in out


def test_eval_inactive_queries_returns_inactive_message(tmp_path, capsys):
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage="queries", all_stages=False)
    captured = capsys.readouterr()
    out = (captured.out + captured.err).lower()
    assert rc == 2
    assert "inactive" in out
    assert "queries" in out


def test_eval_inactive_does_not_invoke_runner(tmp_path, monkeypatch):
    """Inactive-stage invocation must NOT import the runner module — otherwise
    the runner would write a misleading missing-input report."""
    from irc.commands import eval_cmd

    called: list[str] = []

    def fake_import(name: str):
        called.append(name)
        raise AssertionError(f"runner module {name} should not be imported for inactive stages")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage="news", all_stages=False)
    assert rc == 2
    assert called == []


def test_eval_all_excludes_inactive_stages(tmp_path, capsys):
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage=None, all_stages=True)
    captured = capsys.readouterr()
    out = (captured.out + captured.err).lower()
    assert rc == 2
    assert "news" not in out
    assert "queries" not in out
    for stage in ("data", "research", "discovery", "triggers"):
        assert stage in out, f"active stage {stage} missing from --all summary"


def test_live_gated_skips_without_env(tmp_path, monkeypatch, capsys):
    import json
    from datetime import datetime, timedelta, timezone
    from irc.commands.eval_cmd import run_eval
    monkeypatch.delenv("IRC_RUN_LIVE_LLM_EVAL", raising=False)
    rc = run_eval(str(tmp_path), stage="monitor_impact", all_stages=False)
    assert rc == 3
    out = capsys.readouterr().out.lower()
    assert "not executed" in out
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    report_path = tmp_path / "outputs" / today / "evals" / "monitor_impact" / "report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["overall"] == "SKIPPED"


def test_live_gated_skip_does_not_import_runner(tmp_path, monkeypatch):
    from irc.commands import eval_cmd
    monkeypatch.delenv("IRC_RUN_LIVE_LLM_EVAL", raising=False)
    called: list[str] = []

    def fake_import(name: str):
        called.append(name)
        raise AssertionError(f"runner module {name} must not import on SKIPPED path")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage="monitor_impact", all_stages=False)
    assert rc == 3 and called == []


def test_live_gated_gate_blocks_before_runner(tmp_path, monkeypatch):
    from irc.commands import eval_cmd
    monkeypatch.setenv("IRC_RUN_LIVE_LLM_EVAL", "1")
    seen = {}

    def fake_gate(repo_root, command, **kw):
        seen["command"] = command
        return 5

    monkeypatch.setattr(eval_cmd, "preflight_gate", fake_gate)

    def fake_import(name: str):
        raise AssertionError(f"runner {name} must not import when gate blocks")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage="monitor_impact", all_stages=False)
    assert rc == 5 and seen["command"] == "eval-live"
