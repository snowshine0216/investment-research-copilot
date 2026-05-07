from __future__ import annotations
from click.testing import CliRunner
from irc.cli import main


def test_cli_help_lists_subcommands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "config", "freshness"):
        assert cmd in result.output


def test_cli_config_help():
    result = CliRunner().invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.output
