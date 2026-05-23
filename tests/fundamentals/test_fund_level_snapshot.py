"""Unit tests for fund-level snapshot builders (item 005 F3/F4)."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.snapshot import (
    _build_qdii_sentinel_snapshot,
    build_snapshot,
)
from irc.fundamentals.types import (
    FundLevelSnapshot,
    LookthroughTarget,
)


@pytest.mark.parametrize(
    "kind", ["qdii_us", "qdii_hk", "qdii_global"],
)
def test_qdii_sentinel_zero_fetch(kind: str) -> None:
    """No AkShare call should fire for any QDII kind."""
    target = LookthroughTarget(
        kind=kind, key=f"key_{kind}", display_cn="x",
        provider_symbol="ignored",
    )
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        snap = _build_qdii_sentinel_snapshot(target)
    assert mocked.call_count == 0
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.nav_report is None
    assert snap.announcements == ()
    assert snap.evidence == ()
    assert snap.evidence_gaps == ("qdii_information_unavailable",)


def test_qdii_sentinel_fund_id_fallback_to_key() -> None:
    target = LookthroughTarget(
        kind="qdii_us", key="qdii_us:sp500", display_cn="标普500",
        provider_symbol="",
    )
    snap = _build_qdii_sentinel_snapshot(target)
    assert snap.fund_id == "qdii_us:sp500"


def test_qdii_sentinel_prefers_provider_symbol_when_present() -> None:
    target = LookthroughTarget(
        kind="qdii_us", key="qdii_us:sp500", display_cn="标普500",
        provider_symbol="513500",
    )
    snap = _build_qdii_sentinel_snapshot(target)
    assert snap.fund_id == "513500"


def test_build_snapshot_routes_all_qdii_kinds_to_sentinel() -> None:
    for kind in ("qdii_us", "qdii_hk", "qdii_global"):
        target = LookthroughTarget(kind=kind, key="x", display_cn="x")
        with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
            snap = build_snapshot(target)
        assert isinstance(snap, FundLevelSnapshot)
        assert snap.evidence_gaps == ("qdii_information_unavailable",)
        assert mocked.call_count == 0


# ── Task 9: _build_fund_level_snapshot tests ─────────────────────────────────

import datetime as _dt

from irc.fundamentals.snapshot import _build_fund_level_snapshot


def _nav_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "净值日期": [
            _dt.date(2026, 3, 13),
            _dt.date(2026, 3, 14),
            _dt.date(2026, 3, 15),
        ],
        "单位净值": [4.5400, 4.5500, 4.5678],
        "日增长率": ["0.12", "0.22", "0.39"],
    })


def _ann_frames() -> dict[str, pd.DataFrame]:
    dividend = pd.DataFrame({
        "基金代码": ["518880"] * 2,
        "公告标题": ["分红1", "分红2"],
        "基金名称": ["华安黄金易ETF"] * 2,
        "公告日期": [_dt.date(2024, 1, 1), _dt.date(2024, 2, 1)],
        "报告ID": ["AN1", "AN2"],
    })
    report = pd.DataFrame({
        "基金代码": ["518880"] * 2,
        "公告标题": ["报告1", "报告2"],
        "基金名称": ["华安黄金易ETF"] * 2,
        "公告日期": [_dt.date(2024, 3, 1), _dt.date(2024, 4, 1)],
        "报告ID": ["AN3", "AN4"],
    })
    personnel = pd.DataFrame({
        "基金代码": ["518880"] * 2,
        "公告标题": ["人事1", "人事2"],
        "基金名称": ["华安黄金易ETF"] * 2,
        "公告日期": [_dt.date(2024, 5, 1), _dt.date(2024, 6, 1)],
        "报告ID": ["AN5", "AN6"],
    })
    return {
        "fund_open_fund_info_em": _nav_frame(),
        "fund_announcement_dividend_em": dividend,
        "fund_announcement_report_em": report,
        "fund_announcement_personnel_em": personnel,
    }


def _make_side_effect(frames: dict[str, pd.DataFrame]):
    def _side(fn_name, **kw):
        return frames[fn_name]
    return _side


def test_build_fund_level_snapshot_emits_one_data_leg_and_announcements_info_leg() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = _build_fund_level_snapshot(target)
    assert snap.fund_id == "518880"
    assert snap.nav_report is not None
    assert snap.nav_report.latest_nav == 4.5678
    assert len(snap.announcements) == 6
    # Evidence: exactly one data-leg (NAV) + at most 3 info-leg (capped).
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    assert len(data) == 1
    assert data[0].type == "snapshot"
    assert data[0].scope == "instrument"
    assert data[0].owner_instrument_id == "518880"
    assert data[0].parent_fund_id is None
    assert data[0].constituent_key is None
    assert data[0].url == ""
    assert "NAV=4.5678 @ 2026-03-15" in data[0].summary
    assert data[0].holding_weight_pct is None
    assert len(info) == 3  # capped at 3
    for e in info:
        assert e.scope == "instrument"
        assert e.owner_instrument_id == "518880"
        assert e.parent_fund_id is None
        assert e.constituent_key is None
        assert e.url == ""
        assert e.summary.startswith("[AN")  # [report_id] prefix
        assert e.type == "news"
        assert e.source.startswith("fund_announcement_") and e.source.endswith("_em")
    assert snap.source_report_quarter == "2026Q1"
    assert snap.evidence_gaps == ()
    assert snap.fund_level_failure_reasons == ()


def test_build_fund_level_snapshot_nav_only_stamps_announcement_gap() -> None:
    """NAV present but announcements all-empty → fund_announcements_unavailable."""
    target = LookthroughTarget(
        kind="bond", key="cn_bond", display_cn="中国债券",
        provider_symbol="000001",
    )
    frames = {
        "fund_open_fund_info_em": _nav_frame(),
        "fund_announcement_dividend_em": pd.DataFrame(),
        "fund_announcement_report_em": pd.DataFrame(),
        "fund_announcement_personnel_em": pd.DataFrame(),
    }
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(frames),
    ):
        snap = _build_fund_level_snapshot(target)
    assert snap.nav_report is not None
    assert snap.announcements == ()
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    assert info == []
    assert "fund_announcements_unavailable" in snap.evidence_gaps


def test_build_fund_level_snapshot_nav_failure_stamps_nav_gap() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    frames = {
        "fund_open_fund_info_em": pd.DataFrame(),
        "fund_announcement_dividend_em": pd.DataFrame({
            "基金代码": ["518880"], "公告标题": ["x"], "基金名称": ["X"],
            "公告日期": [_dt.date(2024, 1, 1)], "报告ID": ["AN1"],
        }),
        "fund_announcement_report_em": pd.DataFrame(),
        "fund_announcement_personnel_em": pd.DataFrame(),
    }
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(frames),
    ):
        snap = _build_fund_level_snapshot(target)
    assert snap.nav_report is None
    assert len(snap.announcements) == 1
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    assert data == []
    assert "fund_nav_unavailable" in snap.evidence_gaps


def test_build_fund_level_snapshot_announcement_info_summary_carries_report_id() -> None:
    """ADR 0001 §2: empty URL + summary "[{report_id}] {title}" makes citation_ids
    deterministic and unique."""
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = _build_fund_level_snapshot(target)
    info = [e for e in snap.evidence if e.citation_kind == "information"]
    for e in info:
        # The bracketed report_id must appear in summary[:64] for ADR 0001 fallback.
        assert e.summary[:64].startswith("[AN")
        # Distinct entries → distinct citation_ids.
    ids = {e.citation_id for e in info}
    assert len(ids) == len(info)


def test_build_fund_level_snapshot_data_evidence_no_holding_weight() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = _build_fund_level_snapshot(target)
    data = [e for e in snap.evidence if e.citation_kind == "data"]
    for e in data:
        assert e.holding_weight_pct is None


# ── Task 10: build_snapshot dispatch tests ───────────────────────────────────

def test_build_snapshot_routes_gold_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金",
        provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)
    assert snap.fund_id == "518880"


def test_build_snapshot_routes_bond_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="bond", key="cn_bond", display_cn="中国债券",
        provider_symbol="000001",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)


def test_build_snapshot_routes_broad_index_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="broad_index", key="csi300", display_cn="沪深300",
        provider_symbol="510300",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)


def test_build_snapshot_routes_sector_theme_with_provider_symbol_to_fund_level() -> None:
    target = LookthroughTarget(
        kind="sector_theme", key="semiconductor", display_cn="半导体",
        provider_symbol="512480",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_make_side_effect(_ann_frames()),
    ):
        snap = build_snapshot(target)
    assert isinstance(snap, FundLevelSnapshot)


def test_build_snapshot_routes_broad_index_without_provider_symbol_to_legacy() -> None:
    """Empty provider_symbol → falls through to legacy display-only path."""
    from irc.fundamentals.types import ConstituentSnapshot
    target = LookthroughTarget(
        kind="broad_index", key="csi300", display_cn="沪深300",
        provider_symbol="",
    )
    # Legacy path tries _build_cn_snapshot which calls fetch_cn_index_constituents.
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame()  # legacy gets empty too
        snap = build_snapshot(target)
    # The legacy path returns ConstituentSnapshot, not FundLevelSnapshot.
    assert isinstance(snap, ConstituentSnapshot)


def test_build_snapshot_active_fund_path_unchanged() -> None:
    """Item 003 regression — active_fund kind still routes to _build_active_fund_snapshot."""
    from irc.fundamentals.types import ActiveFundSnapshot
    target = LookthroughTarget(
        kind="active_fund", key="fund_005827", display_cn="易方达蓝筹精选",
        provider_symbol="005827",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame()  # holdings empty → empty snapshot
        snap = build_snapshot(target)
    assert isinstance(snap, ActiveFundSnapshot)
