"""Integration tests: `_build_rows` autobuild dispatch for fund-level + QDII kinds."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


# These fixtures stage minimal `_build_rows` inputs. They use the seam
# `irc.fundamentals.akshare_fundamentals._ak_call` for adapter mocking.


def _nav_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "净值日期": [_dt.date(2026, 3, 15)],
        "单位净值": [4.5678],
        "日增长率": ["0.39"],
    })


def _ann_frame_with(report_id: str) -> pd.DataFrame:
    return pd.DataFrame({
        "基金代码": ["X"],
        "公告标题": [f"title-{report_id}"],
        "基金名称": ["X"],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": [report_id],
    })


def _make_universal_side_effect():
    """side_effect that returns NAV + 1 announcement per topic for any symbol."""

    def _side(fn_name, **kw):
        if fn_name == "fund_open_fund_info_em":
            return _nav_frame()
        if fn_name == "fund_announcement_dividend_em":
            return _ann_frame_with("ANDIV")
        if fn_name == "fund_announcement_report_em":
            return _ann_frame_with("ANREP")
        if fn_name == "fund_announcement_personnel_em":
            return _ann_frame_with("ANPER")
        # Fall through: legacy snapshot paths that may still be called.
        return pd.DataFrame()
    return _side


def test_build_snapshot_gold_row_emits_fund_level_evidence(tmp_path: Path) -> None:
    """End-to-end through build_snapshot for a gold target."""
    from irc.fundamentals.snapshot import build_snapshot
    from irc.fundamentals.types import FundLevelSnapshot, LookthroughTarget

    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_universal_side_effect(),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    assert len(data) == 1
    assert len(info) >= 1
    for e in snap.evidence:
        assert e.scope == "instrument"
        assert e.owner_instrument_id == "518880"


def test_build_snapshot_qdii_row_emits_sentinel_zero_calls() -> None:
    from irc.fundamentals.snapshot import build_snapshot
    from irc.fundamentals.types import FundLevelSnapshot, LookthroughTarget

    target = LookthroughTarget(
        kind="qdii_global", key="global_equity", display_cn="qdii",
        provider_symbol="",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
    ) as mocked:
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.evidence_gaps == ("qdii_information_unavailable",)
    assert mocked.call_count == 0


def test_build_rows_routes_fund_level_evidence_into_opportunity_row(tmp_path: Path) -> None:
    """`_build_rows` integration: a gold row produces an OpportunityRow whose
    `thesis_evidence` carries the FundLevelSnapshot's evidence tuple."""
    from irc.commands.opportunity_cmd import _build_rows
    from irc.opportunity.types import OpportunityInput  # noqa: F401
    import duckdb

    # Minimal score row for gold.
    scores = [{
        "instrument_id": "518880", "asset_class": "gold",
        "role": "small_watch",
    }]
    instr_index: dict = {}
    holdings: dict = {}
    asset_class_targets: dict = {}
    theme_thesis = None
    theme_reports: dict = {}
    portfolio_total_cny = 0.0
    available_venues: set = set()

    con = duckdb.connect(":memory:")
    from irc.data.duckdb_helper import ensure_schema
    ensure_schema(con)

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_universal_side_effect(),
    ):
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            rows, _positions, _q, _roles = _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    assert len(rows) == 1
    r = rows[0]
    assert r.instrument_id == "518880"
    # Fund-level evidence is forwarded into thesis_evidence.
    assert len(r.thesis_evidence) >= 2  # at least 1 data + 1 info
    kinds = {e.citation_kind for e in r.thesis_evidence}
    assert "data" in kinds
    assert "information" in kinds
    for e in r.thesis_evidence:
        assert e.owner_instrument_id == "518880"


def test_build_rows_qdii_row_carries_sentinel_gap(tmp_path: Path) -> None:
    from irc.commands.opportunity_cmd import _build_rows
    import duckdb

    scores = [{
        "instrument_id": "513500", "asset_class": "us_etf",
        "role": "small_watch",
    }]
    # Stub Instrument with us_etf class — populated via instr_index.
    from irc.schemas.universe import Instrument
    instr = Instrument(
        instrument_id="513500", name_cn="博时标普500ETF",
        ticker="513500",
        asset_class="us_etf", market="cn_on_exchange",
        currency="cny",
        venue_required=["A股交易"],
        tracked_index="sp500",
    )
    instr_index = {"513500": instr}
    holdings: dict = {}
    asset_class_targets: dict = {}
    theme_thesis = None
    theme_reports: dict = {}
    portfolio_total_cny = 0.0
    available_venues: set = {"A股交易"}

    con = duckdb.connect(":memory:")
    from irc.data.duckdb_helper import ensure_schema
    ensure_schema(con)

    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
    ) as mocked:
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            rows, _positions, _q, _roles = _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    assert len(rows) == 1
    r = rows[0]
    assert "qdii_information_unavailable" in r.evidence_gaps
    # No AkShare call for QDII rows.
    assert mocked.call_count == 0
