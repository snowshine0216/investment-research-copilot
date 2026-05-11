from __future__ import annotations
from click.testing import CliRunner
from irc.cli import main


def test_ask_rejects_oversized_question(tmp_path):
    huge = "x" * 5000
    r = CliRunner().invoke(main, ["ask", "--repo-root", str(tmp_path), huge])
    assert r.exit_code != 0
    assert "max length" in r.output.lower()
