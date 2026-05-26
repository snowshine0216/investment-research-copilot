"""Integration tests: `_build_rows` autobuild dispatch for fund-level + QDII kinds."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import patch

import pandas as pd


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
            rows, _positions, _q, _roles, _verdicts, _plan_hash, _snap_cache = _build_rows(
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
            rows, _positions, _q, _roles, _verdicts, _plan_hash, _snap_cache = _build_rows(
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


def test_fetch_plan_includes_fund_level_costs(tmp_path: Path) -> None:
    """FetchPlan now counts fund-level rows: 4 calls per cold/stale fund."""
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=0,
        active_fund_stale=0,
        passive_misses=0,
        passive_stale=0,
        top_n=10,
        fund_level_misses=3,  # 3 fund-level rows × 4 calls = 12
        fund_level_stale=0,
    )
    assert plan.total_calls() == 3 * 4


def test_fetch_plan_combines_active_and_fund_level_costs() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=2,   # 2 × (1+10×3+4) = 70 — +4 for fund-level NAV+announcements (item 001)
        active_fund_stale=0,
        passive_misses=0,
        passive_stale=0,
        top_n=10,
        fund_level_misses=5,    # 5 × 4 = 20
        fund_level_stale=0,
    )
    assert plan.total_calls() == 70 + 20


def test_preflight_does_not_exceed_budget_for_v1_universe() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    # V1: ~5 active funds + ~20 fund-level rows
    plan = FetchPlan(
        active_fund_misses=52,
        active_fund_stale=0,
        passive_misses=0,
        passive_stale=0,
        top_n=10,
        fund_level_misses=20,
        fund_level_stale=0,
    )
    total = plan.total_calls()
    assert total < 2000, f"total={total} would exceed default budget"


# ── F-FIX-1: QDII-bound cn_etf rows must NOT be counted in fund-level budget ──


def test_classify_fund_level_scores_excludes_qdii_bound_cn_etf(tmp_path: Path) -> None:
    """A cn_etf whose tracked_index maps to a QDII key (e.g. 513100 → nasdaq100)
    must NOT be counted in the fund-level miss/stale budget because build_snapshot
    dispatches it to the zero-cost QDII sentinel path."""
    from datetime import date
    from irc.commands.opportunity_cmd import _classify_fund_level_scores
    from irc.schemas.universe import Instrument

    qdii_etf = Instrument(
        instrument_id="513100",
        name_cn="华夏纳斯达克100ETF",
        ticker="513100",
        asset_class="cn_etf",
        market="cn_on_exchange",
        currency="cny",
        venue_required=["A股交易"],
        tracked_index="nasdaq100",  # maps to QDII US key → zero AkShare cost
    )
    instr_index = {"513100": qdii_etf}
    scores = [{"instrument_id": "513100", "asset_class": "cn_etf"}]

    misses, stale = _classify_fund_level_scores(
        scores, tmp_path, instr_index=instr_index,
        today=date(2026, 5, 23),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert misses == 0, f"QDII-bound cn_etf must not be counted as a miss; got {misses}"
    assert stale == 0, f"QDII-bound cn_etf must not be counted as stale; got {stale}"


def test_classify_fund_level_scores_counts_non_qdii_cn_etf(tmp_path: Path) -> None:
    """A cn_etf whose tracked_index maps to a broad domestic index IS fund-level
    and must be counted (no cached file → counted as a miss)."""
    from datetime import date
    from irc.commands.opportunity_cmd import _classify_fund_level_scores
    from irc.schemas.universe import Instrument

    domestic_etf = Instrument(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        ticker="510300",
        asset_class="cn_etf",
        market="cn_on_exchange",
        currency="cny",
        venue_required=["A股交易"],
        tracked_index="csi300",  # broad_index — does dispatch to fund-level engine
    )
    instr_index = {"510300": domestic_etf}
    scores = [{"instrument_id": "510300", "asset_class": "cn_etf"}]

    misses, stale = _classify_fund_level_scores(
        scores, tmp_path, instr_index=instr_index,
        today=date(2026, 5, 23),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert misses == 1, f"domestic cn_etf with no cache should be a miss; got {misses}"
    assert stale == 0


# ── F-FIX-3: _resolve_fund_level_snapshot must raise RuntimeError (not AssertionError) ──


def test_resolve_fund_level_snapshot_raises_runtime_error_on_wrong_type(tmp_path: Path) -> None:
    """If build_snapshot returns the wrong type (dispatch bug), _resolve_fund_level_snapshot
    must raise RuntimeError, not AssertionError (which is silently swallowed under python -O)."""
    import pytest
    from datetime import date
    from unittest.mock import patch
    from irc.commands.opportunity_cmd import _resolve_fund_level_snapshot
    from irc.fundamentals.types import LookthroughTarget, ConstituentSnapshot

    # A gold target should normally return FundLevelSnapshot, but we force a
    # wrong return to simulate a dispatch bug.
    wrong_snap = ConstituentSnapshot(
        lookthrough_target="wrong",
        as_of_iso="2026-05-23",
        constituents=(),
        filings=(),
        broker_reports=(),
    )
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch("irc.commands.opportunity_cmd.build_snapshot", return_value=wrong_snap):
        with pytest.raises(RuntimeError, match="build_snapshot returned"):
            _resolve_fund_level_snapshot(
                target, tmp_path,
                rebuild=False,
                today=date(2026, 5, 23),
            )
