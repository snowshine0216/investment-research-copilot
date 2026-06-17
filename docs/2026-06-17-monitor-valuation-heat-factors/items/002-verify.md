Verdict: PASS

Subagent: sonnet
Source: branch claude/monitor-valuation-heat-factors-002
Entry point exercised: direct `resolve_valuation_state` call via /tmp/verify_002.py + `uv run pytest tests/monitor/test_lookthrough.py tests/monitor/test_valuation.py -v`

## Observed behavior (per AC)

### AC1 — Look-through branch fills in `_resolve_lookthrough`
- Implemented in `src/irc/monitor/valuation.py:_resolve_lookthrough`:
  - Loads cached holdings via `load_latest_active_fund_cached(fund_id, root / "data")`.
  - Pulls cached PE/PB series via `_stock_series_by_code(con, codes)`.
  - Delegates pure math to `irc.monitor.lookthrough.lookthrough_valuation_state(snapshot, series)`.
  - Coverage gate fail → `ValuationResolution(None, False, "valuation_no_anchor")`.
- Direct exercise output:
  ```
  CASE 1 (60% covered, rising PE):  state='very_expensive', cached=True, reason=None
  CASE 2 (no snapshot):             state=None, cached=False, reason='valuation_no_anchor'
  CASE 3 (no stock_valuation rows): state=None, cached=False, reason='valuation_no_anchor'
  CASE 4 (HK non-6-digit holding):  state=None, cached=False, reason='valuation_no_anchor'
  ```

### AC2 — ADR 0017 evidence isolation (pure functions on monitor cached data, no opportunity pipeline)
- `lookthrough.py` imports `fund_valuation_percentile`, `HoldingWeight`, `MetricSeries` from
  `irc.opportunity.lookthrough_valuation` (pure module, no I/O).
- `valuation.py:_resolve_lookthrough` reads ONLY cached DuckDB (`stock_valuation_history`) +
  monitor-written snapshot JSON (`load_latest_active_fund_cached`). No opportunity output files read.
- Function-local import in `_resolve_lookthrough` avoids module-load cycle
  (`lookthrough.py` imports `percentile_to_valuation_state` from `valuation.py`).
- `import irc.monitor.valuation; import irc.monitor.lookthrough` → `imports OK` (no cycle).

### AC3 — 6 pure active funds get real state; thin coverage → `valuation_no_anchor`; index path and gold/qdii unchanged
- `test_lookthrough_sufficient_coverage_returns_state`: 60% covered, 200 rising PE points → `very_expensive` (pct 1.0), `cached=True`. PASSED.
- `test_lookthrough_coverage_below_floor_is_na`: 30% < 0.50 floor → N/A, `valuation_no_anchor`. PASSED.
- `test_lookthrough_holdings_but_no_stock_valuations_is_na`: holdings present, no series → N/A. PASSED.
- `test_lookthrough_non_ashare_holding_is_na`: HK 5-digit code → uncovered → N/A. PASSED.
- `test_lookthrough_no_snapshot_is_na`: no cached snapshot → N/A. PASSED.
- `test_index_path_unchanged_by_lookthrough`: fund with `tracked_index` still takes index branch. PASSED.

### §6 Invariants
- `valuation_no_anchor` is the N/A reason on every miss path (KNOWN_NA_REASONS member).
- Determinism guard: `uv run pytest tests/evals/test_monitor_signal_runner.py tests/evals/test_monitor_signal_metrics.py -q` → **8 passed**.
- `ValuationResolution` is a `frozen=True` dataclass: `test_result_type_is_frozen` PASSED.

## Test summary

```
tests/monitor/test_lookthrough.py  5 passed
tests/monitor/test_valuation.py   28 passed
  (item 002 look-through tests:    test_lookthrough_* = 7 tests, all PASSED)
tests/evals/test_monitor_signal_runner.py + test_monitor_signal_metrics.py: 8 passed
```

Total: **41 tests, 0 failures.**

## Failures

None.
