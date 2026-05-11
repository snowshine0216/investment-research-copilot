from __future__ import annotations
from pathlib import Path
from click.testing import CliRunner
from irc.cli import main


def test_cli_help_lists_subcommands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "config", "freshness", "universe"):
        assert cmd in result.output


def test_cli_config_help():
    result = CliRunner().invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.output


def test_cli_init_then_validate_then_freshness(tmp_path: Path):
    runner = CliRunner()
    r1 = runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(main, ["config", "validate", "--repo-root", str(tmp_path)])
    assert r2.exit_code == 0, r2.output
    assert "OK" in r2.output
    r3 = runner.invoke(main, ["freshness", "--repo-root", str(tmp_path)])
    assert r3.exit_code == 0, r3.output
    assert "no manifest" in r3.output.lower()


def test_cli_init_force_after_modification(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    pref = tmp_path / "inputs/preferences.yaml"
    pref.write_text("# corrupted\n", encoding="utf-8")
    r = runner.invoke(main, ["config", "validate", "--repo-root", str(tmp_path)])
    assert r.exit_code != 0
    runner.invoke(main, ["init", "--repo-root", str(tmp_path), "--force"])
    r2 = runner.invoke(main, ["config", "validate", "--repo-root", str(tmp_path)])
    assert r2.exit_code == 0
