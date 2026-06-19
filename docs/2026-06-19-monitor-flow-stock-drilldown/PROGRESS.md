# PROGRESS — Monitor flow-stock drill-down

**Mode:** spec · **Project type:** non-web (`/verify`) · **PR shape:** A · **Feature branch:** `monitor-flow-stock-drilldown`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (pre-completed) · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ⏭️ | ⏭️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Evidence cells

- **001 spec** ⏭️ — user-provided, copied verbatim → [items/001-spec.md](items/001-spec.md)
- **001 grill** ⏭️ — user-grilled; ADR 0019 + CONTEXT flow glossary committed on this branch (orchestrator must not auto-invoke)
- **001 plan** ✅ — Opus `superpowers:writing-plans` → [items/001-plan.md](items/001-plan.md) (commit `e6bb084`, 24 tasks / 4 slices, all 6 locked-test flips explicit)
- **001 branch** ✅ `claude/monitor-flow-stock-drilldown-001` (off feature tip `e6bb084`)
- **001 impl** ✅ `ed4883d` (HEAD) — `superpowers:subagent-driven-development`; 5 implementer dispatches (Slice 1a flow_fetch, 1b holding_metrics, 2 report, 3 flow→bias, 4 eval+versioning), each with an independent spec-then-quality review:
  - Slice 1a `flow_fetch` → PASS-WITH-NITS (sleep nit fixed `36b0147`)
  - Slice 1b `holding_metrics` → PASS (imports confirmed real: `opportunity/lookthrough_valuation.py` + `returns.py`)
  - Slice 2 report → PASS (no bias leak, ADR 0015 held, golden regen legit)
  - Slice 3 flow→bias → PASS (4 locked flips correct + 2 consequential test updates legit; `compute_signal` byte-identical)
  - Slice 4 eval+versioning → PASS (2 locked flips; numeric `_target_engine` `["9","10"]→"10"`; reconciliation oracle panel-only; CHANGELOG `[Unreleased]`, VERSION unchanged `0.9.3`)
  - **Post-drift gap closure** `77f3a84` — drift surfaced that spec §5.E's flow-coverage-health tally was absent AND `flow_reconciliation` (defined+tested) was never wired into the eval panel (dead code). Closed both: added `flow_coverage_health` + wired both flow rows into `build_panel_rows` (panel-only, non-gating, back-compat). The oracle now actually runs in `eval monitor_signal`.
  - Integration gate: `651 passed, 12 skipped` (live-gated) across `tests/monitor/ tests/monitor/eval/ tests/commands/test_monitor_cmd*`; ruff clean on feature surface.
- **001 drift** ✅ [items/001-drift.md](items/001-drift.md) `4d19f65` — Verdict PASS, 22/22 plan tasks present, all 6 locked flips correct. One finding (§5.E coverage health) re-classified from "accepted/deferred" to **CLOSED** (`77f3a84`) since the oracle was load-bearing and unwired.
- **001 ship** ✅ [PR #167](https://github.com/snowshine0216/investment-research-copilot/pull/167) (`claude/monitor-flow-stock-drilldown-001` → `monitor-flow-stock-drilldown`) — [items/001-ship.md](items/001-ship.md). VERSION bump skipped (project convention).
- **001 review** ✅ [items/001-review.md](items/001-review.md) — PASS-WITH-NITS. /ship steps 8+9 found **2 P0** (flow dead-wired in the composite; fake-PASS health fallback) + 3 P1 — ALL fixed pre-PR (`f7f63f7`+`6964785`), re-verified closed. The P0 flow-wiring is the headline catch.
- **001 verify** ✅ [items/001-verify.md](items/001-verify.md) `9be402d` — PASS. All 6 acceptance criteria observed via real pure-core smoke: **flow drives the bias** (composite Δ=0.0124 with-vs-without flow, flow FactorScore eligible value=0.75); percent-point bands + ratio canary; board/roll-up render (lean language, no 买入/卖出); reconciliation oracle has teeth (PASS on match, FAIL on mismatch); engine isolation (`engine_mismatch:2`, numeric `["9","10"]→"10"`); schema "3".
- **001 pr-review** ✅ [items/001-pr-review.md](items/001-pr-review.md) `4abeb2d` — PASS-WITH-NITS. [/code-review comment](https://github.com/snowshine0216/investment-research-copilot/pull/167#issuecomment-4748752911): 3 nits, **0 blockers, 0 latent bugs**. Nits = cross-module private imports (`_NA_FLOW_NO_DATA`, `_stock_series_by_code`, `_pe_series_is_mature`); #2/#3 pre-existing codebase convention.
- **001 fix** ✅ 0 rounds — all 3 post-ship verdicts PASS/PASS-WITH-NITS; no blockers/latent bugs to triage. (The 2 P0s were already fixed in the ship phase, pre-PR.) 3 cosmetic nits accepted (consistent with the codebase's established cross-package private-import convention; promoting to public would be out-of-scope churn in the opportunity package).
- **001 merge** ✅ squash `25a082b` — [PR #167](https://github.com/snowshine0216/investment-research-copilot/pull/167) MERGED into `monitor-flow-stock-drilldown` (all 7 pre-merge gates passed: protected-base ✓ feature branch, ship+drift+verify+review+pr-review verdicts, comments resolved). Sub-branch deleted. Item 001 DONE.

## Notes

- Single IN-scope item (N=1). The spec's 4 TDD slices become plan tasks under `items/001-plan.md`.
- QA column omitted — non-web project uses `/verify` (XOR).
- Final landing: Phase 3 opens `monitor-flow-stock-drilldown → main` PR, left OPEN for the user (protected base, no opt-in).

## Final status — RUN COMPLETE (2026-06-19)

- **Items merged:** 1 / 1 (item 001 → [PR #167](https://github.com/snowshine0216/investment-research-copilot/pull/167) squash `25a082b` into the feature branch).
- **Items SKIPPED / BLOCKED:** none.
- **Phase 3:** workflow-completeness audit PASS (all required verdict files present; non-web XOR correct; grill absent-OK in spec mode); merged-branch sanity 664 passed / 12 skipped, ruff clean, `irc monitor --help` wired; doc-sync PASS ([doc-sync.md](doc-sync.md) — README + CLAUDE.md updated to note `drilldown.html` + the flow factor); run-level verify = item verify (N=1, already PASS).
- **Headline:** the /ship pre-landing review caught a P0 — the flow factor was computed but never fed into the composite (`FactorInputs` built without `flow=`), so flow never moved the bias. Fixed pre-PR + a regression test added that drives the real command path. Without that catch the feature would have shipped cosmetically dark.
- **Feature branch:** `monitor-flow-stock-drilldown`
- **Feature-branch PR:** https://github.com/snowshine0216/investment-research-copilot/pull/168
- **Merged into protected branch:** no — PR #168 left OPEN for user review (the protected-base guardrail held; no merge-to-main opt-in was given).
- **Follow-ups:** (1) surface the forward-eval engine-drop count as an explicit eval-report WARN (currently recorded in `details.json.excluded_by_engine`, non-silent); (2) staged veto-class work — dual-track valuation + False-Cheap guard, conflict hard-suppression, flow-reversal guard (spec §9, own future spec).
