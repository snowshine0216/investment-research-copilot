# Item 010 inline review verdict (from `/ship` steps 8+9)

**Verdict:** PASS-WITH-NITS (after pre-PR fix-round)
**Captured by:** 3 parallel subagents (`pr-review-toolkit:code-reviewer` + `pr-review-toolkit:silent-failure-hunter` + adversarial `general-purpose`).
**Date:** 2026-05-24
**Branch:** `autodev/thesis-evidence-010-duckdb-fund-holdings-ingest`
**PR:** https://github.com/snowshine0216/investment-research-copilot/pull/64

## Findings closed in fix-round

### P0 (3 reviewers converged — adversarial BREAKS verdict)
1. **`ingest_one`/`ingest_many` "never raises" contract broken** — DuckDB errors AND `HoldingRow.__post_init__` validation failures (NaN weight from malformed snapshot; `ConstituentAnalysis.__post_init__` only checks `< 0`, NaN passes) propagated through `ingest_many` and crashed the entire ingest stage. Fix: wrap `ingest_one` body in try/except. Regression: `test_ingest_one_nan_weight_propagates_as_failed_not_unhandled_exception`.

### P1
2. **`missing_report_date` early-return** abandoned older candidates (code-reviewer P1.2). Fix: `continue` instead of `return`.
3. **Failed outcomes silent in non-verbose mode** (silent-failure P0.2/P1). Fix: unconditional `_log.warning`.
4. **`upsert_holdings` not transactional** (silent-failure P1.4). Fix: explicit `BEGIN`/`COMMIT`/`ROLLBACK`.

## Deferred (notes/design)

- `is_stale` `>` vs `>=` boundary — intentional per spec; defer.
- Single-writer concurrency assumption — per CONTEXT.md convention; defer.
- Pre-existing DAG check failure inherited from item 009 (`opportunity/auditor.py` imports `irc.memo` — surfaces a `memo ↔ opportunity` cycle that escaped item 009's pre-merge review). Documented for follow-up but out of item 010's scope.

## Verification

- `pytest tests/data/test_fund_holdings_ingestor.py`: 56 passed.
- Item 008 baseline: 24 passed / 1 skipped.
- Ruff clean.

## Recommendation

PASS-WITH-NITS. Ready for merge.
