from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from irc.commands.init_cmd import run_init
from irc.commands.ingest_cmd import _china_today, _upsert_nav, run_ingest


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    return tmp_path


@pytest.fixture(autouse=True)
def _bypass_preflight(monkeypatch):
    """Prevent the network preflight from running in unit tests.

    Tests that specifically test preflight behaviour override _preflight_call
    themselves — this fixture is a safety-net no-op for all others.
    """
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", lambda: None)


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
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
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
    fake_nav = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34]})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
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
    fake_nav = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34]})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
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
    fake_nav = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34]})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_metadata",
            side_effect=_fake_missing_aum_fund_metadata,
        ),
        patch(
            "irc.commands.ingest_cmd.fetch_etf_metadata_em",
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
    fake_nav = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34]})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_metadata",
            side_effect=_fake_missing_manager_tenure_fund_metadata,
        ),
        patch(
            "irc.commands.ingest_cmd.fetch_etf_metadata_em",
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


def _make_instrument(asset_class: str, market: str = "cn_off_exchange"):
    """Tiny stand-in for an Instrument — only the manager-tenure predicate
    fields are needed. Avoids pulling in the full pydantic schema."""
    from types import SimpleNamespace
    return SimpleNamespace(asset_class=asset_class, market=market, ticker="000000")


def test_active_fund_tenure_fallback_uses_inception_years_when_tenure_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XueQiu's basic-info endpoint doesn't expose manager tenure for active
    funds. Use fund inception years as a temporary proxy so well-known managers
    (张坤/谢治宇/etc.) at long-running funds aren't silently dropped from the
    universe while the accurate manager-tenure feed is still deferred."""
    from irc.commands import ingest_cmd

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 9, tzinfo=tz)

    monkeypatch.setattr(ingest_cmd, "datetime", FrozenDateTime)
    instrument = _make_instrument("cn_equity_fund")
    metadata = {
        "inception_date": "2018-03-26",
        "expense_ratio": 0.015, "aum": 2e10,
        "manager_tenure_years": None,
    }
    out = ingest_cmd._apply_active_fund_tenure_fallback(instrument, metadata)
    expected = round((date(2026, 5, 9) - date(2018, 3, 26)).days / 365.25, 2)
    assert out["manager_tenure_years"] == expected
    assert out["manager_tenure_years"] >= 2.0  # passes quality_filter min


def test_active_fund_tenure_fallback_keeps_real_tenure_when_supplied() -> None:
    from irc.commands.ingest_cmd import _apply_active_fund_tenure_fallback
    instrument = _make_instrument("cn_equity_fund")
    metadata = {
        "inception_date": "2010-01-01",
        "expense_ratio": 0.012, "aum": 5e9,
        "manager_tenure_years": 3.5,
    }
    out = _apply_active_fund_tenure_fallback(instrument, metadata)
    assert out["manager_tenure_years"] == 3.5  # NOT 15+ from inception


def test_active_fund_tenure_fallback_skipped_for_passive_etfs() -> None:
    """Passive ETFs (cn_etf, on-exchange) don't need tenure — manager doesn't
    drive returns, they just rebalance to track the index. Fallback must not
    apply, otherwise it would muddy the metadata downstream."""
    from irc.commands.ingest_cmd import _apply_active_fund_tenure_fallback
    instrument = _make_instrument("cn_etf", market="cn_on_exchange")
    metadata = {
        "inception_date": "2018-03-26", "expense_ratio": 0.005,
        "aum": 1e10, "manager_tenure_years": None,
    }
    out = _apply_active_fund_tenure_fallback(instrument, metadata)
    assert out["manager_tenure_years"] is None  # unchanged


def test_active_fund_tenure_fallback_no_op_when_inception_also_missing() -> None:
    from irc.commands.ingest_cmd import _apply_active_fund_tenure_fallback
    instrument = _make_instrument("cn_equity_fund")
    metadata = {"inception_date": None, "expense_ratio": 0.012,
                "aum": 1e9, "manager_tenure_years": None}
    out = _apply_active_fund_tenure_fallback(instrument, metadata)
    assert out["manager_tenure_years"] is None


def test_active_fund_tenure_fallback_no_op_when_inception_invalid() -> None:
    from irc.commands.ingest_cmd import _apply_active_fund_tenure_fallback
    instrument = _make_instrument("cn_equity_fund")
    metadata = {
        "inception_date": "not-a-date", "expense_ratio": 0.012,
        "aum": 1e9, "manager_tenure_years": None,
    }
    out = _apply_active_fund_tenure_fallback(instrument, metadata)
    assert out["manager_tenure_years"] is None


def test_run_ingest_persists_active_fund_tenure_fallback(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_metadata",
            side_effect=_fake_missing_manager_tenure_fund_metadata,
        ),
        patch(
            "irc.commands.ingest_cmd.fetch_etf_metadata_em",
            side_effect=_fake_missing_manager_tenure_fund_metadata,
        ),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    from irc.data.duckdb_helper import connect
    con = connect(repo / "data" / "local.duckdb")
    try:
        stored = con.execute(
            "SELECT manager_tenure_years FROM instruments WHERE instrument_id = '161005'"
        ).fetchone()
    finally:
        con.close()

    assert stored is not None
    assert stored[0] >= 2.0


def test_run_ingest_skips_active_fund_tenure_proxy_when_env_flag_off(repo: Path) -> None:
    (repo / ".env").write_text("ACTIVE_FUND_TENURE_PROXY_ENABLED=false\n", encoding="utf-8")
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_metadata",
            side_effect=_fake_missing_manager_tenure_fund_metadata,
        ),
        patch(
            "irc.commands.ingest_cmd.fetch_etf_metadata_em",
            side_effect=_fake_missing_manager_tenure_fund_metadata,
        ),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    from irc.data.duckdb_helper import connect
    con = connect(repo / "data" / "local.duckdb")
    try:
        stored = con.execute(
            "SELECT manager_tenure_years FROM instruments WHERE instrument_id = '161005'"
        ).fetchone()
    finally:
        con.close()

    assert stored == (None,)


def test_ingest_skips_failed_price_ticker_and_continues(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When EastMoney drops a single ticker (RemoteDisconnected) and the
    yfinance fallback is rate-limited, the pipeline must log and skip that
    instrument, not crash all 58 others."""
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    seen: list[str] = []

    def flaky_prices(ticker: str, start: str, end: str, **_kwargs) -> pd.DataFrame:
        seen.append(ticker)
        if ticker == "513500":
            raise ConnectionError("Connection aborted: RemoteDisconnected")
        return fake_prices

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", side_effect=flaky_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    assert "513500" in seen, "expected 513500 to be attempted"
    assert any(t != "513500" for t in seen), "other tickers must still be processed"
    output = capsys.readouterr().out
    assert "skipped due to upstream errors" in output
    assert "prices: ['513500']" in output
    assert "nav: none" in output


def test_ingest_treats_empty_price_history_as_skipped_ticker(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_prices = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})

    def sparse_prices(ticker: str, start: str, end: str, **_kwargs) -> pd.DataFrame:
        if ticker == "513500":
            return empty_prices
        return fake_prices

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", side_effect=sparse_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    output = capsys.readouterr().out
    assert "skipped due to upstream errors" in output
    assert "prices: ['513500']" in output
    assert "nav: none" in output


