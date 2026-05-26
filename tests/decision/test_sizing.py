"""Tests for the sizing module — per-tranche % suggestion + trigger evaluation.

Pure functions; no I/O or fixtures beyond the small dataclasses they accept.
"""
from __future__ import annotations

import pytest

from irc.decision.sizing import (
    TriggerSpec,
    evaluate_trigger,
    format_why_when_line,
    suggest_tranche_pct,
)


# ── suggest_tranche_pct ───────────────────────────────────────────────────────

def test_suggest_tranche_pct_build_mode_divides_by_four() -> None:
    """`build` mode = accumulate to target over ~4 monthly tranches."""
    assert suggest_tranche_pct(target_weight=0.1121, build_mode="build") == pytest.approx(0.1121 / 4)


def test_suggest_tranche_pct_full_mode_uses_full_target() -> None:
    """`full` mode = position already complete; no tranche split."""
    assert suggest_tranche_pct(target_weight=0.10, build_mode="full") == pytest.approx(0.10)


def test_suggest_tranche_pct_unknown_mode_returns_full_for_safety() -> None:
    """Unknown mode → fall back to target (conservative — caller still sees cap)."""
    assert suggest_tranche_pct(target_weight=0.10, build_mode="taper") == pytest.approx(0.10)


def test_suggest_tranche_pct_zero_target_returns_zero() -> None:
    assert suggest_tranche_pct(target_weight=0.0, build_mode="build") == 0.0


# ── evaluate_trigger ──────────────────────────────────────────────────────────

def test_evaluate_trigger_le_threshold_met_when_value_below() -> None:
    """`<=` comparator: trigger met when current ≤ threshold."""
    trig = TriggerSpec(name="weekly_drawdown_4pct", comparator="<=", threshold=-0.04)
    assert evaluate_trigger(trig, current_value=-0.05) == "met"


def test_evaluate_trigger_le_threshold_not_met_when_value_above() -> None:
    trig = TriggerSpec(name="weekly_drawdown_4pct", comparator="<=", threshold=-0.04)
    assert evaluate_trigger(trig, current_value=-0.01) == "not_met"


def test_evaluate_trigger_gt_threshold_met_when_value_above() -> None:
    """`>` comparator: trigger met when current > threshold."""
    trig = TriggerSpec(name="vix_high", comparator=">", threshold=25.0)
    assert evaluate_trigger(trig, current_value=27.0) == "met"


def test_evaluate_trigger_gt_threshold_not_met_when_value_below() -> None:
    trig = TriggerSpec(name="vix_high", comparator=">", threshold=25.0)
    assert evaluate_trigger(trig, current_value=16.76) == "not_met"


def test_evaluate_trigger_missing_returns_missing() -> None:
    trig = TriggerSpec(name="weekly_drawdown_4pct", comparator="<=", threshold=-0.04)
    assert evaluate_trigger(trig, current_value=None) == "missing"


# ── format_why_when_line ──────────────────────────────────────────────────────

def test_format_why_when_line_includes_trigger_name_and_status_emoji() -> None:
    """The per-instrument 'when to buy' line must show:
    (1) trigger name, (2) condition, (3) current value, (4) status emoji."""
    trig = TriggerSpec(name="weekly_drawdown_4pct", comparator="<=", threshold=-0.04)
    line = format_why_when_line(trig, current_value=-0.0077, current_value_unit="pct")
    assert "weekly_drawdown_4pct" in line
    assert "≤ -4.00%" in line or "-4.00%" in line
    assert "-0.77%" in line
    # Status indicator — must be visible
    assert "✗" in line or "NOT MET" in line


def test_format_why_when_line_met_uses_checkmark() -> None:
    trig = TriggerSpec(name="vix_high", comparator=">", threshold=25.0)
    line = format_why_when_line(trig, current_value=27.0, current_value_unit="raw")
    assert "✓" in line or "MET" in line


def test_format_why_when_line_missing_uses_warning() -> None:
    trig = TriggerSpec(name="weekly_drawdown_4pct", comparator="<=", threshold=-0.04)
    line = format_why_when_line(trig, current_value=None, current_value_unit="pct")
    assert "⚠" in line or "MISSING" in line.upper() or "未知" in line
