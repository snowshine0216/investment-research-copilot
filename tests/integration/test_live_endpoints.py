"""Live end-to-end tests for every external endpoint the ingest pipeline relies on.

Why this file exists: mocked unit tests can pass while production silently fails.
This file hits the real network and asserts on real responses, so a green run
proves data sources actually work for your IP / network / time-of-day.

Run:    RUN_LIVE_INGEST_TESTS=1 uv run pytest tests/integration/test_live_endpoints.py -v -s
Skip:   default `pytest` runs ignore this file unless the env var is set.

Diagnostic policy: each test prints a one-line summary of what it just verified,
so a failing run produces a readable signal of which upstream is broken.

Layered coverage (bottom-up):
  Layer 1 — raw upstream APIs
    • akshare: fund_individual_basic_info_xq (DanJuanFunds; off-exchange feeders)
    • akshare: fund_open_fund_info_em       (NAV history)
    • akshare: bond_zh_us_rate              (DGS10 macro fallback)
    • akshare: index_global_hist_em         (DXY macro fallback)
    • EastMoney HTML profile page           (on-exchange ETF metadata)
    • OpenBB → yfinance equity.price.historical with .SS / .SZ suffix
  Layer 2 — irc data clients (these wrap layer 1)
    • fetch_fund_metadata, fetch_etf_metadata_em, fetch_fund_nav_history
    • fetch_etf_price_history, fetch_macro_series (incl. fallback chain)
  Layer 3 — full irc ingest end-to-end
    • runs `irc init` + `irc ingest` against a tmp dir, asserts DuckDB row counts
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

_RUN = os.environ.get("RUN_LIVE_INGEST_TESTS") == "1"
pytestmark = pytest.mark.skipif(not _RUN, reason="set RUN_LIVE_INGEST_TESTS=1 to run live network tests")


# ─── Layer 1: raw upstream APIs ──────────────────────────────────────────────


def test_akshare_danjuan_off_exchange_feeder() -> None:
    """DanJuanFunds carries open-ended retail feeders (006075-style)."""
    from irc.data.akshare_client import _ak_call
    df = _ak_call("fund_individual_basic_info_xq", symbol="006075")
    assert not df.empty, "DanJuanFunds returned empty for 006075"
    print(f"\n  ✓ DanJuan/006075 → {len(df)} rows")


def test_akshare_eastmoney_nav_history() -> None:
    """EastMoney NAV history is the standard source for cn_funds."""
    from irc.data.akshare_client import _ak_call
    df = _ak_call("fund_open_fund_info_em", symbol="510300", indicator="单位净值走势")
    assert not df.empty, "EastMoney NAV empty for 510300"
    assert "净值日期" in df.columns
    print(f"\n  ✓ EastMoney NAV/510300 → {len(df)} rows, latest={df.iloc[-1]['净值日期']}")


def test_akshare_bond_zh_us_rate_for_dgs10() -> None:
    """bond_zh_us_rate is the no-auth fallback for FRED's DGS10."""
    from irc.data.akshare_client import _ak_call
    df = _ak_call("bond_zh_us_rate")
    assert not df.empty
    assert "美国国债收益率10年" in df.columns
    latest = df.dropna(subset=["美国国债收益率10年"]).iloc[-1]
    print(f"\n  ✓ akshare/US-10y → {latest['日期']} = {latest['美国国债收益率10年']:.3f}%")


def test_akshare_dxy_via_global_index() -> None:
    """DXY (美元指数) historical via index_global_hist_em is the fallback for DTWEXBGS."""
    from irc.data.akshare_client import _ak_call
    df = _ak_call("index_global_hist_em", symbol="美元指数")
    assert not df.empty
    print(f"\n  ✓ akshare/DXY → {len(df)} rows, latest={df.iloc[-1]['日期']} value={df.iloc[-1]['最新价']}")


