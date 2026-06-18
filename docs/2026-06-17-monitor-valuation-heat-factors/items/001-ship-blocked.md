# 001 — /ship steps 8+9 pre-push findings (routed to fix before PR open)

Source: /ship steps 8 (code-reviewer + silent-failure-hunter) + 9 (adversarial). Tests: 505 passed, 10 skipped.

## P0 — query-time CatalogException crashes the brief (must fix)
`monitor_cmd.py` opens `connect(root/data/local.duckdb)` guarded by `db_path.exists()` + try/except,
but the open-guard does NOT cover query time. A DB that exists yet lacks the `instruments` /
`index_valuation_history` tables (partial / pre-migration / hand-created DB) → `connect()` succeeds,
then the `SELECT` in `valuation.py:_tracked_index_for_fund` / `_resolve_index` raises
`duckdb.CatalogException`, which propagates out of the per-fund loop and aborts `irc monitor`.
This contradicts `valuation.py`'s docstring ("Never raises on a data miss") and the spec §5.3
availability contract ("degrade honestly to N/A, never crash the brief").
Fix: catch DuckDB read errors in `resolve_valuation_state` (belt-and-suspenders over the whole
resolve body), log a structured warning, degrade to `ValuationResolution(None, False, "valuation_no_anchor")`.

## P1 — leaked DuckDB connection on mid-loop exception (fix; trivial)
`monitor_cmd.py` per-fund loop + `con.close()` is unguarded; if `_process_fund` raises (LLM/fetch
error, or the P0 above), `con.close()` is skipped → leaked handle. Fix: wrap the loop + close in
`try/finally` (or `contextlib.closing`).

## Notes (non-blocking)
- Connection-open guard logs with `exc_info=True` — good, observable.
- `ValuationResolution.reason` is the item-002 forward contract (kept intentionally); already
  asserted on the index-miss path by `test_index_anchored_immature_history_is_na`.
- Old `_VALUATION_MAP` keys (`fair_cheap`/`fair_expensive`) fully removed — verified by grep, zero callers.
- Edge inputs to `percentile_to_valuation_state` (None/NaN/0/1/boundaries/neg/>1/inf) all CLEAN.

## Resolution
Fixed pre-push by a Sonnet fix subagent (P0 + P1 + regression tests), then ship continues.
Final review verdict captured in items/001-review.md after fixes verify green.
