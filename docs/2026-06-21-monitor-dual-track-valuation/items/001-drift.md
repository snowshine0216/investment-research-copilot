Verdict: PASS

Subagent: sonnet
Plan checklist items: 31 (Tasks 1.1–1.4, 2.1–2.6, 3.1–3.5, 3.6 sweep, 4.1–4.5 incl. ADR + final verification; file-structure Create/Modify/Delete list; locked-test edits)
Verified present in diff: 31
Drift findings:
  - Task 2.2/2.3/2.6 + constants — accepted (plan-sanctioned extraction to `_dual_track.py`)
    Evidence: `src/irc/monitor/_dual_track.py` (new file, 67 lines); `holding_metrics.py` re-exports via `from irc.monitor._dual_track import ...  # noqa: F401 (re-exported for tests)`; test imports from `holding_metrics` still resolve. `holding_metrics.py` stays under 200 lines with extraction.
    Action: accepted — plan §2.3/§2.6 size-budget note says "extract … if over 200 lines"; CLAUDE.md <200-line budget makes this plan-sanctioned. Tests import `industry_band, _FALSE_CHEAP_RICHNESS, _SELF_W, _INDUSTRY_W, _MONITOR_COVERAGE_FLOOR, dual_track_score, DualTrack` from `holding_metrics` (re-exported), matching plan test contract exactly. Note: `_MONITOR_COVERAGE_FLOOR` stays in `holding_metrics.py` (not extracted to `_dual_track.py`) — correct, it belongs to the aggregate layer not the scoring layer.

  - Task 4.2 `_compute_gates` 5-tuple → 7-tuple — confirmed planned
    Evidence: `monitor_cmd.py:432` signature `-> tuple[tuple[GateDecision, ...], dict, dict, dict, dict, dict, dict]`; callers `test_gate_flip_m1.py` (3 sites, lines 94/111/125) and `test_monitor_cmd_drilldown.py` (line 159) updated to unpack `_vr_h, _vc_h`. Plan Task 4.2 §5 "Wire the two new healths into the command panel" specifies exactly this extension.
    Action: accepted — planned.

  - Task 3.1 `test_unknown_fund_no_instrument_row_is_na` renamed/updated — confirmed matches short-circuit design
    Evidence: `tests/monitor/test_valuation.py` — old test `test_lookthrough_branch_is_na_stub` (which checked `reason == "valuation_no_anchor"`) is replaced by `test_unknown_fund_no_instrument_row_is_lookthrough` + `test_lookthrough_branch_returns_path_lookthrough`, both asserting `res.path == "lookthrough"` and `res.reason is None`. `valuation.py:_resolve` returns `ValuationResolution(None, False, None, path="lookthrough")` for the non-index path — reason=None is correct for the short-circuit (no data miss; the factor N/A will be determined by aggregate_valuation in _process_fund). The factor-level `valuation_no_anchor` is preserved via `resolve_valuation_state` degrading to it when `val.path == "lookthrough" and not holding_metrics` (see `test_qdii_009225_stays_valuation_no_anchor_via_state_path` in `test_monitor_cmd_valuation.py`).
    Action: accepted — matches Task 3.1 short-circuit design.

  - Task 4.1 test `HoldingMetric` weight 12.0→50.0 — confirmed semantic intent preserved
    Evidence: `tests/monitor/eval/test_trace.py:test_trace_emits_holding_metrics_block` uses `weight_pct=50.0` (changed from 12.0). Plan note: "12.0 gave NAV coverage 0.12 < 0.40 floor → aggregate None; 50.0 ≥ floor". The test now asserts `block["valuation_aggregate"]["value"] == pytest.approx(-0.7)` (non-None), which requires coverage ≥ 0.40. Semantic intent (assert a computable valuation_aggregate) is preserved — the weight change is the minimum needed to satisfy the NAV floor invariant in the new aggregate logic.
    Action: accepted — plan-sanctioned.

  - Task 3.5 `valuation_rollup_html` not wired into `drilldown_section_html` / `drilldown_page_html`
    Evidence: `render_drilldown.py:drilldown_section_html` (line 140–147) only calls `holdings_board_html + flow_rollup_html`; `valuation_rollup_html` is implemented and tested but not called from the HTML page. `monitor_cmd._write_drilldown` still passes a 5-tuple (line 393).
    Action: accepted — plan Task 3.5 (line 1924) explicitly says: "The `drilldown_page_html` views tuple stays `(fund_id, name_cn, metrics, agg, signal)` for back-compat … Keep the existing 5-tuple if simpler; the board columns + badge are the locked deliverable." The function is built and tested; wiring into the HTML page is OPTIONAL per plan.

  - Critical checks — all present in diff:
    - `ValuationResolution.path` trailing-defaulted ("index"): `valuation.py` — `path: Literal["index", "lookthrough"] = "index"` ✓
    - look-through short-circuit (no portfolio-harmonic compute): `_resolve_lookthrough` deleted from `valuation.py`; `lookthrough.py` + `test_lookthrough.py` deleted ✓
    - `_resolve_lookthrough` deleted, `lookthrough.py` deleted: confirmed in diff ✓
    - `factors._valuation` numeric path via `valuation_aggregate`: `factors.py` lines +72–+78 ✓
    - `FactorInputs.valuation_aggregate` trailing field: `factors.py` line +56 ✓
    - `valuation_no_data` + `valuation_no_coverage` in `KNOWN_NA_REASONS` (12 total): `factors.py` KNOWN_NA_REASONS block; `test_known_na_reasons.py` updated to assert 12 codes ✓
    - reachable branches: `_valuation` has both `agg.reason == _NA_VALUATION_NO_COVERAGE_FACTOR` and fallback `_NA_VALUATION_NO_DATA_FACTOR` branches ✓
    - `industry_no_data`/`false_cheap_clamp` NOT in `KNOWN_NA_REASONS`: only in `_dual_track._REASON_*` (per-stock) ✓
    - `_process_fund` feeds `valuation_aggregate` ONLY when `path=="lookthrough"` AND `holding_metrics` non-empty: `monitor_cmd.py` line +696–+700 `if val.path == "lookthrough" and holding_metrics` ✓
    - valuation over full basket, flow stays top-5: `_build_full_basket_metrics` passes `full_holdings` to `build_holding_metrics` (all holdings) but flow_series fetched only for `top5` symbols ✓
    - `_ENGINE_VERSION="3"`: `monitor_cmd.py` line +74 ✓
    - hard-0 clamp (NOT `min(blend,0)`): `_dual_track.py` line `return DualTrack(industry_score, 0.0, True, _REASON_FALSE_CHEAP_CLAMP, r)` ✓
    - NAV-denominator coverage floor 0.40: `holding_metrics._MONITOR_COVERAGE_FLOOR = 0.40`; `aggregate_valuation` uses it ✓
    - board industry columns + value-trap badge + 行业覆盖 rollup: `render_drilldown.py` adds 行业/行业PE/r/行业分 columns + `_trap_badge` + `valuation_rollup_html` ✓
    - reconciliation oracle reads post-clamp val_score: `structural.py:_board_valuation_value` uses `r.get("val_score")` from trace rows (clamped rows have val_score=0.0, contributing 0) ✓
    - trace `_SCHEMA_VERSION="4"`: `eval/trace.py` line `_SCHEMA_VERSION = "4"` ✓
    - ADR `docs/adr/0020-monitor-dual-track-valuation.md` exists: created (54 lines) ✓
    - `valuation_reconciliation` + `valuation_coverage_health` in `eval/structural.py`: both present ✓
    - `build_panel_rows` extended with `valuation_reconciliation_healths` + `valuation_coverage_healths` params: `eval/determinism.py` ✓
