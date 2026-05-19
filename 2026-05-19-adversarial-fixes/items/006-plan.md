# 006 — Plan

## Steps

1. `src/irc/commands/gold_cmd.py`:
   - Track which gold drivers used real vs stub-fallback values
     (currently the WGC CSV absence silently zeros cb_purchases and
     etf_holdings).
   - Compute `drivers_availability ∈ {complete, partial, unavailable}`
     from the count of zero-fallback drivers.
   - Add `_combine_tilts(regime, drivers_tilt, drivers_availability)`
     pure helper.
   - Emit `gold_regime.json` with new fields: `drivers_score`,
     `drivers_tilt`, `drivers_availability`, `drivers_unavailable` list,
     and a final combined `tilt`. Keep legacy `score` alias for
     downstream consumers.
2. `tests/scoring/test_gold_tilt_combination.py`:
   - complete + range_bound + overweight → overweight
   - complete + trending_down + overweight → clamped to neutral_plus
   - partial + overweight → cautious cap at neutral_plus
   - unavailable → fall back to neutral
