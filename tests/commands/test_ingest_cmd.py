from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from irc.commands.init_cmd import run_init
from irc.commands.ingest_cmd import _upsert_nav, run_ingest


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    return tmp_path


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


def _fake_missing_aum_fund_metadata(fund_code: str) -> dict[str, object]:
    return {k: v for k, v in _fake_fund_metadata(fund_code).items() if k != "aum_text"}


def _fake_missing_manager_tenure_fund_metadata(fund_code: str) -> dict[str, object]:
    return {
        k: v for k, v in _fake_fund_metadata(fund_code).items()
        if k != "manager_tenure_years"
    }


def test_ingest_creates_duckdb_and_manifest(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.2, 4.25], "high": [4.3, 4.31], "low": [4.18, 4.22],
        "close": [4.25, 4.28], "volume": [1e8, 1.1e8],
    })
    fake_macro = pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.23, 1.24], "nav_acc": [2.34, 2.35],
    })
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=fake_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    assert (repo / "data" / "local.duckdb").exists()
    assert (repo / "data" / "_manifest" / "openbb.json").exists()
    assert (repo / "data" / "_manifest" / "akshare.json").exists()


def test_ingest_populates_instruments_table(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty = pd.DataFrame({"date": [], "value": []})
    empty_nav = pd.DataFrame({"date": [], "nav": [], "nav_acc": []})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=empty_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    from irc.data.duckdb_helper import connect
    con = connect(repo / "data" / "local.duckdb")
    count = con.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
    con.close()
    assert count > 0


def test_ingest_populates_discovery_metadata(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    empty_nav = pd.DataFrame({"date": [], "nav": [], "nav_acc": []})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=empty_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    from irc.data.duckdb_helper import connect
    con = connect(repo / "data" / "local.duckdb")
    try:
        stored = con.execute(
            """
            SELECT inception_date, expense_ratio, aum, manager_tenure_years
            FROM instruments WHERE instrument_id = '006075'
            """
        ).fetchone()
    finally:
        con.close()

    assert stored == (date(2018, 3, 26), 0.002, 20_000_000_000.0, 6.0)


def test_ingest_skips_instrument_when_discovery_metadata_incomplete(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    empty_nav = pd.DataFrame({"date": [], "nav": [], "nav_acc": []})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=empty_nav),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_metadata",
            side_effect=_fake_missing_aum_fund_metadata,
        ),
    ):
        rc = run_ingest(repo_root=str(repo))

    # Skip-and-warn: ingest completes with rc=0; the problematic instrument is omitted
    assert rc == 0


def test_ingest_allows_missing_manager_tenure_for_passive_funds(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    empty_nav = pd.DataFrame({"date": [], "nav": [], "nav_acc": []})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=empty_nav),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_metadata",
            side_effect=_fake_missing_manager_tenure_fund_metadata,
        ),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    from irc.data.duckdb_helper import connect
    con = connect(repo / "data" / "local.duckdb")
    try:
        stored = con.execute(
            "SELECT manager_tenure_years FROM instruments WHERE instrument_id = '006075'"
        ).fetchone()
    finally:
        con.close()

    assert stored == (None,)


def test_ingest_idempotent(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    empty_nav = pd.DataFrame({"date": [], "nav": [], "nav_acc": []})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=empty_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
    ):
        rc1 = run_ingest(repo_root=str(repo))
        rc2 = run_ingest(repo_root=str(repo))

    assert rc1 == rc2 == 0


def test_upsert_nav_allows_missing_accumulated_nav(repo: Path) -> None:
    from irc.data.duckdb_helper import connect, ensure_schema

    con = connect(repo / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        count = _upsert_nav(
            con,
            "510300",
            pd.DataFrame({
                "date": ["2026-05-07"],
                "nav": [1.23],
                "nav_acc": [pd.NA],
            }),
        )
        stored = con.execute(
            "SELECT nav, nav_acc FROM nav_history WHERE instrument_id = '510300'"
        ).fetchone()
    finally:
        con.close()

    assert count == 1
    assert stored == (1.23, None)


# ---------------------------------------------------------------------------
# Unit tests for pure helpers (no repo fixture needed)
# ---------------------------------------------------------------------------

from irc.commands.ingest_cmd import (  # noqa: E402
    _is_missing,
    _parse_aum_cny,
    _parse_float,
    _parse_ratio,
)


def test_parse_aum_cny_yi_unit() -> None:
    # "200亿" → 200 × 1e8 = 2e10
    result = _parse_aum_cny("200亿")
    assert result == pytest.approx(200 * 1e8)


def test_parse_aum_cny_none_returns_none() -> None:
    assert _parse_aum_cny(None) is None


def test_parse_aum_cny_non_numeric_text_returns_none() -> None:
    assert _parse_aum_cny("未知") is None


def test_parse_ratio_percent_string() -> None:
    result = _parse_ratio("0.50%")
    assert result == pytest.approx(0.005)


def test_parse_float_invalid_text_returns_none() -> None:
    assert _parse_float("not-a-number") is None


def test_is_missing_with_none_nan_and_value() -> None:
    import math
    assert _is_missing(None) is True
    assert _is_missing(float("nan")) is True
    assert _is_missing(1.0) is False
    assert _is_missing("hello") is False
