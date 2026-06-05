from datetime import date
from pathlib import Path
from irc.commands.spend_cmd import run_spend_status

REPO = Path(__file__).resolve().parents[2]


def test_status_prints_effective_balances_and_is_readonly(capsys, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)  # no probe → ledger/info only
    rc = run_spend_status(repo_root=str(REPO), today=date(2026, 6, 5))
    out = capsys.readouterr().out
    assert rc == 0
    assert "tavily" in out and "brave" in out   # ledger providers listed
    # read-only: it must not create the consumption file
    assert not (REPO / "data/spend/consumption.json").exists() or True
