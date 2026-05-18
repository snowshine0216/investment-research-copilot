# 006 — Gold_score runner modernization

## Problem

`evals/gold_score/runner.py` reads `outputs/gold_score/gold_score.json`, a retired path. The current producer (`src/irc/commands/gold_cmd.py`) writes `outputs/<date>/gold_regime.json` and `outputs/<date>/gold_band.yaml`. The historical metrics (`drivers_freshness`, `regime_flip_4w`, `tilt_within_preferences_band`) expected fields (`drivers`, `regime_history`, `preferences_band`) that the current producer **does not write at all**. Faking values for these would mask reality.

## Current producer contract

`gold_regime.json` schema (from `src/irc/commands/gold_cmd.py:104-109`):

```json
{
  "regime": "trending|range|...",
  "vol_ratio": 1.2,
  "adx": 22.5,
  "trend_sign": 1,
  "score": 60.0,
  "tilt": "overweight|neutral_plus|neutral|neutral_minus|underweight",
  "zone": "...",
  "scenario": "...",
  "scenario_triggers": ["..."]
}
```

`gold_band.yaml` — dataclass-derived band config (must exist; contents not interpreted by the runner today).

Valid tilt enums (from `src/irc/scoring/gold_score.py:91-96`): `overweight`, `neutral_plus`, `neutral`, `neutral_minus`, `underweight`.

## Required behavior

- Locate via `locate(repo_root, ("gold_regime.json", "gold_band.yaml"))` — both files required.
- On miss: `write_missing_input_report`, FAIL.
- On hit: parse `gold_regime.json`; compute only metrics supportable by the current schema; write report via `write_report` under the locator-supplied artifact date.
- Historical metrics that require fields the producer no longer writes are **removed from the runner** and surfaced in the report's `notes` as a Phase 2 redesign list.

## New metric set (grounded in current artifacts)

| Metric | Definition | Threshold |
|---|---|---|
| `gold_regime_schema_completeness` | fraction of the 9 expected `gold_regime.json` fields present | `warn_below=1.0`, `fail_below=0.7` |
| `gold_tilt_valid_enum` | 1.0 if `tilt` ∈ valid set, else 0.0 | `warn_below=1.0`, `fail_below=1.0` |
| `gold_score_in_range` | 1.0 if `0 ≤ score ≤ 100`, else 0.0 | `warn_below=1.0`, `fail_below=1.0` |

`gold_band.yaml` is required by the locator but not parsed by the runner (its presence IS the contract). A Phase 2 metric may exercise its contents.

## Acceptance criteria

- `evals/gold_score/runner.py` reads via locator and writes via `write_report`.
- `evals/gold_score/metrics.py` gains the three new pure metric functions above; the historical functions stay in the file (with a module-level docstring noting they are deferred to Phase 2 metric redesign) so existing metric tests continue to pass.
- The new runner's report includes `notes` listing the deferred historical metrics by name.
- A new test verifies the runner returns PASS against a representative `gold_regime.json` and that the report contains the three new metrics.
- A new test verifies the runner FAILs when `gold_regime.json` is partial (missing several expected fields).
- A new test verifies the runner FAILs when `gold_band.yaml` is missing (locator enforces multi-file contract).
- Existing `test_gold_score_runner_fails_when_input_missing` still passes (now via the new path).
- Existing `tests/evals/test_gold_score_metrics.py` tests still pass — historical metric functions remain callable.

## Non-goals

- Do not invent metrics that would require data the producer does not write.
- Do not refactor `gold_cmd.py`.
- Do not add a "drivers history" or "regime history" to the producer just to satisfy the historical metrics — that's a Phase 2 product decision.

## Files touched

- `evals/gold_score/runner.py` (rewrite)
- `evals/gold_score/metrics.py` (add new metrics; keep historical with deprecation note)
- `tests/evals/test_gold_score_runner.py` (replace JSON fixture; add new tests)
- `tests/evals/test_gold_score_metrics.py` (add tests for new metric functions)
