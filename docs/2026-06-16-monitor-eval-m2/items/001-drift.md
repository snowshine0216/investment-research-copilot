Verdict: PASS

Subagent: sonnet
Plan checklist items: 15 tasks (M0–M5, Tasks 0–14 + M5 verification)
Verified present in diff: 15 / 15

Drift findings:
  - Task 6 / test_flat_series_is_near_zero_momentum — divergent (known deviation a)
    Evidence: tests/monitor/test_trend_property.py:55 — impl uses `st.integers(1, 100).map(float)` instead of plan's `st.floats(1.0, 3.0)`
    Assessment: mathematical intent (flat NAV series ⟹ near-zero trend score) is fully preserved. Arbitrary floats cause FP drift in `_ma_struct`'s MA windows because non-representable constants make the MA differ from the level, spuriously breaking the invariant. Integer-floats are exactly representable, so every MA == base and the invariant holds deterministically. The strategy change is strictly a correctness improvement, not a weakening.
    Action: plan amended inline with one-line rationale (commit follows)

  - Task 10 / ValidationPanelRow in eval/types.py — commit-grouping only (known deviation b)
    Evidence: src/irc/monitor/eval/types.py diff shows ValidationPanelRow added in the same D2/M3 commit (cffe77a) rather than a separate M4 commit. The dataclass shape matches the spec exactly: frozen=True, fields stage:str, status:str, ran_at:str, reasons:tuple[str,...].
    Action: accepted — pure commit-ordering artifact; no spec violation

Spec-critical invariants confirmed (all lines read from actual diff):

  1. recompute_signal_from_trace / deterministic_health take fund_id EXPLICITLY — LANDED
     determinism.py:42 `def recompute_signal_from_trace(fund_id: str, trace_fund: dict)`
     determinism.py:105 `def deterministic_health(fund_id: str, trace_fund: dict)`
     aggregate_deterministic_health passes fund_id from dict key: determinism.py:121 `for fid, f in funds.items()` → `deterministic_health(fid, f)`

  2. aggregate_news_factor property asserts clamped weighted SUM — LANDED
     test_news_factor_property.py:41 `expected = _clamp(sum(r.weight * r.impact * r.confidence for r in rows))`
     Impact-monotonicity also present: test_value_nondecreasing_in_a_rows_impact at line 64.
     NOT a weighted mean for value — confirmed by test name `test_value_is_clamped_weighted_sum_not_mean`.

  3. KNOWN_NA_REASONS + named constants live in factors.py (NOT determinism.py) — LANDED
     factors.py lines 12–29 (diff confirmed). _na() call sites all refactored to named constants.
     determinism.py:12 imports `from irc.monitor.factors import KNOWN_NA_REASONS`.

  4. deterministic_scoring NOT in GATING_STAGES_* and guard test present — LANDED
     gate.py: GATING_STAGES_M0 = {"monitor_signal"}; GATING_STAGES_M1 adds only {"monitor_impact", "monitor_narrative"} — deterministic_scoring absent.
     Guard test: test_panel_rows.py `test_failing_deterministic_health_never_gates_a_bias` asserts `"deterministic_scoring" not in GATING_STAGES_M1` and `gate.suppressed is False` with det_fail in healths tuple.

  5. _compute_gates returns (gates, signal_healths, deterministic_healths) 3-tuple from ONE per-fund projection — LANDED
     monitor_cmd.py:379 `return tuple(gates), signal_healths, deterministic_healths`
     One projection per fund (single `build_eval_trace` call per fund in the loop); M1 gate test call sites all unpacked to 3-tuple (test_gate_flip_m1.py lines 91, 103, 116).

  6. Divergence-1 re-expression landed — LANDED
     test_render_html_eval.py: renamed to `test_validation_panel_gate_outcome_visible_via_badge_when_fund_gated`; asserts `"EVAL-GATED" in html`, `"gated: 1" in html`, `"Validation" in html` — gate-outcome visibility moved to badge_counts/EVAL-GATED.
     test_acceptance_eval.py: appended `assert "gated: 1" in html` and `assert "deterministic_scoring" in html`.
     test_panel.py: extended for multi-row; new `test_panel_renders_per_row_reasons` added.

No scope creep found. PROGRESS.md update is incidental (tracking only).
