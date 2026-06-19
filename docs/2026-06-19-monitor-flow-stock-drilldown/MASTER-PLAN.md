# MASTER-PLAN — Monitor flow-stock drill-down

**Mode:** spec
**Project type:** non-web (Python CLI; `irc` entrypoint) → post-ship verifier is **`/verify`** (NOT `/qa`)
**PR shape:** A (per-item PRs; default — no `--rollup` in invocation)
**Item count:** 1 (N=1)
**Item order:** 001 (single item)

## Branch strategy

- **Feature branch:** `monitor-flow-stock-drilldown` (current branch; holds the 5 design commits + this run dir). Not yet pushed.
- **Item sub-branch:** `claude/monitor-flow-stock-drilldown-001`, cut from the feature branch.
- **Item ship PR:** `claude/monitor-flow-stock-drilldown-001` → `monitor-flow-stock-drilldown` (the per-item review surface; /ship + /verify + /code-review run here).
- **Merge:** squash-merge the sub-PR into `monitor-flow-stock-drilldown`.
- **Phase 3:** open a roll-up PR `monitor-flow-stock-drilldown` → `main` (the single landing PR, per spec §7 "ship as one feature branch"). **Left OPEN, not merged** — `main` is protected and the invocation contained no merge-to-main opt-in.

## Per-mode skill skips (spec mode)

| Phase | Status |
|-------|--------|
| `superpowers:brainstorming` (spec authoring) | ⏭️ SKIPPED — user authored the spec; copied verbatim to `items/001-spec.md` |
| `grill-with-docs` | ⏭️ PRE-COMPLETED — user-grilled (ADR 0019 + CONTEXT glossary committed). Orchestrator must NOT auto-invoke. |
| `superpowers:writing-plans` (Opus) | ▶ RUNS — entry authoring dispatch; reads the spec → `items/001-plan.md` |
| impl / drift / ship / verify / pr-review / fix / merge | RUN unchanged |

## Post-ship gate (XOR + parallel)

- Exactly ONE of `/qa` (web) XOR `/verify` (non-web) → **`/verify`** here (non-web).
- `/code-review` runs in parallel against the open sub-PR.
- Review verdict captured inline by `/ship` steps 8+9.

## Loop exit contract

Merge only when all of: `001-drift.md` PASS, `001-ship.md` (PR URL), `001-verify.md` PASS, `001-review.md` PASS|PASS-WITH-NITS, `001-pr-review.md` PASS|PASS-WITH-NITS. Grill verdict absence-OK (spec mode ⏭️). No retry budget — environmental stops only.

## Implementation notes carried from the spec

- 4 TDD slices, executed via `superpowers:subagent-driven-development` (one fresh subagent per plan task). Red→green→refactor each.
- Spec §7.1 names the 6 locked tests that MUST flip under TDD — the plan must enumerate them as deliberate red→green updates, not "preserved" assertions.
- Test scope on signature changes (project rule + memory): `FactorInputs.flow` defaulting to None keeps 5 construction sites green — run `tests/monitor/`, `tests/monitor/eval/`, AND `tests/commands/`, not just the mirror dir.
- Flow endpoint is DIRECT (CN domain, no `IRC_HTTPS_PROXY`); free (no spend gate); ~15-25 sequential per-symbol calls/run with light pacing; rate-limited symbol → `flow_no_data`, never a crash.
