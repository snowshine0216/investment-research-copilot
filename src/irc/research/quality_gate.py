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


@dataclass(frozen=True)
class QualityVerdict:
    passed: bool        # False → halt the pipeline
    warning: bool       # True → run completed but quality is degraded
    exit_code: int      # 0 PASS or WARN; 2 FAIL
    reasons: tuple[str, ...]


def evaluate_research_quality(reports: list[ThemeReport]) -> QualityVerdict:
    if not reports:
        return QualityVerdict(
            passed=False, warning=False, exit_code=2,
            reasons=("no theme reports were produced",),
        )

    reasons: list[str] = []

    # Locale liveness: if every theme of a locale failed, that whole locale is dead.
    by_locale: dict[str, list[ThemeReport]] = defaultdict(list)
    for r in reports:
        by_locale[r.locale].append(r)
    for locale, items in by_locale.items():
        if items and all(r.failure_reason for r in items):
            reasons.append(
                f"all {len(items)} {locale} themes failed; downstream analysis cannot "
                f"draw on {locale}-language evidence"
            )

    successes = sum(1 for r in reports if not r.failure_reason)
    rate = successes / len(reports)

    if rate < _FAIL_SUCCESS_FLOOR:
        reasons.append(
            f"success rate {rate:.0%} is below the {_FAIL_SUCCESS_FLOOR:.0%} floor"
        )

    if reasons:
        return QualityVerdict(
            passed=False, warning=False, exit_code=2, reasons=tuple(reasons),
        )

    if rate < _WARN_SUCCESS_FLOOR:
        return QualityVerdict(
            passed=True, warning=True, exit_code=0,
            reasons=(
                f"success rate {rate:.0%} is below the {_WARN_SUCCESS_FLOOR:.0%} "
                "warn threshold (run continues)",
            ),
        )

    return QualityVerdict(passed=True, warning=False, exit_code=0, reasons=())
