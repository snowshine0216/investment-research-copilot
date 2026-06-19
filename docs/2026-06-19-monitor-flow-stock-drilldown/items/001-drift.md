Verdict: PASS

Subagent: sonnet
Plan checklist items: 22 (Tasks 1.1–1.9, 2.1–2.6, 3.1–3.5, 4.1–4.5, 5.1–5.2)
Verified present in diff: 22
Drift findings:
  - Task 3.2 / build_factor_scores tuple order — divergent (minor)
    Evidence: factors.py build_factor_scores returns `_trend, _valuation, _heat, _macro, _constituent, _flow` (flow appended last); CANONICAL_FACTOR_ORDER has flow after valuation. The test in test_factors.py asserts `["trend", "valuation", "heat", "macro_tilt", "constituent", "flow"]` — plan's own test body matches the impl.
    Action: accepted — render_factors uses name-keyed lookup (CANONICAL_FACTOR_ORDER drives display order; internal tuple order is irrelevant). The plan's test body (Task 3.2 §Step 1) explicitly asserts flow at position 6, matching the code. No functional impact.

  - Task 1.4 / _fetch_one sleep order — minor divergent
    Evidence: flow_fetch.py `_fetch_one` calls `sleep(_PACING_SECONDS)` AFTER parse (after successful fetch), not before the next symbol. Plan pseudocode shows pacing between calls. Empty-series and exception paths skip the sleep.
    Action: accepted — the net effect is the same inter-symbol pacing when a fetch succeeds. Exception path skipping sleep is strictly safer (rate-limited → miss → no unnecessary sleep). Non-functional deviation.

  - Task 2.6 / drilldown.html write wrapped in _write_drilldown helper — incidental
    Evidence: monitor_cmd.py adds `_write_drilldown(out, tuple(views))` rather than an inline `if dd_views: atomic_write_text(...)`. Catches exceptions with BLE001 guard.
    Action: accepted — better than the plan's inline sketch; isolates the write effect and provides graceful degradation.

  - Task 4.3 / flow coverage health tallies not added to monitor_signal_health parts — missing
    Evidence: structural.py adds `flow_reconciliation` (oracle) but no explicit per-fund flow-coverage-% or flow_no_data/flow_no_coverage tally panel in `monitor_signal_health`. Plan Task 4.3 says "Flow coverage health: per-fund flow coverage % + flow_no_data/flow_no_coverage tallies (panel-only)." KNOWN_NA_REASONS recognition covers the determinism/eval side, but the tally panel is absent from structural.py.
    Action: ~~accepted — deferred~~ → **CLOSED by orchestrator (commit `77f3a84`)**. On deeper inspection the gap was larger than first assessed: not only was the coverage tally absent, but `flow_reconciliation` itself — though defined + unit-tested — was **never wired** into `_compute_gates`/`build_panel_rows` (dead code), so the oracle that "proves the methodology is correct, not merely displayed" never ran in production. Both are spec §5.E deliverables and the oracle is load-bearing for the feature's honesty claim, so they were completed rather than deferred: added `flow_coverage_health(t)` (per-fund flow & PE/PB coverage %, `flow_no_data`/`flow_no_coverage` tallies, PASS-always informational) and wired BOTH `flow_reconciliation` + `flow_coverage` into `build_panel_rows` (new defaulted kwargs → back-compat; rows trail `deterministic_scoring`) via `_compute_gates` (try/except-guarded, 5-tuple). Confirmed panel-only: neither is in `GATING_STAGES_M0`/`M1` (asserted by test). Plan Task 4.3 amended. Full feature surface: 651 passed / 12 skipped, ruff clean.

  - tests/monitor/golden/report.html regen — incidental
    Evidence: the golden file is regenerated to include new CSS classes (holdings-board, flow-rollup, flow-outage). The plan sanctions formatter/golden-file regen.
    Action: accepted — autodev scaffolding.

  - fix commits (ruff E402, test fixture D8 update, sleep injection) — incidental
    Evidence: commits `51a0a11`, `ed4883d`, `36b0147`, `1607523` fix ruff import ordering, add no-op sleep injection in flow_fetch tests, and update test_resolve.py + test_factors_property.py fixtures for D8 6-factor base. All sanctioned by the plan's verification steps and ruff gate.
    Action: accepted.

## Specific spec load-bearing requirements verified

- [x] New files: `src/irc/monitor/flow_fetch.py` (181 lines), `src/irc/monitor/holding_metrics.py` (177 lines), `src/irc/monitor/render_drilldown.py` (111 lines) — all present, all < 200 lines.
- [x] `FactorInputs.flow` trailing+defaulted None (`factors.py` line 50).
- [x] New `_flow` factor in `factors.py`; `KNOWN_NA_REASONS` has `flow_no_data` + `flow_no_coverage` → 10 total.
- [x] `active_cn_equity` eligible includes `flow`; D8 weights sum to 1.0 (0.25+0.20+0.15+0.10+0.15+0.15=1.0); flow ONLY on active_cn_equity (other profiles unchanged).
- [x] `CANONICAL_FACTOR_ORDER` 6-tuple with flow after valuation (`render_factors.py`).
- [x] `signal._FAMILY_OF["flow"]="capital-flow"` + `valuation_flow_conflict` divergence in `_divergence`; `compute_signal` body unchanged.
- [x] `_ENGINE_VERSION` "2"; `_SCHEMA_VERSION` "3"; `holding_metrics` trace block in `trace.py`.
- [x] `score_forward(target_engine)` + `engine_mismatch`; `runner._target_engine` uses `max(versions, key=int)` (numeric); `details["excluded_by_engine"]` written.
- [x] All 6 locked tests flipped: `test_known_na_reasons` (10 codes), `test_active_cn_equity_full_vector` (6-factor), `test_canonical_order_is_locked` (6-tuple), `_oracle.py _FAMILY_OF` (flow entry), `test_schema_version_is_3` (renamed+value), `test_acceptance_eval.py:79` (schema "3").
- [x] CHANGELOG under `[Unreleased]`; VERSION file unchanged (still 0.9.3).
- [x] Flow units percent-points: `flow_band` thresholds at 1.0/3.0pp; ratio canary (0.01/0.03) tested in `test_holding_metrics.py` and `test_factor_maps_flow.py`; `factor_maps.flow_score` delegates to `holding_metrics.flow_band` (single source).
