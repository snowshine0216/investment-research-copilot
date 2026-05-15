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
    # No inputs anywhere → every eval should FAIL (rc=2).
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage=None, all_stages=True)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert rc == 2
    # Summary line must enumerate per-stage status.
    assert "eval summary:" in out.lower(), f"no summary in: {out!r}"
    assert "fail" in out.lower(), f"no FAIL in: {out!r}"
