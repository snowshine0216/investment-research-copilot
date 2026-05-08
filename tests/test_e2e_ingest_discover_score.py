from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from click.testing import CliRunner

from irc.cli import main


def _fake_fund_metadata(fund_code: str) -> dict[str, object]:
    return {
        "fund_code": fund_code,
        "name_cn": f"基金{fund_code}",
        "fund_type": "ETF",
        "aum_text": "200亿",
        "inception_date": "2018-03-26",
        "expense_ratio": "0.20%",
        "manager_tenure_years": 6,
    }


def _fake_prices() -> pd.DataFrame:
    return pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.20, 4.22], "high": [4.25, 4.30],
        "low": [4.18, 4.20], "close": [4.22, 4.28],
        "volume": [1.0e8, 1.1e8],
    })


def _fake_macro() -> pd.DataFrame:
    return pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})


def _fake_nav() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.234, 1.245], "nav_acc": [2.345, 2.356],
    })


def _fake_chat_response() -> MagicMock:
    return MagicMock(
        text='{"score": 70, "rationale": "stable rates"}',
        prompt_tokens=20, completion_tokens=10,
    )


def test_e2e_ingest_then_discover_then_score(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=_fake_prices()),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=_fake_macro()),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=_fake_nav()),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
    ):
        r1 = runner.invoke(main, ["ingest", "--repo-root", str(tmp_path)])
    assert r1.exit_code == 0, r1.output

    with patch(
        "irc.discovery.reason_writer.call_chat",
        return_value=MagicMock(
            text="Reason cites openbb:prices:006075:2026-05-06. Risk: USD risk.",
            prompt_tokens=10, completion_tokens=5,
        ),
    ):
        r2 = runner.invoke(main, ["discover", "--repo-root", str(tmp_path)])
    assert r2.exit_code == 0, r2.output
    watchlist_path = next((tmp_path / "outputs").rglob("discovered_watchlist.csv"))
    watchlist = pd.read_csv(watchlist_path)
    assert not watchlist.empty

    with patch(
        "irc.scoring.factors.macro_fit.call_chat",
        return_value=_fake_chat_response(),
    ):
        r3 = runner.invoke(main, ["score", "--repo-root", str(tmp_path)])
    assert r3.exit_code == 0, r3.output

    out_dirs = list((tmp_path / "outputs").iterdir())
    assert any((d / "discovered_watchlist.csv").exists() for d in out_dirs)
    assert any((d / "scoring.json").exists() for d in out_dirs)
