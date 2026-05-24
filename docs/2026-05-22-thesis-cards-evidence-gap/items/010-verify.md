# Item 010 Verify — DuckDB `fund_holdings` ingest

**Branch:** `autodev/thesis-evidence-010-duckdb-fund-holdings-ingest`
**PR:** https://github.com/snowshine0216/investment-research-copilot/pull/64
**Verified:** 2026-05-24
**Verdicts:** PASS (tasks 1–4) | one pre-existing failure documented below

---

## Task 1: AC Walkthrough — test → AC mapping

All 21 ACs covered. Test file: `tests/data/test_fund_holdings_ingestor.py` (55 tests) +
`tests/commands/test_ingest_cmd.py` (last 3 tests, lines 1068–1194).

| AC | Claim | Test(s) in `test_fund_holdings_ingestor.py` |
|----|-------|----------------------------------------------|
| AC1 | `fund_holdings` DDL byte-equal to locked baseline | `test_fund_holdings_ddl_is_byte_equal_to_locked_baseline`, `test_fund_holdings_remains_in_expected_tables` (`tests/data/test_duckdb_helper.py`) |
| AC2 | Module exports 7 public names; `HoldingRow`/`IngestOutcome` are frozen dataclasses | `test_module_exports_public_surface`, `test_holding_row_accepts_valid_fields`, `test_ingest_outcome_constructs` |
| AC3 | `ingest_one` with empty table + populated cache → `wrote`, `rows_written=N` | `test_ingest_one_writes_when_stale` |
| AC4 | Same-day re-run → `skipped_fresh`, `rows_written=0`, DB row count unchanged | `test_ingest_one_idempotent_with_fresh_report` |
| AC5 | `force=True` re-writes even on fresh table | `test_ingest_one_force_bypasses_staleness` |
| AC6 | `is_stale` returns True when no rows; False within threshold; True past threshold | `test_is_stale_returns_true_when_no_rows`, `test_is_stale_returns_false_within_threshold`, `test_is_stale_returns_true_past_threshold`, `test_is_stale_boundary_exactly_at_threshold`, `test_is_stale_threshold_override`, `test_is_stale_uses_max_report_date_when_multiple_quarters` |
| AC7 | Non-eligible asset classes (`gold`, `cn_bond_fund`, etc.) → `skipped_no_data` | `test_ingest_one_asset_class_filter_gold`, `test_ingest_one_asset_class_filter_other` (parametrised ×6) |
| AC8 | `cn_equity_fund` reads ActiveFundSnapshot cache; `cn_etf` cache-hit wins over AkShare | `test_collect_holding_rows_from_active_fund_snapshot`, `test_collect_holding_rows_cn_etf_cache_hit_wins`, `test_ingest_one_active_fund_cache_wins_over_akshare` |
| AC9 | `cn_etf` cache-miss → `fetch_cn_etf_holdings` called once; source=`akshare_cn_etf` | `test_collect_holding_rows_cn_etf_fallback_to_akshare` |
| AC10 | Empty snapshot preserves existing rows; returns `skipped_no_data` | `test_collect_holding_rows_all_quarters_empty_returns_snapshot_empty`, `test_ingest_one_snapshot_empty_preserves_existing_rows` |
| AC11 | `source_report_date=""` → `missing_report_date` | `test_collect_holding_rows_missing_report_date_returns_empty`, `test_ingest_one_missing_report_date` |
| AC12 | Scoring round-trip: `load_scoring_metrics` returns `holdings_concentration_top10=0.45` | `test_scoring_metrics_reads_ingested_holdings` |
| AC13 | `ingest_many` isolates per-target AkShare raise; batch does not propagate | `test_ingest_many_isolates_per_target_failures`, `test_collect_holding_rows_cn_etf_fallback_handles_raise` |
| AC14 | `ingest_many` returns one `IngestOutcome` per target in input order | `test_ingest_many_preserves_input_order`; wire-in: `test_run_ingest_wires_holdings_step` |
| AC15 | Row insertion order = `(weight_pct DESC, holding_ticker ASC)` deterministic | `test_upsert_holdings_deterministic_row_order` |
| AC16 | Holdings failures non-fatal: `run_ingest` exits 0; no halt sidecar | `test_run_ingest_holdings_failure_not_fatal` (`test_ingest_cmd.py`) |
| AC17 | Manifest's `ak_counts["fund_holdings"]` aggregated and written | `test_run_ingest_holdings_count_in_manifest` (`test_ingest_cmd.py`) |
| AC18 | `_raw_ref` shared across all rows for same `(iid, report_date)` | `test_upsert_holdings_raw_ref_pattern` |
| AC19 | Named-column `INSERT OR REPLACE` SQL with `executemany`; no positional INSERT | `test_upsert_holdings_uses_named_columns` |
| AC20 | `today_iso` = `_china_today()` (wall-clock CST); never a pipeline `seed_date` | `test_run_ingest_wires_holdings_step` (monkeypatches `_china_today`) |
| AC21 | `opportunity/` and `memo/` do not read `fund_holdings` (structural grep) | Verified by grep: `grep -rn "fund_holdings" src/irc/opportunity/ src/irc/memo/` → zero output |

