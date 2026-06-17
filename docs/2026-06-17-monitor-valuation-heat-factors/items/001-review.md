Verdict: PASS
Source: /ship steps 8+9

Reviewers: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose (adversarial). Scoped tests at review time: 505 passed, 10 skipped → 507 passed, 10 skipped after fixes.

All findings surfaced pre-push and were FIXED before the PR opened (commit 7678c95). Zero open findings remain.

## Findings (all resolved)
- **P0 (silent-failure-hunter) — query-time CatalogException crashed the brief.** A `local.duckdb`
  that exists but lacks `instruments`/`index_valuation_history` passed the `db_path.exists()`+`connect()`
  open-guard, then the `SELECT` in valuation.py raised `duckdb.CatalogException`, propagating out of the
  per-fund loop and aborting `irc monitor` — violating valuation.py's "never raises on a data miss"
  docstring and spec §5.3.
  FIXED: `resolve_valuation_state` extracted `_resolve()`; the public fn is now a thin try/except that
  degrades to `ValuationResolution(None, False, "valuation_no_anchor")` on any read error and logs a
  WARNING with `exc_info=True`. Regression tests added (missing `instruments`; missing
  `index_valuation_history`) → N/A, no raise. (valuation.py:108-122)
- **P1 (all three) — leaked DuckDB connection on mid-loop exception.** `con.close()` was unguarded
  after the fund loop.
  FIXED: `run_monitor` wraps the loop + close in `try/finally` (preserving the `con is None` guard).
  (monitor_cmd.py:633-641)

## Non-blocking notes (accepted, no change required)
- Connection-open guard already logs with `exc_info=True` — observable, not silent. Good.
- `ValuationResolution.reason` is the item-002 forward contract (intentional); already asserted on the
  index-miss path by `test_index_anchored_immature_history_is_na`.
- Old `_VALUATION_MAP` keys (`fair_cheap`/`fair_expensive`) fully removed — grep-verified, zero callers.
- Adversarial: all edge inputs to `percentile_to_valuation_state` (None/NaN/0/1/0.20/0.40/0.70/0.90/neg/>1/inf)
  CLEAN; determinism holds. Verdict was RISKS (only the P1 leak), now resolved.

## Invariants confirmed
- gold/qdii_global stay `profile_ineligible` (test_gold_and_qdii_global_valuation_stay_profile_ineligible).
- No new N/A reason codes; ADR 0017 isolation preserved (opportunity pure fns on cached tables only).
