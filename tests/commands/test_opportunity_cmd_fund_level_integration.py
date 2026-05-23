"""End-to-end: `_build_rows` over a 3-row fixture (gold + bond + cn_etf)."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest


def _nav_frame_for(date_str: str = "2026-03-15", nav: float = 4.5678) -> pd.DataFrame:
    y, m, d = (int(x) for x in date_str.split("-"))
    return pd.DataFrame({
        "净值日期": [_dt.date(y, m, d)],
        "单位净值": [nav],
        "日增长率": ["0.39"],
    })


def _ann_frame_for(fund_id: str, report_id: str = "AN1") -> pd.DataFrame:
    return pd.DataFrame({
        "基金代码": [fund_id],
        "公告标题": [f"title-{fund_id}"],
        "基金名称": [fund_id],
        "公告日期": [_dt.date(2024, 1, 1)],
        "报告ID": [report_id],
    })


def _universal_side(fund_ids: list[str]):
    """Return side_effect dispatching to the correct frame per (fn_name, symbol)."""

    def _side(fn_name, **kw):
        symbol = kw.get("symbol", "")
        if fn_name == "fund_open_fund_info_em":
            return _nav_frame_for()
        if fn_name == "fund_announcement_dividend_em":
            return _ann_frame_for(symbol, f"DIV-{symbol}")
        if fn_name == "fund_announcement_report_em":
            return _ann_frame_for(symbol, f"REP-{symbol}")
        if fn_name == "fund_announcement_personnel_em":
            return _ann_frame_for(symbol, f"PER-{symbol}")
        return pd.DataFrame()
    return _side


def test_three_row_integration_gold_bond_cn_etf_dual_coverage(tmp_path: Path) -> None:
    """Gold + cn_bond_fund + cn_etf all produce rows with dual-coverage evidence."""
    from irc.commands.opportunity_cmd import _build_rows
    from irc.schemas.universe import Instrument

    scores = [
        {"instrument_id": "518880", "asset_class": "gold", "role": "small_watch"},
        {"instrument_id": "000001", "asset_class": "cn_bond_fund", "role": "small_watch"},
        {"instrument_id": "510300", "asset_class": "cn_etf", "role": "core_dca"},
    ]
    instr_index = {
        "510300": Instrument(
            instrument_id="510300", name_cn="华泰柏瑞沪深300ETF",
            ticker="510300",
            asset_class="cn_etf", market="cn_on_exchange",
            currency="cny",
            venue_required=["A股交易"],
            tracked_index="csi300",
        ),
    }
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
        side_effect=_universal_side(["518880", "000001", "510300"]),
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
    assert len(rows) == 3
    by_id = {r.instrument_id: r for r in rows}
    for iid in ("518880", "000001", "510300"):
        r = by_id[iid]
        kinds = {e.citation_kind for e in r.thesis_evidence}
        assert "data" in kinds, f"{iid} missing data leg"
        assert "information" in kinds, f"{iid} missing information leg"
        for e in r.thesis_evidence:
            assert e.scope == "instrument"
            assert e.owner_instrument_id == iid


def test_three_row_integration_writes_cache(tmp_path: Path) -> None:
    """Cache write under data/fundamentals/2026Q1/nav/fund_{iid}.json."""
    from irc.commands.opportunity_cmd import _build_rows

    scores = [
        {"instrument_id": "518880", "asset_class": "gold", "role": "small_watch"},
    ]
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
        side_effect=_universal_side(["518880"]),
    ):
        with patch.dict("os.environ", {"IRC_OPPORTUNITY_AUTOBUILD": "1"}):
            _build_rows(
                scores, instr_index, holdings, portfolio_total_cny,
                available_venues, theme_thesis, theme_reports, tmp_path,
                asset_class_targets, con,
                output_date="2026-05-23",
                limit=None,
                rebuild_fundamentals=False,
            )
    cache_files = list((tmp_path / "data" / "fundamentals").rglob("fund_518880.json"))
    assert len(cache_files) == 1
    assert "/nav/" in str(cache_files[0]) or "\\nav\\" in str(cache_files[0])
