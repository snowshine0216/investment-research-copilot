from pathlib import Path
from irc.commands.validate_cmd import run_validate


def test_validate_passes_with_spend_configs(capsys):
    repo = Path(__file__).resolve().parents[2]
    rc = run_validate(repo_root=str(repo))
    out = capsys.readouterr().out
    assert rc == 0
    assert "spend" in out.lower()
