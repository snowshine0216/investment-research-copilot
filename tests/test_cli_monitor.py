from __future__ import annotations

from click.testing import CliRunner

from irc.cli import main


def test_monitor_group_registered():
    res = CliRunner().invoke(main, ["monitor", "--help"])
    assert res.exit_code == 0
    assert "snapshot" in res.output


def test_monitor_snapshot_registered():
    res = CliRunner().invoke(main, ["monitor", "snapshot", "--help"])
    assert res.exit_code == 0
