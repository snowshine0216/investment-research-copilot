"""Quality gate for the research stage output.

A pure function. Given a list of ThemeReports, decide whether the output is
good enough to drive downstream decisions. Two thresholds:
  - FAIL if any whole locale is dead (every theme of that locale failed)
  - FAIL if overall success rate < 0.5
  - WARN if success rate < 0.8 (does not block, but surfaced)

WARN does not stop the pipeline. FAIL stops it (exit code 2).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from irc.research.theme_research import ThemeReport


_FAIL_SUCCESS_FLOOR = 0.5
_WARN_SUCCESS_FLOOR = 0.8

# Adversarial review §A4 (2026-05-19): when a critical theme silently
# loses a provider or returns no relevant sources, downstream thesis
# work loses an axis of independent corroboration. Surface this as a
# WARN-level signal so the memo can flag it even if the overall pipeline
# pass rate is still high.
_CRITICAL_THEMES: frozenset[str] = frozenset({
    "gold_drivers", "cn_monetary", "us_monetary", "holdings_sector",
})
_CRITICAL_DEGRADATION_WARN_THRESHOLD = 2


@dataclass(frozen=True)
class QualityVerdict:
    passed: bool        # False → halt the pipeline
    warning: bool       # True → run completed but quality is degraded
    exit_code: int      # 0 PASS or WARN; 2 FAIL
    reasons: tuple[str, ...]
    degraded_themes: tuple[str, ...] = ()  # critical themes that lost a provider or returned no relevant sources


def _dead_locale_reasons(reports: list[ThemeReport]) -> list[str]:
    by_locale: dict[str, list[ThemeReport]] = defaultdict(list)
    for r in reports:
        by_locale[r.locale].append(r)
    return [
        f"all {len(items)} {locale} themes failed; downstream analysis cannot "
        f"draw on {locale}-language evidence"
        for locale, items in by_locale.items()
        if items and all(r.failure_reason for r in items)
    ]


def _rate_and_reasons(
    reports: list[ThemeReport],
) -> tuple[float, list[str]]:
    successes = sum(1 for r in reports if not r.failure_reason)
    rate = successes / len(reports)
    reasons: list[str] = []
    if rate < _FAIL_SUCCESS_FLOOR:
        reasons.append(
            f"success rate {rate:.0%} is below the {_FAIL_SUCCESS_FLOOR:.0%} floor"
        )
    return rate, reasons


def _critical_theme_degraded(report: ThemeReport) -> bool:
    """A critical theme is degraded when (a) it lost any provider, or
    (b) it returned a non-empty failure_reason (which subsumes the
    "no relevant sources after relevance filter" case from item 001).
    Note: the locale-dead and overall-rate checks already catch the
    case where ALL themes failed; this is the more sensitive signal
    that one critical axis is down even when the overall rate is fine.
    """
    if report.failure_reason:
        return True
    if report.provider_failures:
        return True
    return False


def _degraded_critical_themes(reports: list[ThemeReport]) -> tuple[str, ...]:
    return tuple(
        r.theme for r in reports
        if r.theme in _CRITICAL_THEMES and _critical_theme_degraded(r)
    )


def evaluate_research_quality(reports: list[ThemeReport]) -> QualityVerdict:
    if not reports:
        return QualityVerdict(
            passed=False, warning=False, exit_code=2,
            reasons=("no theme reports were produced",),
        )

    reasons = _dead_locale_reasons(reports)
    rate, rate_reasons = _rate_and_reasons(reports)
    reasons.extend(rate_reasons)
    degraded = _degraded_critical_themes(reports)

    if reasons:
        return QualityVerdict(
            passed=False, warning=False, exit_code=2,
            reasons=tuple(reasons), degraded_themes=degraded,
        )

    warn_reasons: list[str] = []
    if rate < _WARN_SUCCESS_FLOOR:
        warn_reasons.append(
            f"success rate {rate:.0%} is below the {_WARN_SUCCESS_FLOOR:.0%} "
            "warn threshold (run continues)"
        )
    if len(degraded) >= _CRITICAL_DEGRADATION_WARN_THRESHOLD:
        warn_reasons.append(
            "critical themes degraded: " + ", ".join(degraded)
            + " — downstream thesis evidence loses an axis of corroboration"
        )

    if warn_reasons:
        return QualityVerdict(
            passed=True, warning=True, exit_code=0,
            reasons=tuple(warn_reasons), degraded_themes=degraded,
        )

    return QualityVerdict(
        passed=True, warning=False, exit_code=0,
        reasons=(), degraded_themes=degraded,
    )
