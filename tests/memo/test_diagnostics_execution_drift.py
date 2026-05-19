"""Execution-drift alert (item 013, 2026-05-19)."""
from __future__ import annotations

import pytest

from irc.memo.diagnostics import compose_execution_drift_lines


def _alloc(*, residual: float, selected: list[dict] | None = None) -> dict:
    return {
        "diagnostics": {"cash_residual_weight": residual},
        "selected_instruments": selected or [],
    }


def test_drift_below_5pp_emits_no_lines() -> None:
    """5% residual with 5% target → drift 0, no alert."""
    assert compose_execution_drift_lines(_alloc(residual=0.05), cash_target_weight=0.05) == ()


def test_drift_above_5pp_emits_three_line_alert() -> None:
    """The 2026-05-19 reality: residual 15%, target 5% → 10pp drift."""
    lines = compose_execution_drift_lines(_alloc(residual=0.15), cash_target_weight=0.05)
    assert len(lines) == 3
    assert "执行漂移" in lines[0]
    assert "15.0%" in lines[0]
    assert "5.0%" in lines[0]
    assert "10.0pp" in lines[0]
    assert "建议处置" in lines[2]


def test_drift_lists_zero_weight_instruments() -> None:
    alloc = _alloc(
        residual=0.15,
        selected=[
            {"instrument_id": "511520", "name_cn": "政金债ETF富国",
             "target_weight": 0.0},
            {"instrument_id": "017641", "name_cn": "摩根标普500",
             "target_weight": 0.097},
            {"instrument_id": "510050", "name_cn": "上证50ETF华夏",
             "target_weight": 0.0},
        ],
    )
    lines = compose_execution_drift_lines(alloc, cash_target_weight=0.05)
    detail = next(l for l in lines if "未填仓标的" in l)
    assert "511520" in detail
    assert "510050" in detail
    assert "017641" not in detail  # not collapsed; it has weight


def test_no_alloc_returns_empty() -> None:
    assert compose_execution_drift_lines(None, cash_target_weight=0.05) == ()
    assert compose_execution_drift_lines({}, cash_target_weight=0.05) == ()


def test_missing_diagnostics_returns_empty() -> None:
    """Defensive: if cash_residual_weight isn't present, no alert."""
    assert compose_execution_drift_lines({"diagnostics": {}}, cash_target_weight=0.05) == ()


def test_drift_exactly_at_threshold_emits_lines() -> None:
    """5pp drift is the threshold — inclusive on the lower bound."""
    lines = compose_execution_drift_lines(_alloc(residual=0.10), cash_target_weight=0.05)
    assert len(lines) == 3
