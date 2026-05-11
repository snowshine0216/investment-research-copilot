"""
Mocked E2E smoke: generated CN fund universe flows through the discovery pipeline.

Flow: init → build-cn-funds (Akshare mocked) → ingest (mocked) → discover (mocked LLM)
Verifies that "003095" (CN equity fund) appears in the watchlist and that diagnostics CSV
contains "cn_equity_fund" in the asset_class column.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from click.testing import CliRunner

from irc.cli import main


# ─── Fake catalog returned by fetch_open_fund_catalog ────────────────────────

def _fake_catalog() -> pd.DataFrame:
    """Return a minimal open-fund catalog containing 003095 (CN equity fund)."""
    return pd.DataFrame([
        {
            "fund_code": "003095",
            "fund_name": "中欧医疗健康混合A",  # CN equity fund (healthcare theme)
            "fund_type": "混合型",
        }
    ])


# ─── Fake metadata / metrics ─────────────────────────────────────────────────

def _fake_fund_metadata(fund_code: str) -> dict:
    return {
        "fund_code": fund_code,
        "name_cn": f"基金{fund_code}",
        "fund_type": "混合型",
        "aum_text": "200亿",
        "inception_date": "2018-03-26",
        "expense_ratio": "1.2%",
        "manager_tenure_years": 6,
    }


def _fake_prices() -> pd.DataFrame:
    import datetime
    rows = [
        {"date": datetime.date(2026, d, 1), "open": 3300.0 + d, "high": 3310.0 + d,
         "low": 3290.0 + d, "close": 3305.0 + d, "volume": 1.5e8}
        for d in range(1, 10)
    ]
    return pd.DataFrame(rows)


def _fake_macro() -> pd.DataFrame:
    import datetime
    return pd.DataFrame({"date": [datetime.date(2026, 5, 7)], "value": [1.65]})


def _fake_nav() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.234, 1.245], "nav_acc": [2.345, 2.356],
    })


def _raw_ref_from_messages(messages: list[dict]) -> str:
    user_message = next((m["content"] for m in messages if m.get("role") == "user"), "")
    marker = "Available raw_refs: "
    if marker not in user_message:
        return "akshare:nav_history:003095:2026-05-07"
    raw_refs = user_message.split(marker, 1)[1].splitlines()[0]
    return raw_refs.split(", ", 1)[0].strip()


def _discover_chat_response(raw_ref: str) -> MagicMock:
    return MagicMock(
        text=f"Strong CN healthcare thesis citing {raw_ref}.",
        prompt_tokens=10,
        completion_tokens=5,
    )


# ─── Test ─────────────────────────────────────────────────────────────────────

def test_generated_cn_fund_flows_through_discovery(tmp_path: Path) -> None:
    runner = CliRunner()

    # 1) init
    r = runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    assert r.exit_code == 0, f"init failed:\n{r.output}"

    # 2) universe build-cn-funds — Akshare mocked
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_fake_catalog()):
        r = runner.invoke(main, ["universe", "build-cn-funds", "--repo-root", str(tmp_path)])
    assert r.exit_code == 0, f"universe build-cn-funds failed:\n{r.output}"
    generated = tmp_path / "config" / "universe" / "cn_funds.generated.yaml"
    assert generated.exists(), "generated file not created"

    # 3) ingest + discover — Akshare and LLM mocked
    patches = [
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=_fake_prices()),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=_fake_macro()),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=_fake_nav()),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
        patch("irc.discovery.reason_writer.call_chat",
              side_effect=lambda *a, **kw: _discover_chat_response(
                  _raw_ref_from_messages(kw.get("messages", []))
              )),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        r = runner.invoke(main, ["ingest", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"ingest failed:\n{r.output}"

        r = runner.invoke(main, ["discover", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"discover failed:\n{r.output}"

    # 4) verify watchlist contains 003095
    watchlists = list((tmp_path / "outputs").rglob("discovered_watchlist.csv"))
    assert watchlists, "no discovered_watchlist.csv found"
    watchlist_df = pd.read_csv(watchlists[0], dtype={"instrument_id": str})
    assert "003095" in watchlist_df["instrument_id"].values, (
        f"003095 not in watchlist:\n{watchlist_df}"
    )

    # 5) verify diagnostics CSV has cn_equity_fund
    diag_files = list((tmp_path / "outputs").rglob("discovery_diagnostics.csv"))
    assert diag_files, "no discovery_diagnostics.csv found"
    diag_df = pd.read_csv(diag_files[0])
    assert "cn_equity_fund" in diag_df["asset_class"].values, (
        f"cn_equity_fund not in diagnostics asset_class:\n{diag_df}"
    )
