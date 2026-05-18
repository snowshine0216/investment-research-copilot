# 009 — Memo runner modernization

## Problem

`evals/memo/runner.py` reads `outputs/memo/memo.md` (retired path) and three sidecar files (`audit.json`, `refs.json`, `baseline_chars.txt`) the current producer never writes. The current producer (`src/irc/commands/memo_cmd.py:147-160`) writes to `outputs/<date>/`:

- `memo.md` — the memo draft
- `memo_audit.txt` — free-form audit notes (unstructured)
- `memo_traceability.json` — `{n_refs_provided, n_refs_quoted_verbatim, n_refs}`

Historical metrics that can't be grounded in current artifacts:
- `auditor_no_factual_flags` — needs a structured audit result (current `memo_audit.txt` is free text).
- `length_drift_vs_baseline` — needs a baseline-chars contract the current pipeline does not maintain.

Metric the spec wants preserved or redesigned grounded in current artifacts:
- `seven_sections_present(memo_text)` — works as-is against `memo.md`.
- A verbatim-ref metric — `memo_traceability.json` already records `n_refs_quoted_verbatim / n_refs_provided`; we can compute the same invariant directly from structured data instead of scanning the memo text.

## Required behavior

- Locate `(memo.md, memo_traceability.json)` via shared locator — both required (multi-file contract).
- Compute:
  - `seven_sections_present` (existing function, unchanged).
  - `verbatim_ref_rate` (new) = `n_refs_quoted_verbatim / n_refs_provided`, defaulting to 1.0 when `n_refs_provided == 0`.
- Report `notes` lists `auditor_no_factual_flags` and `length_drift_vs_baseline` as deferred to Phase 2.
- Write report via `write_report` under the located artifact date.
- `memo_audit.txt` is NOT required by the locator (it can be present or absent; the runner does not consume it).

## Acceptance criteria

- Runner uses locator + `write_report`; retired path is gone.
- New `verbatim_ref_rate(traceability)` function in `evals/memo/metrics.py`.
- Tests: missing input FAIL; valid (memo.md + memo_traceability.json) → PASS; deferred-metrics note present; partial multi-file set → FAIL (locator).
- Existing metric tests still pass (`auditor_no_factual_flags` and `length_drift_vs_baseline` stay in metrics.py with deferral note).

## Files touched

- `evals/memo/runner.py` (rewrite)
- `evals/memo/metrics.py` (add `verbatim_ref_rate`; deferral note on historical functions)
- `tests/evals/test_memo_runner.py` (new fixtures)
- `tests/evals/test_memo_metrics.py` (add test for `verbatim_ref_rate`)
