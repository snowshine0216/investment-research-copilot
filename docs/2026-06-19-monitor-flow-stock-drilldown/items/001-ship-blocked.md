Verdict: FAIL (pre-PR — /ship steps 8+9 blocked ship; routed to triage-fix)

Source: /ship steps 8 (pr-review-toolkit:code-reviewer + silent-failure-hunter) + 9 (adversarial)
Diff reviewed: monitor-flow-stock-drilldown...HEAD (claude/monitor-flow-stock-drilldown-001)

## P0 — BLOCKERS (must fix before PR)

1. **Flow factor is dead-wired — `FactorInputs.flow` never populated** (silent-failure-hunter).
   `src/irc/commands/monitor_cmd.py:650` builds `FactorInputs(...)` with NO `flow=` arg, even though `holding_metrics` is computed at line 640 and `aggregate_flow` is imported. Result: `inp.flow is None` → `_flow()` returns `flow_no_data` for EVERY fund → flow is renormed out of every composite → the bias NEVER reflects flow. The drill-down board shows per-stock flow scores (cosmetic), giving a false impression flow drives the bias. This defeats the feature's primary deliverable (spec D1/D2: "drive the bias by adding a dedicated flow factor"). Same class of bug as the prior valuation/heat "dark factor" (memory: monitor_cmd hardcoded their inputs to None).
   ROOT CAUSE of the miss: no test exercises monitor_cmd's flow→composite wiring; all factor tests construct `FactorInputs(flow=…)` directly.
   FIX: pass `flow=aggregate_flow(holding_metrics) if holding_metrics else None` into the `FactorInputs(...)` constructor. ADD an integration test that proves a fund with healthy flow data gets a flow `FactorScore` (available=True) in its composite (TDD: must FAIL before the wiring, PASS after).

2. **Panel-only health exception fallback uses status="PASS"** (silent-failure-hunter).
   `src/irc/commands/monitor_cmd.py:449-461` — when `flow_reconciliation`/`flow_coverage_health` throw, the fallback `StageHealth` is hardcoded `status="PASS"` with a `*_error` reason. A crashed health computation shows PASS in the panel — misleading. FIX: use `status="WARN"` (panel-only, cannot affect gating, but honestly signals unknown-due-to-error). (Mirror: `monitor_signal_health`'s fallback is FAIL, which is correct for a GATING stage; these are panel-only so WARN is the honest middle.)

## P1 — should fix (cheap, fixing in this round)

3. **`_target_engine` unguarded `max(versions, key=int)`** (code-reviewer + adversarial) — `evals/monitor_forward/runner.py:56` raises `ValueError` if any ledger row carries a non-numeric engine string (corruption/hand-edit). FIX: guard non-digit engine strings (treat as legacy "0"/skip) so `irc eval monitor_forward` can't crash on a corrupt ledger.

4. **`_NA_FLOW_NO_DATA` duplicated** in `holding_metrics.py:28` and `factors.py:21` (code-reviewer) — two independent `"flow_no_data"` literals; a future edit to one silently breaks `_flow()`'s `inp.flow.reason ==` check. FIX: single source — import the constant.

5. **Mutable default dict B006** in `build_panel_rows` (`eval/determinism.py:162-163`) — `={}` with noqa. FIX: `=None` sentinel + `or {}` in body (legitimately silences the lint; read-only so no current bug).

## P1 — noted, NOT silent (no fix this round)

6. **Forward ledger low-n on engine-"2" day 1** (silent-failure-hunter) — when only a few engine-"2" rows exist, isolation drops the rest; metrics run on a tiny corpus. NOT a silent cap: the excluded count IS written to `details.json.excluded_by_engine` (satisfies spec §5.E "log what was dropped"). The forward scorer already has an `insufficient_data` path for low n. Surfacing the engine drop as an explicit WARN is a future enhancement, not a blocker.

## CLEAN (adversarially probed, confirmed correct)
- No 100× unit inversion: parse does no `/100`; `flow_band(0.01)`/`flow_band(0.03)` → 0.0 (deadband).
- `aggregate_flow` div-by-zero guarded (`total_w>0`, `covered_w<=0`); exactly-0.50 coverage passes (spec "<0.50").
- HTML escaped throughout `render_drilldown.py`; None fields render `—`+reason.
- `flow_fetch` never-raises is genuinely per-symbol; misses recorded → no re-hit.
- `valuation_flow_conflict` fires correctly at the `_DIVERGE`=0.3 boundary.
- All 6 locked flips correct; weights sum to 1.0; `FactorInputs.flow` trailing+defaulted.
