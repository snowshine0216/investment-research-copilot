Verdict: PASS

## Subagent
claude-sonnet-4-6

## Source
Branch: `claude/narrative-coverage-markdown-002` (confirmed via `git branch --show-current`)

## Entry points exercised

- `uv run irc narrative --help`
- `uv run python -c "import irc.narrative.analyze, irc.commands.narrative_autobuild, irc.commands.opportunity_cmd, irc.fundamentals.snapshot_cache; from irc.fundamentals.snapshot_cache import load_latest_nav_cached; from irc.opportunity.lookthrough import QDII_KINDS; print('imports OK', QDII_KINDS)"`
- `grep -rn "from irc.commands|import irc.commands" src/irc/narrative/`
- `uv run irc narrative compute_metals --analyze --db /tmp/nope-irc.duckdb --out /tmp/irc-verify-002`
- `grep -c 基金概況 src/irc/commands/narrative_autobuild.py src/irc/narrative/analyze.py`
- `uv run pytest tests/narrative/ tests/fundamentals/ tests/opportunity/ -q` → **906 passed, 18 skipped**

## Observed behavior — AC → evidence

**AC1 — Fund-level eligibility by resolved lookthrough kind.**
Test: `test_fund_level_eligible_only_for_provider_symbol_kinds` (autobuild) + `test_fund_level_missing_excludes_active_and_bare_rows`.
PASS — build invoked for cn_etf/us_etf with provider_symbol; excluded for cn_equity_fund and bare QDII.

**AC2 — Eligibility decided before any I/O, via instr_index.**
Test: `test_fund_level_target_resolves_via_instr_no_io`.
PASS — eligibility resolved from in-memory `Instrument` via `map_lookthrough(_build_input(...))`, zero fetch calls asserted.

**AC3 — Cache-presence gate (no refetch), latest-nav/ scan.**
Test: `test_fund_level_missing_excludes_cached_nav` + `test_passive_skips_when_nav_cache_present`.
PASS — fund with pre-seeded nav/ cache file triggers zero `build_snapshot` calls.

**AC4 — Effects at edges; analyze_fund read-only.**
Layering check: `grep -rn "from irc.commands|import irc.commands" src/irc/narrative/` → `NONE (narrative imports nothing from commands ✓)`.
Test: `test_analyze_fund_fund_level_issues_no_build` (analyze.py).
PASS.

**AC5 — analyze_fund dispatches on lookthrough kind.**
Tests: `test_load_snapshot_for_row_dispatches_active` + `test_load_snapshot_for_row_dispatches_fund_level` + `test_analyze_fund_wires_cache_and_builder`.
PASS — cn_etf row with pre-seeded nav/ cache produces OpportunityRow from FundLevelSnapshot branch.

**AC6 — Dual-leg gate → real thesis_state (Policy-B-free).**
Test: `test_analyze_recovers_passive_etf_with_real_thesis` (narrative_cmd.py) — stubbed builder returning two-leg FundLevelSnapshot asserts `thesis_state == "intact"` and `position_risk_level != "insufficient"`.
PASS.

**AC7 — Partial-evidence honesty.**
Test: `test_analyze_passive_one_leg_is_insufficient` — one-leg FundLevelSnapshot yields `thesis_state == "evidence_insufficient"` → `position_risk_level == "insufficient"`.
PASS.

**AC8 — Default-on with shared IRC_NARRATIVE_AUTOBUILD kill-switch.**
Tests: `test_passive_kill_switch_disables_build` + `test_passive_autobuild_builds_eligible_missing`.
PASS — same env var governs both active and passive autobuilds.

**AC9 — Build + cache-write shape mirrors opportunity fund-level path.**
Tests: `test_fund_level_build_one_writes_nav_cache` (writes via `write_nav_cache` with `cache_probed_at`) + `test_fund_level_build_one_skips_qdii_sentinel` + `test_fund_level_build_one_skips_empty_quarter`.
PASS.

**AC10 — Per-fund failure degrades, never crashes.**
Tests: `test_fund_level_build_one_swallows_exception` + `test_analyze_passive_build_failure_degrades` — builder raises for one fund, run still returns rc=0 with full report, that fund is `insufficient`.
PASS.

**AC11 — Fetch budget enforced pre-build (shared plan).**
Tests: `test_shared_budget_guard_raises_before_any_build` + `test_shared_budget_counts_active_and_fund_level_together` + `test_fund_level_build_one_reraises_fetch_budget`.
CLI: `test_run_narrative_returns_3_on_fetch_budget_exceeded`.
PASS — single shared `FetchPlan(active_fund_misses=Na, fund_level_misses=Np)` costed at 4 calls each; `fetch_budget_exhausted` never written to evidence_gaps: test `test_module_never_writes_budget_exhausted_sentinel` passes.

**AC12 — Determinism / idempotence.**
Tests: `test_passive_analyze_idempotent_second_run_zero_builds` (zero builds on second run) + `test_run_twice_byte_identical` (byte-identical JSON).
PASS.

**AC13 — No live network in unit tests.**
Test: `test_passive_autobuild_no_live_network_marker` verifies all new tests stub their builders.
All 105 narrative tests pass without `IRC_RUN_LIVE_AKSHARE=1`.
PASS.

**AC14 — Active path unchanged; existing suites green.**
Tests: `test_load_snapshot_for_row_dispatches_active` + `test_skips_etf_rows_builds_only_active` confirm cn_equity_fund rows still use active loader and are never built by passive path.
All 905 non-skipped tests in `tests/narrative/ + tests/fundamentals/ + tests/opportunity/` pass.
PASS.

## Offline CLI checks

| Check | Result |
|---|---|
| `irc narrative --help` shows `--analyze` flag | PASS — flag present, no import error |
| Import health: all 5 modules + QDII_KINDS | PASS — `imports OK ('qdii_us', 'qdii_hk', 'qdii_global')` |
| Layering: narrative imports nothing from commands | PASS — `NONE (narrative imports nothing from commands ✓)` |
| Error path: rc=2, no traceback, no "fundamentals snapshot" | PASS — `EXIT_CODE=2`, clean error string |
| Forbidden 基金概況 count in both files | PASS — `0 0` |

## Failures

None. 0 failures across all 14 ACs.
