"""PURE: composite-percentile series → rotation_state per board (spec §6, D5).

p80-entry / p70-exit hysteresis over the trading-day-indexed pctl series:
- emerging: first day above 0.80 was ≤5 td ago (early-detection deliverable).
- hot:      above the band >5 td (band exit only below 0.70).
- fading:   fell below 0.70 within the last 5 td after being hot/emerging.
- quiet:    otherwise.
Recomputed PURELY from the series — no incremental state file (D5). Total
function of the series slice (AC4); no I/O.
"""
from __future__ import annotations

P_ENTER = 0.80
P_EXIT = 0.70
EMERGING_WINDOW = 5


def _in_band_flags(pctls: list[float]) -> list[bool]:
    """Hysteresis membership: enter above P_ENTER, stay until below P_EXIT."""
    flags: list[bool] = []
    inside = False
    for p in pctls:
        if inside:
            inside = p >= P_EXIT
        else:
            inside = p >= P_ENTER
        flags.append(inside)
    return flags


def _days_since_entry(flags: list[bool]) -> int | None:
    """Trading days since the current in-band run began (1 = entered today).
    None when not currently in band."""
    if not flags or not flags[-1]:
        return None
    run = 0
    for f in reversed(flags):
        if not f:
            break
        run += 1
    return run


def _days_since_band_exit(flags: list[bool]) -> int | None:
    """Trading days since the last True→False transition. None if never exited or
    currently in band."""
    if not flags or flags[-1]:
        return None
    for i in range(len(flags) - 1, 0, -1):
        if flags[i - 1] and not flags[i]:
            return len(flags) - i
    return None


def classify_board(pctl_series: tuple[tuple[str, float], ...]) -> tuple[str, int]:
    """Pure (AC4): (state, days_in_state). Total function of the series slice."""
    pctls = [p for _d, p in pctl_series]
    flags = _in_band_flags(pctls)
    entry = _days_since_entry(flags)
    if entry is not None:
        if entry <= EMERGING_WINDOW:
            return "emerging", entry
        return "hot", entry
    exit_age = _days_since_band_exit(flags)
    if exit_age is not None and exit_age <= EMERGING_WINDOW:
        return "fading", exit_age
    return "quiet", 0