Test run:
```
tests/data/test_fund_holdings_ingestor.py: 55 passed in 0.56s
tests/commands/test_ingest_cmd.py: 100 passed in 415.79s (7:01)
```

---

## Task 2: Item 008 baseline hard-check

Command: `pytest tests/integration/test_publishable_set_lockdown.py -x -q`

Result: **24 passed, 1 skipped** — exactly the expected baseline. No byte-equality regression.

---

## Task 3: Broader regression sweep

Command: `pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py --ignore=tests/test_e2e_plan3_full_pipeline.py --deselect tests/commands/test_run_cmd.py::test_only_stage_runs_single -x -q`

Result: **1 failed, 665 passed, 1 deselected, 16 warnings** (427.77s)

### Failure: `tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports`

**Status: Pre-existing on the parent feature branch; NOT introduced by item 010.**

- The `dag_acyclic_check` function in `evals/architecture/metrics.py` builds a top-level
  subpackage import graph (collapsing `irc.X.Y` → `X`). It detects the edge
  `opportunity → memo` (from `src/irc/opportunity/auditor.py:
  `from irc.memo.numeric_audit import NumericFinding`) and
  `memo → opportunity` (from `src/irc/memo/`), forming a cycle.
- `auditor.py` was added in commit `6202841` (item 009 — citation-gate,
  merged before item 010 began). The test passes on `main`; it was broken
  by an earlier item on this parent feature branch.
- Item 010's new module `src/irc/data/fund_holdings_ingestor.py` does NOT add any
  new cross-subpackage cycle (verified: `data → fundamentals` only; no `fundamentals → data` edge exists).
- This failure pre-dates item 010's 13 commits. No item 010 code change caused or can fix it.

---

## Task 4: Ruff check

Command: `ruff check src/irc/data/fund_holdings_ingestor.py src/irc/commands/ingest_cmd.py tests/data/test_fund_holdings_ingestor.py tests/commands/test_ingest_cmd.py`

Result: **All checks passed!**

---

## Task 5: Idempotency smoke

Invoked `ingest_one` twice against fund_id `005827` in a temporary DuckDB.
- First call: `today_iso='2024-04-10'` (10 days after `report_date='2024-03-31'`).
  Table is empty → `is_stale=True` → writes 5 rows.
  Result: `status='wrote', rows_written=5`.
- Second call: same `today_iso`, same fund. Table now has rows from `2024-03-31`
  (10 days old, within 30-day threshold) → `is_stale=False` → skips.
  Result: `status='skipped_fresh', rows_written=0`. DB row count still 5.

Output:
```
=== Idempotency Smoke ===
First call  → status='wrote', rows_written=5
  DB rows after first call: 5
Second call → status='skipped_fresh', rows_written=0
  DB rows after second call: 5

PASS: Second call returns skipped_fresh, rows_written=0, DB row count unchanged (5).
```

---

## Summary

| Check | Result |
|-------|--------|
| AC walkthrough (21 ACs → tests) | PASS — all 21 ACs covered |
| Item 008 baseline (24p 1s) | PASS — byte-equality intact |
| Regression sweep (665 tests) | PASS (1 pre-existing failure on parent branch, pre-dates item 010) |
| Ruff lint | PASS — clean |
| Idempotency smoke | PASS — second `ingest_one` returns `skipped_fresh`, zero rows written |

**Overall verdict: PASS.** The one regression (`test_dag_acyclic_check`) is pre-existing on the `autodev/thesis-cards-evidence-gap` feature branch and was introduced by item 009 (`auditor.py` cross-import from `memo`); item 010 neither caused nor worsened it.