def test_eastmoney_etf_profile_page_for_each_user_ticker() -> None:
    """Verify the EastMoney HTML scraper works for every on-exchange ETF in the
    project's default universe — the previously failing tickers."""
    from irc.data.akshare_client import fetch_etf_metadata_em
    on_exchange = ["513500", "159941", "513180", "513530", "159920", "518880", "159934", "510300", "510500"]
    failures: list[str] = []
    for code in on_exchange:
        try:
            m = fetch_etf_metadata_em(code)
            assert m["inception_date"], f"{code}: missing inception_date"
            assert m["aum_text"], f"{code}: missing aum_text"
            assert m["expense_ratio"] is not None, f"{code}: missing expense_ratio"
            print(f"  ✓ EM/{code} → {m['name_cn']!r} inception={m['inception_date']} aum={m['aum_text']} fee={m['expense_ratio']}")
        except Exception as exc:
            failures.append(f"{code}: {type(exc).__name__}: {exc}")
            print(f"  ✗ EM/{code} → {exc}")
    assert not failures, f"{len(failures)}/{len(on_exchange)} EM scrapes failed:\n  " + "\n  ".join(failures)


def test_akshare_etf_price_history_for_cn_ticker() -> None:
    """fund_etf_hist_em is the canonical CN-ETF price source. Used as the
    primary path for 6-digit numeric tickers (yfinance rate-limits these)."""
    from irc.data.akshare_client import fetch_etf_price_history_akshare
    df = fetch_etf_price_history_akshare("513500", start="2026-04-01", end="2026-05-07")
    assert not df.empty, "akshare returned no price history for 513500"
    assert {"date", "open", "high", "low", "close", "volume"} <= set(df.columns)
    print(f"\n  ✓ akshare/513500 prices → {len(df)} rows, latest close={df.iloc[-1]['close']:.2f}")


def test_yfinance_via_openbb_for_us_ticker() -> None:
    """Non-CN tickers still go through OpenBB+yfinance. Skipped silently when
    yfinance is rate-limiting (an environment issue, not a code defect)."""
    from irc.data.openbb_client import fetch_etf_price_history
    try:
        df = fetch_etf_price_history(ticker="SPY", start="2026-04-01", end="2026-05-01")
    except Exception as exc:
        pytest.skip(f"yfinance unavailable in this env: {exc}")
    assert not df.empty
    print(f"\n  ✓ yf/SPY → {len(df)} rows, latest close={df.iloc[-1]['close']:.2f}")


def test_fetch_etf_price_history_routes_cn_ticker_to_akshare() -> None:
    """The unified fetch_etf_price_history must succeed for a CN ticker even
    when yfinance is rate-limited — proves the akshare-first routing works."""
    from irc.data.openbb_client import fetch_etf_price_history
    df = fetch_etf_price_history(ticker="513500", start="2026-04-01", end="2026-05-07")
    assert not df.empty
    assert "close" in df.columns
    print(f"\n  ✓ unified/513500 → {len(df)} rows, latest close={df.iloc[-1]['close']:.2f}")


def test_openbb_fred_macro_series_known_unauth_failure() -> None:
    """OpenBB's FRED provider needs FRED_API_KEY or INTRINIO_API_KEY. Without
    either, the call must fail — this test documents that and is the trigger
    that activates the akshare fallback path."""
    if os.environ.get("FRED_API_KEY") or os.environ.get("INTRINIO_API_KEY"):
        pytest.skip("FRED/INTRINIO key set — fallback not exercised in this env")
    from irc.data.openbb_client import _call_obb
    with pytest.raises(Exception) as excinfo:
        _call_obb("economy.fred_series", symbol="DGS10", start_date="2026-01-01", end_date="2026-05-01")
    msg = str(excinfo.value)
    print(f"\n  ✓ FRED unauthed (expected) → {msg.splitlines()[0][:120]}")


# ─── Layer 2: irc data clients (wrappers + fallbacks) ─────────────────────────


def test_fetch_macro_series_falls_back_to_akshare_when_fred_unavailable() -> None:
    """fetch_macro_series tries OpenBB+FRED first; on failure (no API key)
    falls back to akshare. With no FRED key set the akshare path must succeed."""
    from irc.data.openbb_client import fetch_macro_series
    df = fetch_macro_series(series_id="DGS10", start="2026-01-01", end="2026-05-01")
    assert not df.empty, "macro fallback returned empty for DGS10"
    assert {"date", "value"} <= set(df.columns)
    print(f"\n  ✓ fetch_macro_series(DGS10) via fallback → {len(df)} rows, latest={df.iloc[-1]['date']} value={df.iloc[-1]['value']}")


