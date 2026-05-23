"""Citation-id determinism for FundLevelSnapshot evidence (ADR 0001 §2).

Empty URL + summary "[{report_id}] {title}" → the preimage falls back to
`f"{source}:{date}:{summary[:64]}"`, putting the discriminating `report_id`
in the first ~24 chars (well within the 64-char window).
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import patch

import pandas as pd

from irc.fundamentals.snapshot import _build_fund_level_snapshot
from irc.fundamentals.types import LookthroughTarget


def _frames(ids: list[str]):
    """Return _ak_call side_effect that returns one announcement per topic
    with given report_ids."""

    def _side(fn_name, **kw):
        if fn_name == "fund_open_fund_info_em":
            return pd.DataFrame({
                "净值日期": [_dt.date(2026, 3, 15)],
                "单位净值": [4.5678],
            })
        if fn_name == "fund_announcement_dividend_em":
            return pd.DataFrame({
                "基金代码": ["518880"], "公告标题": [f"title-{ids[0]}"],
                "基金名称": ["X"],
                "公告日期": [_dt.date(2024, 1, 1)],
                "报告ID": [ids[0]],
            })
        if fn_name == "fund_announcement_report_em":
            return pd.DataFrame()
        if fn_name == "fund_announcement_personnel_em":
            return pd.DataFrame()
        return pd.DataFrame()
    return _side


def _snap_for(ids: list[str]):
    target = LookthroughTarget(
        kind="gold", key="gold", display_cn="黄金", provider_symbol="518880",
    )
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=_frames(ids),
    ):
        return _build_fund_level_snapshot(target)


def test_citation_id_is_deterministic_across_runs() -> None:
    snap1 = _snap_for(["AN001"])
    snap2 = _snap_for(["AN001"])
    ids1 = [e.citation_id for e in snap1.evidence]
    ids2 = [e.citation_id for e in snap2.evidence]
    assert ids1 == ids2


def test_citation_id_changes_when_report_id_changes() -> None:
    """Two announcements with same title + date but different report_id →
    distinct citation_ids (preimage's summary[:64] discriminates via [report_id])."""
    snap_a = _snap_for(["AN001"])
    snap_b = _snap_for(["AN002"])
    info_a = [e for e in snap_a.evidence if e.citation_kind == "information"]
    info_b = [e for e in snap_b.evidence if e.citation_kind == "information"]
    assert info_a and info_b
    assert info_a[0].citation_id != info_b[0].citation_id


def test_nav_citation_id_deterministic() -> None:
    snap1 = _snap_for(["AN001"])
    snap2 = _snap_for(["AN001"])
    nav1 = [e for e in snap1.evidence if e.citation_kind == "data"][0]
    nav2 = [e for e in snap2.evidence if e.citation_kind == "data"][0]
    assert nav1.citation_id == nav2.citation_id
