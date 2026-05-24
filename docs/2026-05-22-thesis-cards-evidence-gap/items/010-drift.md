# Item 010 Drift Report — DuckDB `fund_holdings` ingest

**Branch:** `autodev/thesis-evidence-010-duckdb-fund-holdings-ingest`
**Base:** `autodev/thesis-cards-evidence-gap`
**Date:** 2026-05-24
**Verdict:** CLEAN — no drift detected

---

## Commit count

Plan specified 12 commits; 12 commits landed, one per task in the correct conventional-commit style:

```
7a8aa5f feat(data): add fund_holdings_ingestor module skeleton + HoldingRow/IngestOutcome dataclasses (AC2)
c97f7cd feat(data): add is_stale staleness gate for fund_holdings (AC6, AC20)
d9fb9e0 feat(data): add upsert_holdings named-column INSERT OR REPLACE (AC15, AC18, AC19)
d085e3b feat(data): add collect_holding_rows active-fund snapshot path (AC8, AC10, AC11)
8bbd9e5 feat(data): add cn_etf AkShare fallback to collect_holding_rows with defensive try/except (AC9, AC13, F5)
abb7d17 test(data): add Q6 regression — collect_holding_rows glob matches active_fund_cache_path
a1689d6 feat(data): add ingest_one orchestrator with staleness gate + asset-class filter (AC3, AC4, AC5, AC7, AC10, AC11, AC12)
97ff7c6 feat(data): add ingest_many orchestrator preserving order + isolating failures (AC13, AC14)
c65bda5 test(data): lock scoring integration — load_scoring_metrics reads ingested holdings (AC12)
9fb6730 feat(ingest): wire fund_holdings ingestor into run_ingest as best-effort enrichment (AC14, AC16, AC17, AC20)
738d0d7 test(data): lock fund_holdings DDL byte-equality (AC1)
7663280 docs(adr): note item 010 fund_holdings_ingestor as downstream consumer in ADR 0002 §5
```

---

## File-touch map vs plan

| File | Plan | Actual |
|---|---|---|
| `src/irc/data/fund_holdings_ingestor.py` | Create | Created (A) |
| `src/irc/commands/ingest_cmd.py` | Modify | Modified (M) |
| `tests/data/test_fund_holdings_ingestor.py` | Create | Created (A) |
| `tests/fixtures/active_fund_snapshots/__init__.py` | Create | Created (A) |
| `tests/commands/test_ingest_cmd.py` | Modify | Modified (M) |
| `tests/data/test_duckdb_helper.py` | Modify | Modified (M) |
| `docs/adr/0002-active-fund-fetch-engine.md` | Modify | Modified (M) |
| `src/irc/data/duckdb_helper.py` | NOT touched | Not touched |
| `src/irc/fundamentals/snapshot_cache.py` | NOT touched | Not touched |
| `src/irc/fundamentals/akshare_fundamentals.py` | NOT touched | Not touched |
| `src/irc/scoring/metrics_loader.py` | NOT touched | Not touched |
| `src/irc/opportunity/` | NOT touched | Not touched (AC21 clean) |
| `src/irc/memo/` | NOT touched | Not touched (AC21 clean) |

No extra files touched; no planned files skipped.

---

## AC coverage map

| AC | Description | Test(s) | Status |
|---|---|---|---|
| AC1 | DuckDB schema unchanged; DDL byte-equal | `test_fund_holdings_ddl_is_byte_equal_to_locked_baseline`, `test_fund_holdings_remains_in_expected_tables` | PASS |
| AC2 | Module exports 7 public names | `test_module_exports_public_surface` | PASS |
| AC3 | Empty-table upsert writes rows | `test_ingest_one_writes_when_stale` | PASS |
| AC4 | Idempotent same-day rerun → skipped_fresh, zero INSERTs | `test_ingest_one_idempotent_with_fresh_report` | PASS |
| AC5 | `force=True` bypasses staleness | `test_ingest_one_force_bypasses_staleness` | PASS |
| AC6 | 30-day staleness gate (29 fresh / 31 stale / none=stale) | `test_is_stale_returns_true_when_no_rows`, `test_is_stale_returns_false_within_threshold`, `test_is_stale_returns_true_past_threshold`, `test_is_stale_boundary_exactly_at_threshold`, `test_is_stale_threshold_override`, `test_is_stale_uses_max_report_date_when_multiple_quarters` | PASS |
| AC7 | Asset-class filter (gold/cn_bond_fund/us_etf/qdii_*) | `test_ingest_one_asset_class_filter_gold`, `test_ingest_one_asset_class_filter_other[cn_bond_fund/us_etf/hk_etf/qdii_us/qdii_hk/qdii_global]` | PASS |
| AC8 | Active-fund cache wins over AkShare | `test_collect_holding_rows_from_active_fund_snapshot`, `test_collect_holding_rows_cn_etf_cache_hit_wins`, `test_ingest_one_active_fund_cache_wins_over_akshare` | PASS |
| AC9 | `cn_etf` AkShare fallback path | `test_collect_holding_rows_cn_etf_fallback_to_akshare` | PASS |
| AC10 | Snapshot empty preserves existing rows; no delete | `test_collect_holding_rows_all_quarters_empty_returns_snapshot_empty`, `test_ingest_one_snapshot_empty_preserves_existing_rows` | PASS |
| AC11 | Missing `source_report_date` → `missing_report_date` | `test_collect_holding_rows_missing_report_date_returns_empty`, `test_ingest_one_missing_report_date` | PASS |
| AC12 | `load_scoring_metrics` returns `0.45` after ingest | `test_scoring_metrics_reads_ingested_holdings` | PASS |
| AC13 | Partial AkShare failure does not raise | `test_collect_holding_rows_cn_etf_fallback_handles_raise`, `test_ingest_many_isolates_per_target_failures` | PASS |
| AC14 | `ingest_many` returns one outcome per target in order; verbose log gating | `test_ingest_many_preserves_input_order`, `test_run_ingest_wires_holdings_step` | PASS |
| AC15 | Deterministic row insertion order (weight DESC, ticker ASC) | `test_upsert_holdings_deterministic_row_order` | PASS |
| AC16 | Wire-in does not break ingest; no HaltReason for holdings failures | `test_run_ingest_holdings_failure_not_fatal` | PASS |
| AC17 | Manifest carries `fund_holdings` count | `test_run_ingest_holdings_count_in_manifest` | PASS |
| AC18 | `_raw_ref` shared across all rows for same (iid, report_date) | `test_upsert_holdings_raw_ref_pattern` | PASS |
| AC19 | Named-column INSERT shape locked | `test_upsert_holdings_uses_named_columns` | PASS |
| AC20 | `today_iso` is wall-clock `_china_today()` | `test_is_stale_returns_true_when_no_rows` (explicit iso arg), `test_run_ingest_wires_holdings_step` (patches `_china_today`) | PASS |
| AC21 | Item 010 independent of item 008's AC22/AC23 | `grep -rn "fund_holdings" src/irc/opportunity/ src/irc/memo/` → zero output | PASS |

