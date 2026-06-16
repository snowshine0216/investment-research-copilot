"""PURE §2.2 entry/outcome/maturity formula — shared by forward_score and backtest.

Three dates kept strictly separate. `anchor` is the entry anchor (run_date for
forward, as_of_date for retro). Entry = first nav_date STRICTLY > anchor.
outcome_idx = entry_idx + H. Maturity needs an entry obs, outcome in-range,
outcome_date <= today, and both endpoints finite & > 0. Otherwise a recorded
reason (no_entry_obs / not_matured / bad_nav) — never a FAIL. A scorer-invariant
violation (outcome_idx < entry_idx) raises ValueError → the runner maps to FAIL."""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EntryOutcome:
    reason: str                      # "ok" | "no_entry_obs" | "not_matured" | "bad_nav"
    entry_idx: int = -1
    outcome_idx: int = -1
    entry_nav_date: str = ""
    outcome_nav_date: str = ""
    fwd_ret: float = float("nan")


def _first_after(series: tuple[tuple[str, float], ...], anchor: str) -> int:
    for i, (d, _) in enumerate(series):
        if d > anchor:              # STRICT > — same-day NAV is never the entry
            return i
    return -1


def series_entry_outcome(
    series: tuple[tuple[str, float], ...], *, anchor: str, h: int, today: str,
) -> EntryOutcome:
    entry_idx = _first_after(series, anchor)
    if entry_idx < 0:
        return EntryOutcome(reason="no_entry_obs")
    outcome_idx = entry_idx + h
    if outcome_idx < entry_idx:                      # scorer invariant
        raise ValueError(f"outcome_idx {outcome_idx} < entry_idx {entry_idx}")
    if outcome_idx >= len(series):
        return EntryOutcome(reason="not_matured", entry_idx=entry_idx)
    outcome_date = series[outcome_idx][0]
    if outcome_date > today:
        return EntryOutcome(reason="not_matured", entry_idx=entry_idx,
                            outcome_idx=outcome_idx)
    e_nav, o_nav = series[entry_idx][1], series[outcome_idx][1]
    if not (math.isfinite(e_nav) and math.isfinite(o_nav) and e_nav > 0 and o_nav > 0):
        return EntryOutcome(reason="bad_nav", entry_idx=entry_idx, outcome_idx=outcome_idx)
    fwd = o_nav / e_nav - 1.0
    if not math.isfinite(fwd):                       # scorer invariant: NaN despite good endpoints
        raise ValueError("fwd_ret NaN despite finite positive endpoints")
    return EntryOutcome(
        reason="ok", entry_idx=entry_idx, outcome_idx=outcome_idx,
        entry_nav_date=series[entry_idx][0], outcome_nav_date=outcome_date, fwd_ret=fwd,
    )
