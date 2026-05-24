"""Item 010 D B1 — fund_holdings ingestor unit + integration tests.

Real on-disk DuckDB via tmp_path; real ActiveFundSnapshot JSON cache files
written via item 003's write_active_fund_cache. No mocks, no live network.
"""
from __future__ import annotations

import pytest


def test_holding_row_accepts_valid_fields() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    row = HoldingRow(
        instrument_id="005827",
        report_date="2024-03-31",
        holding_ticker="600519",
        holding_name="贵州茅台",
        weight_pct=8.5,
        source="active_fund_snapshot",
    )
    assert row.instrument_id == "005827"
    assert row.weight_pct == 8.5


def test_holding_row_rejects_empty_instrument_id() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="instrument_id"):
        HoldingRow(
            instrument_id="",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=8.5,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_malformed_report_date() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="report_date"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024/03/31",  # wrong delimiter
            holding_ticker="600519",
            holding_name="X",
            weight_pct=8.5,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_empty_holding_ticker() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="holding_ticker"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="",
            holding_name="X",
            weight_pct=8.5,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_negative_weight() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="weight_pct"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=-0.01,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_weight_over_100() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="weight_pct"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=100.01,
            source="active_fund_snapshot",
        )


def test_holding_row_accepts_boundary_weights() -> None:
    """0.0 and 100.0 are both inclusive."""
    from irc.data.fund_holdings_ingestor import HoldingRow
    HoldingRow(
        instrument_id="x", report_date="2024-03-31",
        holding_ticker="y", holding_name="z",
        weight_pct=0.0, source="active_fund_snapshot",
    )
    HoldingRow(
        instrument_id="x", report_date="2024-03-31",
        holding_ticker="y", holding_name="z",
        weight_pct=100.0, source="akshare_cn_etf",
    )


def test_holding_row_rejects_unknown_source() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="source"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=8.5,
            source="manual_paste",
        )


def test_ingest_outcome_constructs() -> None:
    from irc.data.fund_holdings_ingestor import IngestOutcome
    out = IngestOutcome(
        instrument_id="005827", status="wrote",
        report_date="2024-03-31", rows_written=10, detail="",
    )
    assert out.status == "wrote"
    assert out.rows_written == 10


def test_module_exports_public_surface() -> None:
    """AC2 — module exports all seven public names."""
    import irc.data.fund_holdings_ingestor as m
    for name in (
        "HoldingRow",
        "IngestOutcome",
        "collect_holding_rows",
        "upsert_holdings",
        "is_stale",
        "ingest_one",
        "ingest_many",
    ):
        assert hasattr(m, name), f"missing public name: {name}"


# ── Task 2: is_stale ─────────────────────────────────────────────────────────

from datetime import date, timedelta
from pathlib import Path


def _connect_with_schema(tmp_path: Path):
    """Open a fresh DuckDB at tmp_path/local.duckdb with schema applied."""
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)
    return con


def _insert_holding(con, *, iid, report_date, ticker="600519",
                    name="贵州茅台", weight=8.5, ingested_at="2026-05-24 00:00:00",
                    source="test", raw_ref="ref:1") -> None:
    """Direct positional insert for fixture seeding — bypasses the ingestor."""
    con.execute(
        "INSERT INTO fund_holdings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [iid, report_date, ticker, name, weight, ingested_at, source, raw_ref],
    )


def test_is_stale_returns_true_when_no_rows(tmp_path: Path) -> None:
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        assert is_stale(con, "005827", today_iso="2026-05-24") is True
    finally:
        con.close()


def test_is_stale_returns_false_within_threshold(tmp_path: Path) -> None:
    """29 days old is fresh (boundary check at threshold_days=30)."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        twenty_nine_days_ago = today - timedelta(days=29)
        _insert_holding(con, iid="005827", report_date=twenty_nine_days_ago)
        assert is_stale(con, "005827", today_iso=today.isoformat()) is False
    finally:
        con.close()


def test_is_stale_returns_true_past_threshold(tmp_path: Path) -> None:
    """31 days old is stale."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        thirty_one_days_ago = today - timedelta(days=31)
        _insert_holding(con, iid="005827", report_date=thirty_one_days_ago)
        assert is_stale(con, "005827", today_iso=today.isoformat()) is True
    finally:
        con.close()


def test_is_stale_boundary_exactly_at_threshold(tmp_path: Path) -> None:
    """Exactly 30 days old is NOT stale (gate is `> threshold_days`)."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        thirty_days_ago = today - timedelta(days=30)
        _insert_holding(con, iid="005827", report_date=thirty_days_ago)
        assert is_stale(con, "005827", today_iso=today.isoformat()) is False
    finally:
        con.close()


def test_is_stale_threshold_override(tmp_path: Path) -> None:
    """threshold_days=7 swaps the boundary at 8 days old."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        _insert_holding(con, iid="A", report_date=today - timedelta(days=7))
        _insert_holding(con, iid="B", report_date=today - timedelta(days=8))
        assert is_stale(con, "A", today_iso=today.isoformat(), threshold_days=7) is False
        assert is_stale(con, "B", today_iso=today.isoformat(), threshold_days=7) is True
    finally:
        con.close()


def test_is_stale_uses_max_report_date_when_multiple_quarters(tmp_path: Path) -> None:
    """Latest report_date wins for the freshness check."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        _insert_holding(con, iid="005827", report_date=today - timedelta(days=200),
                        ticker="OLD")
        _insert_holding(con, iid="005827", report_date=today - timedelta(days=10),
                        ticker="NEW")
        assert is_stale(con, "005827", today_iso=today.isoformat()) is False
    finally:
        con.close()