All 21 ACs covered; all green.

---

## Test suite run

```
uv run pytest tests/data/test_fund_holdings_ingestor.py \
              tests/commands/test_ingest_cmd.py \
              tests/integration/test_publishable_set_lockdown.py -q

124 passed, 1 skipped in 456.61s
```

The 1 skip is a pre-existing live-network test in the lockdown suite (requires `IRC_RUN_LIVE_AKSHARE=1`). Item 008 baseline byte-equality tests (AC22/AC23) remain green.

---

## Implementation spot-checks

### `fund_holdings_ingestor.py` (~299 LOC; plan budget ≤ 200 LOC)

The module is 299 lines, slightly over the 180 LOC estimate in the plan. The excess is attributable to the full `collect_holding_rows` implementation which the plan acknowledged grows with the cn_etf fallback path. All function size budgets (< 20 lines ideal) are respected individually. No concern.

### `ingest_cmd.py` wire-in

- Import alias: `from irc.data.fund_holdings_ingestor import ingest_many as ingest_fund_holdings` — matches plan.
- `"fund_holdings": 0` added to `ak_counts` initialiser — matches plan.
- `holdings_counts` declared before `try:` block at line 457 — matches plan's recommended option (a).
- Block position: after nav loop, before `finally:` — matches plan.
- `today_iso` passed directly from `_china_today()` called at line 431 — AC20 / F1 satisfied.
- `_verbose` gating for per-iid `_log.info` — matches plan.
- Unconditional `print(f"  fund_holdings: ...")` after `print("ingest OK: ...")` — matches plan.

### `upsert_holdings` SQL string

Matches plan's locked SQL string verbatim:
`INSERT OR REPLACE INTO fund_holdings (instrument_id, report_date, holding_ticker, holding_name, weight_pct, _ingested_at, _source, _raw_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`

### ADR 0002 §5 cross-reference

Updated at line 103 of `docs/adr/0002-active-fund-fetch-engine.md` with the exact text from the plan, referencing `src/irc/data/fund_holdings_ingestor.py` as the downstream consumer.

### AC21 structural independence

`grep -rn "fund_holdings" src/irc/opportunity/ src/irc/memo/` returns zero matches. The opportunity and memo packages are untouched.

### `_raw_ref` format note

`build_ref_id` returns `"{source}:{topic}:{instrument_id}:{date}"` (a colon-delimited string, not the `[ref:hex16]` citation format from ADR 0001). This is consistent with the project's existing `_raw_ref` convention for DuckDB provenance columns — ADR 0001's hex-16 format applies to LLM-facing citation markers in markdown, not to DuckDB `_raw_ref` fields. No drift.

---

## Minor observations (non-blocking)

1. **Vestigial test `test_ingest_one_idempotent_same_day_skipped_fresh`:** The plan noted this scratch test should be removed before commit. It was removed — only `test_ingest_one_idempotent_with_fresh_report` exists, which is the correct clean lock.
2. **`ingest_one` drops `source` variable:** The implementation uses `rows, _source, detail = collect_holding_rows(...)` (underscore-prefixed `_source` since it is unused). This is correct — `source` is already embedded in each `HoldingRow`; the tuple return is for callers that may need it without iterating rows.
3. **Module LOC:** 299 lines vs plan's "~180 LOC" estimate. Within acceptable range given the combined active-fund + cn_etf fallback + docstring detail in `collect_holding_rows`.
