# 007 — Allocation runner modernization

## Problem

`evals/allocation/runner.py` reads `outputs/allocation/allocation.json`. The current producer (`src/irc/commands/allocate_cmd.py`) writes `outputs/<date>/proposed_allocation.yaml`. The historical metrics `in_band_per_class`, `currency_in_tolerance`, and `max_pair_correlation_1y` require fields (`class_bands`, `currency_targets`, `currency_exposure`, `correlation_matrix_1y`) that the current producer **does not write**.

## Producer contract (from `allocate_cmd.py:46-55`)

```yaml
generated_at: ...
gold_tilt: ...
target_weights_per_class: { ... }   # used by weight_sum
selected_instruments: [ ... ]       # used by effective_n
dropped_due_to_correlation: [ ... ]
diagnostics: { ... }
```

## Required behavior

- Locate `proposed_allocation.yaml` via shared locator.
- Parse YAML.
- Compute only the two metrics supportable by current artifacts: `weight_sum_deviation` and `effective_n`. Keep their thresholds unchanged.
- Add report `notes` listing the three deferred metrics as Phase 2 redesign candidates.
- Write via `write_report` under the located artifact date.

## Acceptance criteria

- `evals/allocation/runner.py` uses locator + `write_report`.
- The runner does not invoke `in_band_per_class`, `currency_in_tolerance`, or `max_pair_correlation_1y`.
- The historical metric functions stay in `evals/allocation/metrics.py` with a module-level docstring noting deferral.
- Tests cover: missing input → FAIL; valid YAML → metrics computed + Phase-2 note present; weight_sum deviation > threshold → FAIL.
- Existing `tests/evals/test_allocation_metrics.py` tests pass unchanged.

## Files touched

- `evals/allocation/runner.py` (rewrite)
- `evals/allocation/metrics.py` (docstring note only)
- `tests/evals/test_allocation_runner.py` (replace JSON fixture with YAML)
