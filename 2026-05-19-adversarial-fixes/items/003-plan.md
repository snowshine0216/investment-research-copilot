# 003 — Plan

## Steps

1. `src/irc/research/quality_gate.py`:
   - Add `_CRITICAL_THEMES = {gold_drivers, cn_monetary, us_monetary,
     holdings_sector}`.
   - Add `_CRITICAL_DEGRADATION_WARN_THRESHOLD = 2`.
   - Add `_critical_theme_degraded(report)` (failure_reason OR
     provider_failures non-empty).
   - Add `_degraded_critical_themes(reports) -> tuple[str, ...]`.
   - Extend `QualityVerdict` with `degraded_themes`.
   - In `evaluate_research_quality`, emit WARN when ≥2 critical themes
     degraded (in addition to the existing rate-based WARN).
2. `tests/research/test_provider_degradation.py` covering:
   - 0 degraded → PASS clean
   - 1 critical degraded → PASS clean
   - ≥2 critical degraded → WARN
   - non-critical degradation does not trigger
   - holdings_sector relevance-filter failure counts
