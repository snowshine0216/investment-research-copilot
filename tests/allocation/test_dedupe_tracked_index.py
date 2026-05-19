"""Tracked-index dedupe (adversarial-review item 008, 2026-05-19).

Two S&P500 share classes (017641 + 050025) and two Nasdaq100 share
classes (018043 + 019172) ended up in the same allocation last week,
turning ~25% of NAV into two correlated factor bets. This pins the
deterministic dedupe-before-correlation-filter behavior.
"""
from __future__ import annotations

import pandas as pd
import pytest

from irc.allocation.correlation_filter import drop_duplicate_index_trackers
from irc.allocation.pipeline import run_allocation


def test_dedupe_same_class_same_index_keeps_higher_weight() -> None:
    rows = [
        {"instrument_id": "017641", "asset_class": "us_etf",
         "tracked_index": "sp500", "target_weight": 0.097, "composite_score": 58},
        {"instrument_id": "050025", "asset_class": "us_etf",
         "tracked_index": "sp500", "target_weight": 0.056, "composite_score": 53},
    ]
    kept, dropped = drop_duplicate_index_trackers(rows)
    assert [r["instrument_id"] for r in kept] == ["017641"]
    assert dropped[0]["instrument_id"] == "050025"
    assert dropped[0]["reason"] == "duplicate_tracked_index"
    assert dropped[0]["kept_against"] == "017641"


def test_dedupe_passes_empty_tracked_index_through() -> None:
    rows = [
        {"instrument_id": "A", "asset_class": "cn_equity_fund",
         "tracked_index": "", "target_weight": 0.05, "composite_score": 60},
        {"instrument_id": "B", "asset_class": "cn_equity_fund",
         "tracked_index": None, "target_weight": 0.04, "composite_score": 55},
    ]
    kept, dropped = drop_duplicate_index_trackers(rows)
    assert {r["instrument_id"] for r in kept} == {"A", "B"}
    assert dropped == []


def test_dedupe_different_class_same_index_keeps_both() -> None:
    rows = [
        {"instrument_id": "517010", "asset_class": "cn_etf",
         "tracked_index": "hs300", "target_weight": 0.08, "composite_score": 60},
        {"instrument_id": "000176", "asset_class": "cn_equity_fund",
         "tracked_index": "hs300", "target_weight": 0.05, "composite_score": 58},
    ]
    kept, dropped = drop_duplicate_index_trackers(rows)
    assert {r["instrument_id"] for r in kept} == {"517010", "000176"}
    assert dropped == []


def test_dedupe_normalizes_case_and_whitespace() -> None:
    rows = [
        {"instrument_id": "A", "asset_class": "us_etf",
         "tracked_index": "  SP500 ", "target_weight": 0.05, "composite_score": 60},
        {"instrument_id": "B", "asset_class": "us_etf",
         "tracked_index": "sp500", "target_weight": 0.04, "composite_score": 55},
    ]
    kept, dropped = drop_duplicate_index_trackers(rows)
    assert len(kept) == 1
    assert kept[0]["instrument_id"] == "A"


def test_pipeline_drops_duplicate_sp500_and_renormalizes_class_total() -> None:
    """End-to-end: two us_etf rows tracking sp500 → one survives and
    absorbs the dropped weight so the class total is preserved."""
    scores = [
        {"instrument_id": "017641", "asset_class": "us_etf",
         "role": "core_us_equity", "tracked_index": "sp500", "composite_score": 70},
        {"instrument_id": "050025", "asset_class": "us_etf",
         "role": "core_us_equity", "tracked_index": "sp500", "composite_score": 65},
    ]
    class_targets = {
        "us_etf": {"center": 0.50, "band": [0.30, 0.70]},
        "gold":   {"center": 0.50, "band": [0.30, 0.70]},
    }
    out = run_allocation(
        scores=scores, class_targets=class_targets,
        gold_tilt="neutral", correlation=pd.DataFrame(),
        per_class_top_k=4,
    )
    us = [r for r in out.selected_instruments if r["asset_class"] == "us_etf"]
    assert len(us) == 1
    # Dropped diagnostic carries the reason.
    drop = [d for d in out.dropped_due_to_correlation
            if d.get("reason") == "duplicate_tracked_index"]
    assert len(drop) == 1
    assert drop[0]["kept_against"] == us[0]["instrument_id"]
