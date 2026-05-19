"""FX / QDII premium diagnostic lines (item 014, 2026-05-19)."""
from __future__ import annotations

import pytest

from irc.memo.diagnostics import compose_fx_qdii_lines


def _alloc(rows: list[dict]) -> dict:
    return {"selected_instruments": rows}


def test_qdii_below_floor_emits_no_lines() -> None:
    alloc = _alloc([
        {"instrument_id": "017641", "asset_class": "us_etf", "target_weight": 0.10},
        {"instrument_id": "G", "asset_class": "gold", "target_weight": 0.20},
    ])
    assert compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45)) == ()


def test_qdii_above_floor_emits_three_lines() -> None:
    """The 2026-05-19 reality: ~25% in us_etf via QDII."""
    alloc = _alloc([
        {"instrument_id": "017641", "asset_class": "us_etf", "target_weight": 0.097},
        {"instrument_id": "050025", "asset_class": "us_etf", "target_weight": 0.056},
        {"instrument_id": "018043", "asset_class": "us_etf", "target_weight": 0.052},
        {"instrument_id": "019172", "asset_class": "us_etf", "target_weight": 0.045},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert len(lines) == 3
    assert "外汇与QDII敞口提醒" in lines[0]
    # 0.097 + 0.056 + 0.052 + 0.045 = 0.25
    assert "25.0%" in lines[0]
    assert "溢价/折价" in lines[1]
    assert "对冲成本" in lines[2]


def test_qdii_within_usd_tolerance_says_so() -> None:
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert "落在" in lines[0]
    assert "超出" not in lines[0]


def test_qdii_above_usd_tolerance_flags_exceeded() -> None:
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.50},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert "超出" in lines[0]


def test_qdii_no_tolerance_still_emits_header() -> None:
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=None)
    assert len(lines) == 3
    assert "外汇与QDII敞口提醒" in lines[0]


def test_hk_etf_counts_toward_qdii() -> None:
    """hk_etf in this codebase is also QDII-feeder."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "hk_etf", "target_weight": 0.15},
        {"instrument_id": "Y", "asset_class": "us_etf", "target_weight": 0.10},
    ])
    lines = compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45))
    assert lines  # 25% combined
    assert "25.0%" in lines[0]


def test_cn_classes_dont_count() -> None:
    alloc = _alloc([
        {"instrument_id": "G", "asset_class": "gold", "target_weight": 0.30},
        {"instrument_id": "B", "asset_class": "cn_bond_fund", "target_weight": 0.30},
    ])
    assert compose_fx_qdii_lines(alloc, usd_tolerance=(0.25, 0.45)) == ()


def test_no_alloc_returns_empty() -> None:
    assert compose_fx_qdii_lines(None, usd_tolerance=(0.25, 0.45)) == ()
    assert compose_fx_qdii_lines({}, usd_tolerance=(0.25, 0.45)) == ()