def test_fetch_macro_series_falls_back_for_dxy() -> None:
    from irc.data.openbb_client import fetch_macro_series
    df = fetch_macro_series(series_id="DTWEXBGS", start="2026-01-01", end="2026-05-01")
    assert not df.empty
    assert {"date", "value"} <= set(df.columns)
    print(f"\n  ✓ fetch_macro_series(DTWEXBGS) via fallback → {len(df)} rows, latest={df.iloc[-1]['date']} value={df.iloc[-1]['value']}")


def test_fetch_fund_metadata_for_off_exchange_feeder() -> None:
    from irc.data.akshare_client import fetch_fund_metadata
    out = fetch_fund_metadata("006075")
    assert out["fund_code"] == "006075"
    assert out["inception_date"], "missing inception_date"
    print(f"\n  ✓ fetch_fund_metadata/006075 → {out['name_cn']!r} inception={out['inception_date']}")


def test_fetch_fund_nav_history_for_on_exchange_etf() -> None:
    from irc.data.akshare_client import fetch_fund_nav_history
    df = fetch_fund_nav_history("510300")
    assert not df.empty
    assert {"date", "nav"} <= set(df.columns)
    print(f"\n  ✓ fetch_fund_nav_history/510300 → {len(df)} rows, latest={df.iloc[-1]['date']}")


# ─── Layer 3: full irc ingest end-to-end ──────────────────────────────────────


def _row_count(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _instrument_ids_with_data(con, table: str) -> set[str]:
    rows = con.execute(f"SELECT DISTINCT instrument_id FROM {table}").fetchall()
    return {r[0] for r in rows}


def test_irc_ingest_end_to_end_populates_duckdb(tmp_path: Path) -> None:
    """The whole point: run real `irc init` + `irc ingest` against the live
    network and assert DuckDB has rows for every category of instrument we
    expect to ingest. Skips cmb_paper_gold (intentionally — no public source)."""
    from irc.cli import main
    from irc.data.duckdb_helper import connect

    runner = CliRunner()
    init_result = runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    assert init_result.exit_code == 0, f"init failed:\n{init_result.output}"

    ingest_result = runner.invoke(main, ["ingest", "--repo-root", str(tmp_path)])
    assert ingest_result.exit_code == 0, f"ingest failed:\n{ingest_result.output}"

    con = connect(tmp_path / "data" / "local.duckdb")
    try:
        # All instruments enrolled (excluding cmb_paper_gold which we skip with warning):
        # qdii_us(5) + qdii_hk(3) + gold(3) + cn_funds(2) = 13 rows.
        assert _row_count(con, "instruments") == 13

        # Metadata coverage: every numeric-ticker instrument should have inception_date.
        missing_meta = con.execute(
            "SELECT instrument_id FROM instruments "
            "WHERE inception_date IS NULL AND instrument_id != 'cmb_paper_gold'"
        ).fetchall()
        assert not missing_meta, f"instruments missing inception_date: {[r[0] for r in missing_meta]}"

        # Price history: every cn_on_exchange instrument should have rows in `prices`.
        priced = _instrument_ids_with_data(con, "prices")
        expected_priced = {"513500", "159941", "159920", "513180", "513530", "518880", "159934"}
        missing_priced = expected_priced - priced
        assert not missing_priced, f"missing price data for on-exchange ETFs: {sorted(missing_priced)}"

        # NAV history: cn_funds + off-exchange feeders.
        nav_ids = _instrument_ids_with_data(con, "nav_history")
        expected_nav = {"510300", "510500", "006075", "050025", "161130"}
        missing_nav = expected_nav - nav_ids
        assert not missing_nav, f"missing NAV data: {sorted(missing_nav)}"

        # Macro series: DGS10 + DTWEXBGS via fallback chain.
        macro_series = {r[0] for r in con.execute("SELECT DISTINCT series_id FROM macro_series").fetchall()}
        assert macro_series == {"DGS10", "DTWEXBGS"}, f"macro_series populated: {macro_series}"

        # Sanity: every populated table has > 0 rows.
        for tbl in ("instruments", "prices", "nav_history", "macro_series"):
            n = _row_count(con, tbl)
            print(f"  ✓ {tbl}: {n} rows")
            assert n > 0, f"{tbl} is empty"
    finally:
        con.close()
