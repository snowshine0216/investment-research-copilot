"""PURE data-health digest builders. No file/clock/env access — the notify edge
reads artifacts + clock and passes dicts + dates here. Mirrors classify.py.

Every builder is TOTAL: a missing/corrupt input dict yields a single `warn`
`health_unknown` item, never an exception (degrade-never-crash, ADR 0016 AC8).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from irc.notify.calendar import previous_trading_day, trading_day_age

Level = Literal["info", "warn"]

_COVERAGE_FLOOR = 0.80
_STALE_TD_LIMIT = 3
_MACRO_AGE_LIMIT_DAYS = 7
_MAX_SIGNAL_IDS = 5
_UNKNOWN_TEXT = "数据健康未知 (health unknown)"


@dataclass(frozen=True)
class HealthItem:
    code: str
    level: Level
    text: str


@dataclass(frozen=True)
class HealthDigest:
    items: tuple[HealthItem, ...] = ()

    @property
    def has_warnings(self) -> bool:
        return any(i.level == "warn" for i in self.items)


def health_unknown() -> HealthDigest:
    return HealthDigest((HealthItem("health_unknown", "warn", _UNKNOWN_TEXT),))


def _md(iso: str) -> str:
    """`2026-07-06` -> `07-06` (MM-DD render form used across the digest)."""
    return iso[5:]
