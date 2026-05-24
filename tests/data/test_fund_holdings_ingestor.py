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
