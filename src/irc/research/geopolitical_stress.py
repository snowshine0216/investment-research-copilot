from __future__ import annotations

import re

from irc.research.theme_research import ThemeReport

GEOPOLITICAL_STRESS_DEFAULT: float = 0.4
"""Default returned when no usable theme report is available. Matches the
prior hardcoded value at gold_cmd.py:74 so behavior is unchanged on the
degraded path."""

# English tokens are matched with regex word boundaries to avoid silent
# false positives (the bare token "war" used to match "forward", "warning",
# "warrant" etc., which are common in gold/macro research text). For stems
# like escalation, we list explicit inflections rather than relying on
# substring matching.
_STRESS_TOKENS_EN: tuple[str, ...] = (
    "war", "wars", "wartime", "warring",
    "sanction", "sanctions", "sanctioned",
    "tariff", "tariffs",
    "strike", "strikes",
    "conflict", "conflicts", "conflicting",
    "escalate", "escalates", "escalated", "escalating", "escalation",
    "invasion", "invasions", "invade", "invaded",
    "missile", "missiles",
    "attack", "attacks", "attacked",
    "embargo", "embargoes", "embargoed",
)

_CALM_TOKENS_EN: tuple[str, ...] = (
    "peace", "peaceful",
    "ceasefire", "ceasefires",
    "truce",
    "deescalate", "deescalated", "deescalation",
    "diplomacy", "diplomatic", "diplomat",
)

# CJK tokens are matched as plain substrings — there is no word-boundary
# notion in Chinese text and these tokens are unambiguous enough that
# substring matching does not produce false positives.
_STRESS_TOKENS_CJK: tuple[str, ...] = (
    "战争", "制裁", "关税", "冲突", "升级", "袭击", "导弹", "封锁",
)

_CALM_TOKENS_CJK: tuple[str, ...] = (
    "缓和", "协议", "停火", "和谈", "和平",
)

# Each net stress-vs-calm hit moves the score by this much; chosen so a
# handful of clear hits is enough to deviate meaningfully from the default
# without saturating on a single mention. Linear in net hits; saturation
# is via the [0, 1] clip in geopolitical_stress_from_theme_report.
_PER_HIT_DELTA: float = 0.05


def _count_hits(text: str, en_tokens: tuple[str, ...], cjk_tokens: tuple[str, ...]) -> int:
    """Count token occurrences. English uses word-boundary regex to avoid
    substring false positives; CJK uses plain substring matching."""
    lower = text.lower()
    pattern = r"\b(?:" + "|".join(re.escape(t) for t in en_tokens) + r")\b"
    en_hits = len(re.findall(pattern, lower))
    cjk_hits = sum(lower.count(t) for t in cjk_tokens)
    return en_hits + cjk_hits


def _has_usable_report(report: ThemeReport | None) -> bool:
    if report is None:
        return False
    if report.failure_reason:
        return False
    return bool(report.report_md and report.report_md.strip())


def geopolitical_stress_from_theme_report(
    report: ThemeReport | None,
    *,
    default: float = GEOPOLITICAL_STRESS_DEFAULT,
) -> float:
    """Derive a 0..1 geopolitical-stress score from a theme report.

    Returns `default` when the report is missing, failed, or empty. Otherwise
    counts stress vs calm keyword hits in the report body, applies a small
    per-hit delta to the default, and clips to [0, 1].

    Intentionally simple — the goal is to remove the hardcoded constant,
    not to build a sentiment model. Replace with something stronger when
    we have one.
    """
    if not _has_usable_report(report):
        return default
    assert report is not None  # for type checker
    stress = _count_hits(report.report_md, _STRESS_TOKENS_EN, _STRESS_TOKENS_CJK)
    calm = _count_hits(report.report_md, _CALM_TOKENS_EN, _CALM_TOKENS_CJK)
    net = stress - calm
    if net == 0:
        return default
    score = default + (net * _PER_HIT_DELTA)
    return max(0.0, min(1.0, score))
