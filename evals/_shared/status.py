from __future__ import annotations
from typing import Literal


Status = Literal["PASS", "WARN", "FAIL"]
_RANK: dict[str, int] = {"PASS": 0, "WARN": 1, "FAIL": 2}


def classify_status(
    value: float, thresholds: dict[str, float], direction: str,
) -> Status:
    """direction: 'higher_is_better' or 'lower_is_better'."""
    if direction == "higher_is_better":
        warn = thresholds.get("warn_below")
        fail = thresholds.get("fail_below")
        if fail is not None and value < fail:
            return "FAIL"
        if warn is not None and value < warn:
            return "WARN"
        return "PASS"
    if direction == "lower_is_better":
        warn = thresholds.get("warn_above")
        fail = thresholds.get("fail_above")
        if fail is not None and value > fail:
            return "FAIL"
        if warn is not None and value > warn:
            return "WARN"
        return "PASS"
    raise ValueError(f"unknown direction: {direction}")


def worst_status(statuses: list[Status]) -> Status:
    if not statuses:
        return "PASS"
    return max(statuses, key=lambda s: _RANK[s])
