"""Tests for `_format_trigger_status_compact` — the picks-table-cell
compact form of the decision-report's `format_why_when_line`.

Per trigger: `{trigger.name} {marker}` where marker is one of ✓ / ✗ / ⚠.
Multi-trigger: `<br>` joined, YAML insertion order preserved (no sort).
Empty triggers tuple → "" (renderer then emits "—" for the cell).
"""
from __future__ import annotations

from irc.memo.picks_table import _format_trigger_status_compact


def test_format_empty_triggers_returns_empty_string() -> None:
    """No triggers → empty string. Renderer converts "" to em-dash."""
    assert _format_trigger_status_compact(
        triggers=(),
        macro_snapshot={},
        weekly_return_by_id={},
        instrument_id="510300",
    ) == ""


def test_format_single_met_trigger_uses_checkmark() -> None:
    """Drawdown -5% under -4% threshold → met → ✓."""
    triggers = (
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
        instrument_id="510300",
    )
    assert out == "weekly_drawdown_4pct ✓"


def test_format_single_not_met_trigger_uses_cross() -> None:
    """Drawdown -1% above -4% threshold → not_met → ✗."""
    triggers = (
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.01},
        instrument_id="510300",
    )
    assert out == "weekly_drawdown_4pct ✗"


def test_format_single_missing_trigger_uses_warning() -> None:
    """No weekly_return for the instrument → missing → ⚠."""
    triggers = (
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={},  # 510300 absent
        instrument_id="510300",
    )
    assert out == "weekly_drawdown_4pct ⚠"


def test_format_multi_trigger_joined_with_br_preserves_yaml_order() -> None:
    """Two triggers → one row, joined by <br>. YAML order from the input
    tuple is preserved (no sort, no shuffle)."""
    triggers = (
        {
            "name": "vix_above_25",
            "comparator": ">",
            "threshold": 25.0,
            "data_field": "macro.vix",
        },
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={"vix": 27.0},  # met
        weekly_return_by_id={"510300": -0.01},  # not_met
        instrument_id="510300",
    )
    assert out == "vix_above_25 ✓<br>weekly_drawdown_4pct ✗"


def test_format_unknown_comparator_falls_back_to_missing() -> None:
    """Comparator that evaluate_trigger doesn't recognise → missing → ⚠."""
    triggers = (
        {
            "name": "weird_trigger",
            "comparator": "~~",
            "threshold": 0.0,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
        instrument_id="510300",
    )
    assert out == "weird_trigger ⚠"


def test_format_trigger_status_compact_preserves_zero_threshold() -> None:
    """P1-1 fix: integer 0 threshold is preserved, not silently swapped by `or 0.0`.

    Trigger: weekly_return > 0 (threshold=0, comparator=">").
    With weekly_return=+0.05 the condition is met → ✓.
    If `or 0.0` had substituted 0.0 the result would be the same here, BUT
    we confirm via a negative case: weekly_return=-0.01 should yield ✗ (not_met),
    which is only correct if threshold=0 (not some other default).
    """
    triggers = [
        {
            "name": "weekly_return_above_zero",
            "comparator": ">",
            "threshold": 0,  # integer zero — falsy, so `or 0.0` would substitute
            "data_field": "instrument.weekly_return",
        }
    ]
    # Positive return: 0.05 > 0 → met → ✓
    out_met = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": 0.05},
        instrument_id="510300",
    )
    assert out_met == "weekly_return_above_zero ✓"

    # Negative return: -0.01 > 0 → not_met → ✗
    out_not_met = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.01},
        instrument_id="510300",
    )
    assert out_not_met == "weekly_return_above_zero ✗"


def test_format_trigger_with_missing_name_uses_default_label() -> None:
    """Defensive: trigger dict without a `name` key → label 'trigger'."""
    triggers = (
        {
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
        instrument_id="510300",
    )
    assert out == "trigger ✓"
