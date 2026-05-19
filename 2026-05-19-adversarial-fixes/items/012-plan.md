# 012 — Plan

## Steps

1. `src/irc/opportunity/discipline.py`:
   - Loosen `derive_risk_action` trim-review condition. Old rule
     required `overweight AND (expensive OR hot)` which rarely fires
     for a system without active positions. New rule:
     `trim_review` if `(overweight AND (expensive OR hot))` OR
     `(is_holding AND (expensive OR hot))`.
2. `src/irc/templates/config/triggers.yaml`:
   - Add trim-side triggers: `valuation_very_expensive`,
     `heat_crowded`, `weight_above_band_high`.
3. `src/irc/schemas/triggers.py`:
   - Allow `threshold: float | str` (categorical thresholds need string
     comparators for valuation_state/heat_state).
4. `tests/opportunity/test_trim_triggers.py`:
   - very_expensive holding → trim_review
   - crowded holding → trim_review
   - very_expensive non-holding → none (DCA pauses, no risk action)
   - overweight + expensive (legacy path) → still trim_review
   - falsified thesis > trim signal → exit_review
   - fair valuation holding → none
