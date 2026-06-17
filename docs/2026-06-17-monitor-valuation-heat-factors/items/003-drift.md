Verdict: PASS

Subagent: sonnet / Plan checklist items: 31 / Verified present in diff: 31 / Drift findings: 0

---

## Plan checklist coverage

### Task 0 (baseline verification)
- Task 0 is verification-only, not a code artifact. No diff expected. Accepted.

### Task 1 — `parse_purchase_status` (pure parse + `heat_fetch.py` creation)
- `src/irc/monitor/heat_fetch.py` created: PRESENT (diff confirms new file, 102 lines).
- Module docstring notes CN direct / AUM-Δ deferred: PRESENT (lines 1–14 of new file).
- `_RESTRICTION_CAP_THRESHOLD = 1e8`, `_OPEN_STATUSES = frozenset({"开放申购"})`: PRESENT.
- Column constants `_CODE_COL`, `_STATUS_COL`, `_CAP_COL`: PRESENT.
- `_norm_code`: PRESENT (zfill(6), str+strip).
- `_row_for`: PRESENT (pure, None on missing code column or no match).
- `_cap_below_threshold`: PRESENT (returns False not None on missing/unparseable cap).
- `parse_purchase_status(table, fund_id) -> bool | None`: PRESENT. Signature, None-table guard, missing-column guard, OR logic, all match plan exactly.
- `tests/monitor/test_heat_fetch.py` created: PRESENT (172 lines).
- All 12 plan-prescribed parse test cases present verbatim: PRESENT (`test_open_status_high_cap_not_restricted`, parametrized `test_non_open_status_is_restricted` with 6 statuses, `test_open_status_low_cap_is_restricted`, `test_cap_exactly_at_threshold_not_restricted`, `test_fund_absent_returns_none`, `test_missing_status_column_returns_none`, `test_missing_cap_column_falls_back_to_status_only`, `test_missing_code_column_returns_none`, `test_none_table_returns_none`, `test_empty_table_returns_none`, `test_unparseable_cap_with_open_status_not_restricted`, `test_code_zero_pad_match`).

### Task 2 — `fetch_purchase_table` + `heat_inputs_for` edge (never-raises tests)
- `fetch_purchase_table(fetch=None) -> pd.DataFrame | None`: PRESENT (lazy `import akshare as ak` inside body, `# local import` comment matches house pattern).
- Never-raises: bare `except Exception` + `_log.warning(..., exc_info=True)` + `return None`: PRESENT.
- Empty/non-DataFrame returns None with warning: PRESENT.
- `heat_inputs_for(fund_id, *, purchase_table) -> tuple[bool|None, float|None]`: PRESENT. Returns `(parse_purchase_status(purchase_table, fund_id), None)`.
- Task 2 tests (`test_fetch_returns_table_from_injected_fetch`, `test_fetch_returns_none_when_fetch_raises`, `test_fetch_returns_none_on_empty_frame`, `test_fetch_returns_none_on_non_dataframe`, `test_heat_inputs_for_open_fund`, `test_heat_inputs_for_restricted_fund`, `test_heat_inputs_for_none_table_yields_none_restricted`, `test_heat_inputs_for_absent_fund_yields_none_restricted`): all PRESENT in `tests/monitor/test_heat_fetch.py`.

### Task 3 — heat scoring integration tests
- Integration helper `_heat_score_for` and four integration tests (`test_restricted_true_yields_eligible_crowded_heat`, `test_restricted_false_yields_eligible_calm_heat`, `test_restricted_none_yields_heat_no_data`, `test_gold_profile_heat_still_eligible_when_restricted`): all PRESENT in `tests/monitor/test_heat_fetch.py`.

### Task 4 — double-gated live probe
- `tests/monitor/test_heat_fetch_live.py` created: PRESENT (52 lines).
- `pytestmark` with `pytest.mark.live_akshare` AND `pytest.mark.skipif(os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1", ...)`: PRESENT. Both gates confirmed.
- `_MONITOR_IDS` list of 10 ids: PRESENT.
- `test_purchase_table_reachable_and_all_ids_parse` and `test_missing_id_parses_to_none_gracefully`: PRESENT.
- `fetch_purchase_table()` called with no args (lazy-import path): PRESENT.

### Task 5 — `monitor_cmd.py` wiring
- Import `from irc.monitor.heat_fetch import fetch_purchase_table, heat_inputs_for` added after `from irc.data.duckdb_helper import connect`: PRESENT (diff line `+from irc.monitor.heat_fetch import fetch_purchase_table, heat_inputs_for`).
- `_process_fund` signature adds `purchase_table=None` keyword: PRESENT (`def _process_fund(fund: MonitorFund, cfg, root: Path, llm_config, *, con=None, purchase_table=None,)`).
- `restricted, aum_delta_pct = heat_inputs_for(fund.id, purchase_table=purchase_table)` added just before `inp = FactorInputs(...)`: PRESENT.
- Two hardcoded `restricted=None, aum_delta_pct=None` lines replaced with live variables: PRESENT. Valuation lines (`valuation_state=val.state, valuation_cached=val.cached`) left untouched: CONFIRMED (not in diff hunk).
- `fetch_purchase_table()` called once in `run_monitor` after the `con` block: PRESENT (`purchase_table = fetch_purchase_table()  # ONE akshare call/run; None on failure → heat_no_data`).
- Warning log when `purchase_table is None`: PRESENT.
- `_process_fund(...)` threaded with `con=con, purchase_table=purchase_table`: PRESENT (multi-line form).
- `tests/commands/test_monitor_cmd_heat.py` created with 3 plan-specified tests: PRESENT (`test_process_fund_restricted_fund_gets_crowded_heat`, `test_process_fund_open_fund_gets_calm_heat`, `test_process_fund_no_table_defaults_to_heat_no_data`).
- Task 5 Step 5 — `test_monitor_cmd_eval_wiring.py` lambda fixed to `**kw`: PRESENT (`lambda fund, cfg, root, llm, **kw:`). `fetch_purchase_table` stubbed to `lambda: None` in the same `_patch_pipeline`: PRESENT.
- Plan Step 7 note: `fetch_purchase_table` stub also added to `tests/monitor/test_acceptance_eval.py` `_patch`: PRESENT (`monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)`).

### Task 6 — determinism / size-budget (verification only)
- `factor_maps.py` NOT in the diff: CONFIRMED (git diff --name-only shows 0 changes to factor_maps.py or factors.py).
- `http_proxy.py` NOT in the diff: CONFIRMED.
- No new N/A reason codes: CONFIRMED (factors.py not modified; heat_no_data pre-exists).
- `heat_fetch.py` line count: 102 lines (well under 200): CONFIRMED.

---

## Incidentals accepted

- `tests/monitor/test_acceptance_eval.py` hunk — adds `monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)`: accepted. Plan Task 5 Step 7 explicitly calls for this proactive stub in `_patch` / `_patch_pipeline` to keep the offline suite from hitting the network. Functional consequence of the wiring, not scope creep.
- Import ordering in `monitor_cmd.py` — the new `heat_fetch` import lands between `duckdb_helper` and `valuation` alphabetically: incidental, accepted.

---

## Scope-creep scan

No diff hunks exist outside the 7 plan-listed files. No new public symbols beyond those specified. No new N/A reason codes. No proxy plumbing added. Gold/qdii_global eligibility paths untouched (factor_maps.py not modified). The `_patch_pipeline` stub for `fetch_purchase_table` in `test_monitor_cmd_eval_wiring.py` and `test_acceptance_eval.py` is explicitly called out in Task 5 Step 7. No scope creep found.
