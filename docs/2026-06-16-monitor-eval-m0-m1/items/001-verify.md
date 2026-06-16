Verdict: PASS

Subagent: sonnet
Source: /verify
Entry points exercised:
  - `uv run irc eval monitor_impact` (no IRC_RUN_LIVE_LLM_EVAL) → rc=3 [live CLI]
  - `uv run irc eval monitor_narrative` (no IRC_RUN_LIVE_LLM_EVAL) → rc=3 [live CLI]
  - `uv run irc eval --all` → monitor_signal in output; monitor_impact/narrative absent [live CLI]
  - `uv run irc eval monitor_signal` (no eval_trace.json today) → FAIL (no input file) rc=2 [live CLI]
  - `uv run pytest -q tests/monitor/test_acceptance_eval.py tests/commands/test_monitor_cmd_trace.py tests/commands/test_monitor_cmd_eval_wiring.py` → 6 passed [integration test]
  - `uv run pytest -q tests/monitor/eval/` → 53 passed [unit test]
  - `uv run pytest -q tests/evals/test_registry.py tests/evals/test_missing_input_helper.py tests/evals/test_status.py tests/evals/test_latest_report.py` → 31 passed [unit/integration test]
  - `uv run pytest -q tests/evals/test_monitor_signal_metrics.py tests/evals/test_monitor_signal_runner.py` → 8 passed [unit test]
  - `uv run pytest -q tests/commands/test_eval_cmd.py tests/commands/test_gate_wiring.py` → 20 passed [integration test]
  - `uv run pytest -q tests/monitor/test_render_html_eval.py` → 8 passed [integration test]
  - `uv run pytest -q tests/spend/test_scope.py` → 6 passed [unit test]

Observed behavior:
  - A. eval_trace.json serialization — test_run_monitor_writes_eval_trace_and_ledger asserts file exists at outputs/<date>/monitor/eval_trace.json with top-level keys {schema_version,engine_version,run_date,funds}; test_per_fund_schema_keys asserts all per-fund subkeys; test_round_trip_json_serializable asserts dump→reload equality across a good+degraded fixture. build_eval_trace is a pure function with the required signature. [integration test + unit test]
  - B. Degraded NAV — test_degraded_nav_no_indexerror_and_nulls: nav_series=() yields nav_acc=None, obs_count=0, max_gap_days=None, latest_unit_nav=0.0 without raising. test_degraded_nav_fund_is_eval_gated_with_null_nav_acc: fund with nav_series=() is EVAL_GATED in trace AND ledger row carries nav_acc=null. [integration test]
  - C. Unified evidence pool — test_unified_pool_contains_macro_and_constituent_ids: overlapping citation_ids appear once, both macro+constituent ids present. test_constituent_impact_citation_resolves_against_unified_pool: constituent-only citation_id resolves to PASS. FundTraceBundle frozen dataclass with correct fields confirmed. [unit test]
  - D. Pure cores — all 53 tests in tests/monitor/eval/ pass covering types.py (HealthStatus/Badge/StageHealth/GateDecision/FundTraceBundle), structural.py (signal_consistency/citation_integrity/nav_quality/monitor_signal_health all branches), staleness.py (absent/skipped/stale/fresh), latest_stage_report (absent→None; multiple dates→newest; SKIPPED→UNKNOWN via resolve_health), panel.py (snapshot). [unit test]
  - E. gate.py — GATING_STAGES_M0=frozenset({"monitor_signal"}) confirmed in source; apply_eval_gate tests all branches (FAIL→gated/suppressed, WARN/UNKNOWN→caveated, clean→validated); published_state: NO_CALL when status!="ok" wins over EVAL_GATED. [unit test]
  - F. forward_log.py — ledger_row fields confirmed including nav_basis="coalesce(nav_acc,nav)"; append_ledger uses open(path,"a"), two-batch test asserts both survive; write failure is swallowed (tested via unwritable path); latest_per_key dedup by (run_date,fund_id) keeping max written_at. [unit test]
  - G. evals/monitor_signal/ — 8 tests pass: oracle_signal_match, citation_resolution, nav_completeness metrics unit-tested; runner test: good fixture→PASS rc=0; tampered composite→FAIL rc=2; missing input→FAIL rc=2 "no input file" (confirmed via live CLI). [unit test + live CLI]
  - H. Shared-infra — "SKIPPED" added to Status literal; worst_status unchanged (tested); EVAL_RC_SKIPPED=3 and skipped_report confirmed in missing_input.py; live_gated in Lifecycle; monitor_signal in active_suite; monitor_impact/narrative as live_gated placeholders with in_all_suite=False; latest_report.py exists. [unit test]
  - I. eval_cmd live_gated SKIPPED + spend gate — live CLI: `irc eval monitor_impact` without IRC_RUN_LIVE_LLM_EVAL → prints "monitor_impact eval: SKIPPED (env absent; not executed)", rc=3, report.json written with overall=="SKIPPED" (confirmed by reading outputs/2026-06-16/evals/monitor_impact/report.json). test_live_gated_skip_does_not_import_runner confirms no import of missing module. test_live_gated_gate_blocks_before_runner: monkeypatched gate→5 returns 5, runner never called. eval-live scope: tasks=={monitor_impact,monitor_narrative}, search_providers==frozenset(). completeness test test_every_llm_yaml_task_is_mapped_somewhere passes. [live CLI + integration test]
  - J. Live-run integration + render — _process_fund returns 3-tuple (view, cost_history, FundTraceBundle); test_run_monitor_still_renders_when_trace_write_fails: injected OSError on eval_trace.json → rc=0, report.html still written. test_stale_nav_fund_is_eval_gated_and_panel_names_it: stale NAV fund→EVAL_GATED in trace and "older than" in gate.reason, "EVAL-GATED" + "Validation" in HTML. Render: eval-gated CSS class, validated ✓ chip, caveated ⚠ chip, NO_CALL wins over EVAL_GATED when status!="ok", Validation panel with monitor_signal row, panel overall not PASS when gate suppressed. [integration test]
  - K. Acceptance guards — test_eval_trace_emitted_and_ledger_uses_coalesce_basis: asserts eval_trace.json exists AND all ledger rows carry nav_basis=="coalesce(nav_acc,nav)". [integration test]

Failures: none
