"""Per-tranche sizing + trigger-state evaluation for decision-grade rendering.

Pure functions: callers pass in the trade plan's trigger spec + the current
data point, and these helpers return a sized suggestion and a one-line
status string. Used by the memo §5 + decision_report.md "Decision Sheet"
section that lets a reader answer *why, when, how much* per pick.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TriggerSpec:
    """Locked subset of the trade_plan.yaml trigger schema needed for
    decision-grade rendering. `comparator` is a member of `<=, >, <, >=, ==`.
    `threshold` and `current_value` share a unit defined by the caller — for
    `instrument.weekly_return` this is a fraction (e.g. -0.04 == -4%); for
    `macro.vix` it is a raw scalar (e.g. 25.0)."""
    name: str
    comparator: str
    threshold: float


TriggerState = Literal["met", "not_met", "missing"]


# `build` mode = accumulate from zero over N tranches. Project convention is
# 4 tranches (monthly) — see CONTEXT.md → "build mode" and the per-row
# `buy_method=small_account_anchor (default)` in trade_plan.yaml.
_BUILD_TRANCHE_COUNT: int = 4


def suggest_tranche_pct(target_weight: float, build_mode: str) -> float:
    """Suggested per-tranche cap as a fraction of total portfolio.

    `build` mode → `target_weight / 4` (the per-period cap, only fires
    when the trigger condition is met). Other modes default to the full
    target (no tranching).
    """
    if target_weight <= 0:
        return 0.0
    if build_mode == "build":
        return target_weight / _BUILD_TRANCHE_COUNT
    return target_weight


def evaluate_trigger(trig: TriggerSpec, current_value: float | None) -> TriggerState:
    """Evaluate a trigger against the current data point.

    Missing input → ``missing`` (renderer should warn). Otherwise compares
    by the comparator and returns ``met`` / ``not_met``.
    """
    if current_value is None:
        return "missing"
    comp = trig.comparator
    t = trig.threshold
    v = float(current_value)
    if comp == "<=":
        return "met" if v <= t else "not_met"
    if comp == ">=":
        return "met" if v >= t else "not_met"
    if comp == "<":
        return "met" if v < t else "not_met"
    if comp == ">":
        return "met" if v > t else "not_met"
    if comp == "==":
        return "met" if v == t else "not_met"
    # Unknown comparator → treat as missing so the renderer falls back to a warning.
    return "missing"


def _fmt_value(v: float | None, unit: str) -> str:
    if v is None:
        return "未知 / unknown"
    if unit == "pct":
        return f"{v * 100:+.2f}%"
    return f"{v:.2f}"


def _fmt_threshold(t: float, unit: str) -> str:
    if unit == "pct":
        return f"{t * 100:+.2f}%"
    return f"{t:.2f}"


def format_why_when_line(
    trig: TriggerSpec,
    current_value: float | None,
    current_value_unit: str = "raw",
) -> str:
    """Render the per-instrument 'why-when' status line.

    Format::

      触发 `{name}`：{condition}；current = {current} ⇒ {status_marker}.

    `status_marker` is one of: ``✓ MET``, ``✗ NOT MET``, ``⚠ MISSING``.
    The Chinese label survives because the memo + decision_report are both
    bilingual; the English status word is for machine-grep friendliness.
    """
    state = evaluate_trigger(trig, current_value)
    threshold_str = _fmt_threshold(trig.threshold, current_value_unit)
    current_str = _fmt_value(current_value, current_value_unit)
    condition = f"{trig.comparator} {threshold_str}"
    if state == "met":
        marker = "✓ MET"
    elif state == "not_met":
        marker = "✗ NOT MET"
    else:
        marker = "⚠ MISSING (数据缺失)"
    return (
        f"触发 `{trig.name}`：{condition}；current = {current_str} ⇒ {marker}."
    )
