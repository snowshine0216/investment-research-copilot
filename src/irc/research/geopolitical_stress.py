from __future__ import annotations

from irc.research.theme_research import ThemeReport

GEOPOLITICAL_STRESS_DEFAULT: float = 0.4
"""Default returned when no usable theme report is available. Matches the
prior hardcoded value at gold_cmd.py:74 so behavior is unchanged on the
degraded path."""

_STRESS_TOKENS: tuple[str, ...] = (
    # English
    "war", "sanction", "tariff", "strike", "conflict", "escalat",
    "invasion", "missile", "attack", "embargo",
    # Chinese
    "战争", "制裁", "关税", "冲突", "升级", "袭击", "导弹", "封锁",
)

_CALM_TOKENS: tuple[str, ...] = (
    # English
    "peace", "ceasefire", "agreement", "truce", "deescalat", "diplomacy",
    # Chinese
    "缓和", "协议", "停火", "和谈", "和平",
)

# Each net stress-vs-calm hit moves the score by this much; chosen so a
# handful of clear hits is enough to deviate meaningfully from the default
# without saturating on a single mention.
_PER_HIT_DELTA: float = 0.05


def _count_hits(text: str, tokens: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(lower.count(token) for token in tokens)


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
    stress = _count_hits(report.report_md, _STRESS_TOKENS)
    calm = _count_hits(report.report_md, _CALM_TOKENS)
    net = stress - calm
    if net == 0:
        return default
    score = default + (net * _PER_HIT_DELTA)
    return max(0.0, min(1.0, score))
