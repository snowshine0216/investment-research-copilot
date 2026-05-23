from __future__ import annotations

import json
from pathlib import Path

import pytest

from irc.fundamentals.snapshot_cache import (
    active_fund_cache_path,
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot
from irc.opportunity.types import ConstituentAnalysis, ThesisEvidence


def _make_snapshot(quarter: str = "2024Q1") -> ActiveFundSnapshot:
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a",
        date="2024-04-15", summary="贵州茅台 24Q1",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=6.2,
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=(ev,), failure_reasons=(), one_line_view="x",
    )
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter=quarter, cache_probed_at="",
        constituent_analyses=(c,),
        failure_reasons_by_symbol={"600519": ()},
    )


def test_active_fund_cache_path_uses_quarter(tmp_path: Path) -> None:
    path = active_fund_cache_path("005827", "2024Q1", tmp_path)
    assert path == tmp_path / "fundamentals" / "2024Q1" / "active_fund" / "fund_005827.json"


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    snap = _make_snapshot()
    written = write_active_fund_cache(snap, tmp_path)
    assert written.exists()
    loaded = load_active_fund_cache("005827", "2024Q1", tmp_path)
    assert loaded is not None
    assert loaded.fund_id == "005827"
    assert loaded.source_report_quarter == "2024Q1"
    assert loaded.constituent_analyses[0].symbol == "600519"
    assert loaded.constituent_analyses[0].evidence[0].citation_id != ""


def test_load_active_fund_cache_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_active_fund_cache("005827", "2024Q1", tmp_path) is None


def test_load_active_fund_cache_returns_none_on_malformed(tmp_path: Path) -> None:
    path = active_fund_cache_path("005827", "2024Q1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json}", encoding="utf-8")
    assert load_active_fund_cache("005827", "2024Q1", tmp_path) is None


def test_write_then_reload_preserves_holding_weight_pct(tmp_path: Path) -> None:
    snap = _make_snapshot()
    write_active_fund_cache(snap, tmp_path)
    loaded = load_active_fund_cache("005827", "2024Q1", tmp_path)
    assert loaded.constituent_analyses[0].evidence[0].holding_weight_pct == 6.2
