# 006 — Gold drivers into tilt

## Why

`gold_regime.json` derives the tilt from `vol_ratio` + `ADX` only —
range_bound / normal / neutral. Meanwhile `config/gold_drivers.yaml`
declares 6 fundamental drivers and `compute_gold_score()` is fully
implemented in `src/irc/scoring/gold_score.py` but its output never
makes it into `gold_regime.json` or the tilt decision.

The adversarial review (§B2 and §D) notes: "the gold engine is
configured to do nothing ~95% of the time and is marketed as a 6-driver
model in the spec." With central banks buying +3% YoY in Q1, fiscal
deficit $954B, and rising geopolitical risk, every fundamental driver is
pro-gold but the system says "neutral, pause."

## What changes

1. In `src/irc/scoring/pipeline.py` (or the gold pipeline entry point),
   compute `compute_gold_score(...)` whenever the necessary inputs are
   available; serialize the result to `gold_regime.json` as:

```json
{
  "regime": "range_bound",
  "zone": "normal",
  "tilt_from_regime": "neutral",
  "drivers_score": 67.4,                 # NEW
  "drivers_tilt": "neutral_plus",        # NEW, via gold_tilt_from_score
  "drivers_availability": "complete",    # NEW: complete | partial | unavailable
  "tilt": "neutral_plus"                 # NEW: combined final tilt
}
```

2. Combination rule (deterministic, no LLM):
   - If `drivers_availability == "complete"`, the final `tilt` is the
     **drivers_tilt** (overrides the regime-only tilt) UNLESS the
     regime is `trending_down` AND `drivers_tilt` is `overweight`, in
     which case clamp to `neutral_plus`.
   - If `drivers_availability == "partial"`, use the more-conservative
     of regime tilt vs drivers tilt.
   - If `drivers_availability == "unavailable"`, fall back to regime tilt
     and add a memo note "黄金驱动数据缺失，倾斜回退为价格分形".
3. Inputs for `compute_gold_score`: read from the ingest macro snapshot.
   When the snapshot lacks a field, set the corresponding driver input
   to its neutral value AND track which fields were inferred so
   `drivers_availability` reports correctly.

## Acceptance criteria

- `gold_regime.json` always contains `drivers_score`, `drivers_tilt`,
  `drivers_availability`, and the combined `tilt`.
- For inputs where all 6 drivers are pro-gold, `drivers_tilt` is
  `overweight` or `neutral_plus` (i.e. the tilt is NOT neutral).
- Test fixture with partial driver data exercises the partial path.
- Existing gold_regime tests pass with the new fields.

## Tests to add

- `tests/scoring/test_gold_tilt_combination.py`:
  - all 6 drivers pro-gold + range_bound regime → overweight or
    neutral_plus
  - all 6 drivers anti-gold + range_bound regime → underweight or
    neutral_minus
  - drivers complete but regime trending_down → clamp rule
  - drivers unavailable → falls back to regime tilt
