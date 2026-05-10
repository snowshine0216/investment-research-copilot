from __future__ import annotations
from pathlib import Path
import pytest
from click.testing import CliRunner
from irc.cli import main
from irc.commands.init_cmd import run_init


def test_eval_architecture_only(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "architecture", "--repo-root", str(tmp_path)])
    assert r.exit_code in (0, 1)  # PASS or WARN allowed


def test_eval_unknown_stage_errors(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "ghost", "--repo-root", str(tmp_path)])
    assert r.exit_code != 0