def test_ingest_returns_nonzero_when_all_price_tickers_fail(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", side_effect=ConnectionError("down")),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 1
    output = capsys.readouterr().out
    assert "ERROR: ingest failed" in output
    assert not (repo / "data" / "_manifest" / "openbb.json").exists()


def test_ingest_skips_malformed_price_rows_and_continues(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    bad_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": ["--"], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})

    def malformed_once(ticker: str, start: str, end: str, **_kwargs) -> pd.DataFrame:
        if ticker == "510300":
            return bad_prices
        return fake_prices

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", side_effect=malformed_once),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    output = capsys.readouterr().out
    assert "prices: ['510300']" in output


def test_ingest_returns_nonzero_when_price_persistence_fails(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    failed = False

    def flaky_upsert(_con, _instrument_id: str, df: pd.DataFrame) -> int:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("duckdb down")
        return len(df)

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd._upsert_prices", side_effect=flaky_upsert),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 1
    assert not (repo / "data" / "_manifest" / "openbb.json").exists()


def test_ingest_records_cn_exchange_price_provenance_as_akshare(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    from irc.data.duckdb_helper import connect
    con = connect(repo / "data" / "local.duckdb")
    try:
        stored = con.execute(
            "SELECT _source, _raw_ref FROM prices WHERE instrument_id = '510300' LIMIT 1"
        ).fetchone()
    finally:
        con.close()

    assert stored == ("akshare", "akshare:prices:510300:2026-05-06")
    openbb = json.loads((repo / "data" / "_manifest" / "openbb.json").read_text())
    akshare = json.loads((repo / "data" / "_manifest" / "akshare.json").read_text())
    assert openbb["record_counts"]["prices"] == 0
    assert akshare["record_counts"]["prices"] > 0


def test_ingest_skips_malformed_nav_rows_and_continues(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    bad_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": ["--"], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})

    def malformed_once(fund_code: str) -> pd.DataFrame:
        if fund_code == "005827":
            return bad_nav
        return fake_nav

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", side_effect=malformed_once),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    output = capsys.readouterr().out
    assert "nav: ['005827']" in output


def test_ingest_returns_nonzero_when_nav_persistence_fails(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    failed = False

    def flaky_upsert(_con, _instrument_id: str, df: pd.DataFrame) -> int:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("duckdb down")
        return len(df)

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd._upsert_nav", side_effect=flaky_upsert),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 1
    assert not (repo / "data" / "_manifest" / "akshare.json").exists()


def test_ingest_skips_eastmoney_after_first_exhausted_retry_chain(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    skip_flags: list[bool] = []

    def tracked_prices(
        ticker: str,
        start: str,
        end: str,
        *,
        skip_cn_eastmoney: bool = False,
        on_cn_eastmoney_exhausted=None,
    ) -> pd.DataFrame:
        skip_flags.append(skip_cn_eastmoney)
        if len(skip_flags) == 1 and on_cn_eastmoney_exhausted is not None:
            on_cn_eastmoney_exhausted()
        return fake_prices

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", side_effect=tracked_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    assert skip_flags[0] is False
    assert any(skip_flags[1:])


def test_ingest_skips_failed_nav_ticker_and_continues(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A single NAV fetch failure (XueQiu auth blip, network drop) must not
    halt the whole pipeline — log and skip, like the price path."""
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    nav_calls: list[str] = []

    def flaky_nav(fund_code: str) -> pd.DataFrame:
        nav_calls.append(fund_code)
        if fund_code == "005827":
            raise RuntimeError("XueQiu auth blip")
        return fake_nav

    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", side_effect=flaky_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    assert "005827" in nav_calls
    assert any(t != "005827" for t in nav_calls), "other NAV tickers must still be fetched"
    output = capsys.readouterr().out
    assert "skipped due to upstream errors" in output
    assert "prices: none" in output
    assert "nav: ['005827']" in output


def test_ingest_returns_nonzero_when_all_nav_tickers_empty(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 1
    output = capsys.readouterr().out
    assert "ERROR: ingest failed: no successful nav ingest" in output
    assert not (repo / "data" / "_manifest" / "akshare.json").exists()


def test_ingest_continues_when_macro_fetch_fails_with_missing_credentials(repo: Path) -> None:
    """Macro provider (FRED/Intrinio) needs an API key. When unavailable, ingest
    must skip with a warning and let downstream defaults kick in — not halt."""
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch(
            "irc.commands.ingest_cmd.fetch_macro_series",
            side_effect=RuntimeError("Provider fallback failed. fred missing credentials"),
        ),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))
    assert rc == 0


def test_ingest_routes_off_exchange_funds_to_nav_not_yfinance(repo: Path) -> None:
    """Off-exchange active funds have no yfinance ticker — they must go through
    fetch_fund_nav_history (akshare NAV path), not fetch_etf_price_history."""
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34],
    })
    with (
        patch("irc.commands.ingest_cmd._preflight_call"),
        patch(
            "irc.commands.ingest_cmd.fetch_etf_price_history",
            return_value=fake_prices,
        ) as mock_yf,
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch(
            "irc.commands.ingest_cmd.fetch_fund_nav_history",
            return_value=fake_nav,
        ) as mock_nav,
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    yf_tickers = {c.kwargs.get("ticker", c.args[0] if c.args else None) for c in mock_yf.call_args_list}
    nav_tickers = {c.args[0] for c in mock_nav.call_args_list}
    assert "005827" not in yf_tickers, f"005827 should not be sent to yfinance; got {yf_tickers}"
    assert "005827" in nav_tickers, f"005827 should go through NAV path; got {nav_tickers}"
    assert "006075" in nav_tickers, f"QDII feeder 006075 should go through NAV path; got {nav_tickers}"
    assert [c.args[0] for c in mock_nav.call_args_list].count("005827") == 1
    assert "510300" not in nav_tickers, f"510300 already has price history; got NAV calls {nav_tickers}"
    assert "CMB_AU" not in yf_tickers and "CMB_AU" not in nav_tickers, (
        "cmb_paper_gold (ticker CMB_AU) has no public source — must be skipped"
    )


def test_ingest_idempotent(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    fake_nav = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.23], "nav_acc": [2.34]})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_fake_fund_metadata),
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


# ---------------------------------------------------------------------------
# _ingest_preflight tests
# ---------------------------------------------------------------------------
from irc.commands.ingest_cmd import _ingest_preflight
from irc.pipeline_halt import HaltReason


def test_preflight_returns_none_on_success(monkeypatch):
    monkeypatch.setattr(
        "irc.commands.ingest_cmd._preflight_call",
        lambda: None,
    )
    assert _ingest_preflight() is None


def test_preflight_returns_unreachable_on_transient_error(monkeypatch):
    def boom() -> None:
        raise ConnectionResetError("[Errno 54] Connection reset by peer")
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)
    reason = _ingest_preflight()
    assert isinstance(reason, HaltReason)
    assert reason.kind == "akshare_unreachable"
    assert reason.stage == "ingest"
    assert "Connection reset" in (reason.first_error or "")


def test_preflight_returns_error_on_non_transient_exception(monkeypatch):
    def boom() -> None:
        raise ValueError("unexpected schema: missing column 'nav'")
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)
    reason = _ingest_preflight()
    assert isinstance(reason, HaltReason)
    assert reason.kind == "akshare_error"
    assert "unexpected schema" in (reason.first_error or "")


def test_preflight_returns_unexpected_on_baseexception(monkeypatch):
    def boom() -> None:
        raise KeyboardInterrupt()
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)
    # KeyboardInterrupt should NOT be caught — it must propagate.
    import pytest
    with pytest.raises(KeyboardInterrupt):
        _ingest_preflight()


# ---------------------------------------------------------------------------
# run_ingest preflight wiring + stale-guard tests
# ---------------------------------------------------------------------------

def test_run_ingest_preflight_failure_writes_sidecar(repo: Path, monkeypatch):
    def boom() -> None:
        raise ConnectionResetError("[Errno 54] Connection reset by peer")
    monkeypatch.setattr("irc.commands.ingest_cmd._preflight_call", boom)

    rc = run_ingest(str(repo))

    assert rc == 1
    sidecar = repo / "outputs" / _china_today() / ".halt_reason.json"
    assert sidecar.exists()
    reason = HaltReason.read_sidecar(sidecar)
    assert reason is not None
    assert reason.kind == "akshare_unreachable"
    assert reason.stage == "ingest"


def test_run_ingest_preflight_clears_stale_sidecar(repo: Path, monkeypatch):
    today = _china_today()
    out_dir = repo / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = out_dir / ".halt_reason.json"
    stale.write_text('{"kind":"old","stage":"ingest","detail":"old run"}',
                     encoding="utf-8")

    # Successful preflight, then short-circuit the rest by raising in a place
    # that returns rc=1 cleanly.
    monkeypatch.setattr(
        "irc.commands.ingest_cmd.load_repo_configs",
        lambda root: (_ for _ in ()).throw(RuntimeError("stop early")),
    )
    import pytest
    with pytest.raises(RuntimeError):
        run_ingest(str(repo))

    assert not stale.exists(), "stale sidecar must be deleted on entry"


# ---------------------------------------------------------------------------
# run_ingest 0-success sidecar test
# ---------------------------------------------------------------------------

def test_run_ingest_zero_success_writes_sidecar(repo: Path, monkeypatch):
    def fail_price(*_a, **_kw):
        raise ConnectionResetError("simulated outage (price)")
    def fail_nav(*_a, **_kw):
        raise ConnectionResetError("simulated outage (nav)")

    monkeypatch.setattr("irc.commands.ingest_cmd.fetch_etf_price_history", fail_price)
    monkeypatch.setattr("irc.commands.ingest_cmd.fetch_fund_nav_history", fail_nav)

    rc = run_ingest(str(repo))

    assert rc == 1
    sidecar = repo / "outputs" / _china_today() / ".halt_reason.json"
    assert sidecar.exists()
    reason = HaltReason.read_sidecar(sidecar)
    assert reason is not None
    assert reason.kind == "akshare_empty"
    assert reason.stats.get("price_attempts", 0) > 0
    assert reason.stats.get("price_successes", -1) == 0
    assert reason.first_error  # non-empty
    assert "ConnectionResetError" in (reason.first_error or ""), "first_error must be exception text, not instrument ID"
