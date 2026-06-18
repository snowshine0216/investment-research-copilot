Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct entry-point exercise + integration test suite
Entry point exercised:
  - `uv run pytest tests/monitor/test_valuation.py tests/monitor/test_valuation_wiring.py tests/monitor/test_factor_maps.py tests/monitor/test_known_na_reasons.py -v`
  - `uv run pytest tests/evals/test_monitor_signal_runner.py tests/evals/test_monitor_signal_metrics.py -q`
  - `uv run python -c "from irc.commands.monitor_cmd import _process_fund, run_monitor; from irc.monitor.valuation import resolve_valuation_state; print('imports OK')"`
  - `uv run irc monitor --help`
  - Direct `resolve_valuation_state` exercise against seeded in-memory DuckDB (4 scenarios below)

Observed behavior:

  - AC1 — `src/irc/monitor/valuation.py` exists with `resolve_valuation_state(fund, *, con, root) -> ValuationResolution` (frozen dataclass: state, cached, reason); `percentile_to_valuation_state` applies shared `_band` thresholds DRY; None/NaN → None. All 10 band-boundary parametrize tests + 2 None/NaN tests PASS. `ValuationResolution` is frozen (FrozenInstanceError test PASS).

  - AC2 — `_tracked_index_for_fund` reads `instruments.tracked_index` (same table/column the opportunity layer uses). Verified: seeding `csi300` in instruments → index path taken; `tracked_index=None` in instruments → look-through stub. `test_index_anchored_unactivated_sector_is_na` (un-activated sector slug → N/A) PASS.

  - AC3 — `_VALUATION_MAP` in `factor_maps.py` contains exactly five states: `cheap→1.0, reasonable_low→0.5, fair→0.0, expensive→-0.5, very_expensive→-1.0`. All 5 state tests + unrecognized-state-returns-None test PASS (6 parametrize cases in `test_factor_maps.py`).

  - AC4 — `monitor_cmd.py:582` calls `val = resolve_valuation_state(fund, con=con, root=root)` and passes `valuation_state=val.state, valuation_cached=val.cached` to `FactorInputs`. Import verified; wiring integration test (`test_index_fund_gets_real_valuation_state`, `test_gold_and_qdii_global_valuation_stay_profile_ineligible`) PASS.

  - AC5 — Direct exercise (4 scenarios):
      - TEST 1 (csi300 index anchored, 200 rising rows): `ValuationResolution(state='very_expensive', cached=True, reason=None)` — real state, cached=True.
      - TEST 2 (009225, no instruments row → look-through stub): `ValuationResolution(state=None, cached=False, reason='valuation_no_anchor')` — honest N/A, CORRECT-BY-DESIGN (AC5 strike-through: `009225`'s `china_internet` is not in `_INDEX_VALUATION_KEYS`; `test_china_internet_anchor_is_na_documented_gap` PASS).
      - TEST 3 (tracked_index=None in instruments → look-through stub): `ValuationResolution(state=None, cached=False, reason='valuation_no_anchor')` — honest N/A stub (item 002 fills in).
      - TEST 4 (instruments table absent → P0-fix degrade): `ValuationResolution(state=None, cached=False, reason='valuation_no_anchor')` — no raise, graceful N/A.

  - §6 invariants:
      - `gold`/`qdii_global` stay `profile_ineligible`: `test_gold_and_qdii_global_valuation_stay_profile_ineligible` PASS (wiring integration).
      - All N/A reasons in `KNOWN_NA_REASONS`: `test_known_na_reasons_is_exactly_the_eight_codes`, `test_every_na_branch_emits_a_known_reason`, `test_every_known_reason_is_reachable_from_a_branch` all PASS.
      - Determinism guard: `tests/evals/test_monitor_signal_runner.py` + `tests/evals/test_monitor_signal_metrics.py` — 8 passed.

  - CLI / import: `imports OK`; `uv run irc monitor --help` loads cleanly.

  - Full test count: 37 passed (valuation+wiring+factor_maps+known_na_reasons) + 8 passed (determinism guard) = 45 total. 0 failures.

Failures: none
