Verdict: PASS

Subagent: sonnet
Source: Fallback used: Bash CLI + pytest
Entry point exercised:
  - `uv run irc narrative --help`
  - `uv run irc narrative compute_metals --analyze --db /tmp/does-not-exist-irc.duckdb --out /tmp/irc-verify-001`
  - `uv run python -c "... _narrative_autobuild_on() ..."`
  - `grep -c 基金概況 src/irc/commands/narrative_autobuild.py`
  - `uv run pytest tests/narrative/test_narrative_autobuild.py tests/narrative/test_narrative_cmd.py -v` (29 passed)

Observed behavior:

  - AC1 (eligibility: cn_equity_fund only) — test_eligible_only_for_cn_equity_fund PASSED; test_skips_etf_rows_builds_only_active PASSED: build list == ["000A"], cn_etf never built.
  - AC2 (cache-presence gate: probe resolved quarter) — test_skips_when_resolved_quarter_cache_present PASSED: zero build calls when cache pre-seeded for resolved quarter.
  - AC3 (effects at edges: analyze_fund unchanged) — test_analyze_invokes_autobuild_with_resolved_quarter PASSED; existing test_analyze.py suite unmodified and green.
  - AC4 (default-on + kill-switch) — offline: `off= False, on= True` observed; test_autobuild_on_default_true PASSED; test_autobuild_off_when_env_zero PASSED; test_kill_switch_disables_build PASSED.
  - AC5 (build+cache-write shape mirrors opportunity) — test_build_one_writes_cache_with_probed_at PASSED (snap.cache_probed_at set, root passed); test_build_one_skips_write_on_empty_quarter PASSED (written == []).
  - AC6 (per-fund failure degrades to insufficient, rc=0) — test_build_one_swallows_builder_exception PASSED; test_analyze_per_fund_error_yields_partial_results PASSED: rc=0, report has 2 funds, failed fund position_risk_level="insufficient".
  - AC7 (fetch budget enforced pre-build) — test_budget_guard_raises_before_any_build PASSED: FetchBudgetExceeded raised before any build; test_run_narrative_returns_3_on_fetch_budget_exceeded PASSED: rc=3 with actionable stderr (IRC_FETCH_BUDGET, IRC_NARRATIVE_AUTOBUILD=0, shortlist path); test_module_never_writes_budget_exhausted_sentinel PASSED.
  - AC8 (idempotence / byte-identical second run) — test_analyze_idempotent_second_run_zero_builds PASSED: build_count["n"]==1 after two runs; first==second (byte-identical JSON).
  - AC9 (corrected error string) — offline CLI: RC=2, no Python traceback; stderr = "ERROR: --analyze needs data/local.duckdb (run `irc ingest`) and a snapshot quarter under data/fundamentals/. Active-fund snapshots are auto-built during a successful --analyze..."; grep: "fundamentals snapshot" absent, "irc ingest" present; test_analyze_missing_db_error_string_is_corrected PASSED.
  - AC10 (no live network in unit tests) — all 29 tests pass without IRC_RUN_LIVE_AKSHARE=1; no live markers observed in test_narrative_autobuild.py or test_narrative_cmd.py; grep for 基金概况 in narrative_autobuild.py = 0.
  - AC11 (recovers active funds end-to-end) — test_analyze_recovers_active_fund_with_real_thesis PASSED: fund["thesis_state"] != "evidence_insufficient", thesis_evidence non-empty.

Failures: none
