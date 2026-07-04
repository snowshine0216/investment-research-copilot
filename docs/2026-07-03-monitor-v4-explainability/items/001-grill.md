Verdict: PASS

Subagent: grill-with-docs (autonomous — no user in loop; recommended answers auto-accepted per dispatch override). Upstream locks from the 2026-07-03 source-spec grill (P1 reason format, P2 chip/tooltip/anchor + dedupe surfaces, OD-3 weekly best-effort refresh, schema 6→7 in this item, no `_ENGINE_VERSION` change) were NOT reopened; the grill hardened the item spec's own mechanisms against CONTEXT.md, the ADRs, and actual code.

Questions resolved: 9 (RD-1 … RD-9 in the spec's `## Resolved decisions`). 2 corrections (strike-through), 4 additions, 3 verifications-with-evidence. Zero unresolved.

Docs touched:
- `CONTEXT.md` — 今日速览 entry gains the fourth/first-position run-global caveat line; Validation badge/chip entry gains the anchor+tooltip clause; new term **Caveat reason (run-global vs fund-specific)** added to the Monitor eval spine section. No other entries touched (no bloat).
- `docs/adr/` — **no new ADR** (RD-9: three-of-three fails for every candidate decision).
- `docs/2026-07-03-monitor-v4-explainability/items/001-spec.md` — refined in place (criteria 3, 4, 6, 12, 14; open-question 3; appended `## Resolved decisions`). Strike-throughs preserved, nothing deleted.

Spec refined: yes — summary of the Q/A per item below (full rationale + code citations live in the spec's `## Resolved decisions`).

## Resolved decisions

**RD-1 — Is the monitor_cmd.py:485 schema-literal-drift claim true, and is the unification plan sound?**
Q: Does `monitor_cmd.py:485` really hardcode `"6"` in the schema slot separately from `trace._SCHEMA_VERSION`?
A: Yes — verified `Provenance(_ENGINE_VERSION, "2", "6", "")` with field order `(engine_version, prompt_version, schema_version, spend_summary)`. Unify by renaming to public `SCHEMA_VERSION` in `trace.py` and importing at the construction site. All three named test files exist with `"6"` pins; the `"5"` back-compat fixture is untouched.
Rationale: report header and trace moved together at the 5→6 bump — they are the same version, so one constant.
Doc impact: none (spec-level pin only).

**RD-2 — Is `RUN_GLOBAL_STAGES = M1 − M0` the right classification mechanism?**
Q: The set arithmetic yields the right two stages today, but is derivation the right definition?
A: No — corrected to an explicit literal frozenset + an equality guard test against `M1 − M0`. Run-global-ness is a resolution-locality property (`_suite_eval` resolves once per run; `monitor_signal` is per-fund in `_compute_gates`), not a gating-set property. A future per-fund gating stage added to M1 would be silently misclassified by the derived form (renderer would collapse a fund-specific cause to one line); the literal + pin makes that a loud test failure. The pin is tautological against a derived definition — teeth require the literal.
Rationale: fail loud over fail silent on a semantic coincidence.
Doc impact: CONTEXT.md *Caveat reason* entry carries the classification semantics.

**RD-3 — Does the weekly-wrapper slice conflict with ops/launchd/lib-run.sh conventions?**
Q: Lock, watchdog, notify paging, early-exit paths — any conflicts? And does the spec's command line actually run?
A: One real defect: `run_with_watchdog` executes `"$@" &`, and a `VAR=1` word expanded from `"$@"` is execed as a command name (bash assignment parsing precedes expansion) → rc 127, masked by the best-effort guard — the evals would never fire. Fixed with an `env IRC_RUN_LIVE_LLM_EVAL=1` prefix + a text-pin test on that exact form. Everything else verified compatible: sentinel/lock early-exits precede the append point (criterion 13 holds structurally); the EXIT-trap lock is correctly held through the evals; notify pages before the evals; rc 124/5/1/2 all flow into the breadcrumb without touching the wrapper rc.
Rationale: a silent rc-127 is precisely the failure class (green wrapper, permanently stale suites) this item exists to eliminate.
Doc impact: `ops/launchd/README.md` env-var table gains the `IRC_WEEKLY_EVAL_TIMEOUT` row (criterion 14).

**RD-4 — What does the overview line say for suite-state combinations the locked wording doesn't cover?**
Q: Exactly-one-suite-unhealthy, mixed stale+absent, fresh-WARN — tests must pin exact strings.
A: Deterministic fallback grammar: per-suite `{中文label}：{fragment}` segments reusing the criterion-4 label map (`过期 {N}天` / `缺失` / raw status), ` · ` joined; suffix always appended; both-stale and all-absent keep the locked wordings verbatim.
Rationale: reuses locked vocabulary, invents nothing, fully testable.
Doc impact: none beyond criterion 6.

**RD-5 — Where does the caveat line sit in the strip, and what about the 今日无变化 quiet line?**
A: First row (entry-point rationale from P2); counts as a row for the all-empty check so an all-caveated quiet day can never render 今日无变化.
Doc impact: CONTEXT.md 今日速览 entry updated.

**RD-6 — Does turning the chip into an `<a>` break rendering?**
A: One `_CSS` rule needed (no `text-decoration`/color reset on `.val-chip`; default link underline would show). Tests pin element/href/title only.
Doc impact: none.

**RD-7 — Does the `("stale",)` → `("stale, 15d",)` change break any consumer, and is the segment grammar unambiguous?**
A: Blast radius verified empty by grep (only display joins + substring-check tests; the sole production reason-parser targets `flow_cover` rows). Boundary semantics match as-built code: stale iff `.days > 14`, so `15d` is the minimum stamp and criterion 1's exactly-14d test pins existing behavior. No `monitor_signal` reason producer emits `"; "`, so segment splitting is unambiguous; a `", "`/`": "`-bearing fixture is added to the gate-format test shape.
Doc impact: CONTEXT.md *Caveat reason* entry records the age-stamped-at-source / parse-never-reclock rule.

**RD-8 — Is forward-ledger comparability really preserved under schema 6→7 and the reason population?**
A: Yes — ledger rows carry no `schema_version` (only `manifest_versions.engine`); the scorer filters on engine only; `gate_reason` is written but read by nothing (verified), so its "" → populated change is additive observability, not a break.
Doc impact: noted in the spec so a reviewer doesn't flag the ledger content change as drift.

**RD-9 — Any ADR?**
A: No. Reason grammar follows the existing FAIL-branch precedent (not surprising, reversible via a future bump); wrapper change is trivially reversible; constant unification is trivial. CONTEXT.md is the right register for the classification term.
Doc impact: none (deliberately).
