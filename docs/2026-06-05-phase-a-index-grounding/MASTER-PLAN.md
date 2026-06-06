# MASTER-PLAN — Phase A: Broad-index valuation grounding

**Mode:** spec
**Project type:** non-web
**PR shape:** A
**Feature branch:** `claude/stupefied-banach-f1f037` (pre-existing worktree branch; non-protected)
**Default/protected base:** `main` (Phase 3 opens a roll-up PR into it — NOT merged; no opt-in given)
**Item order:** 001 (N=1)
**Branch prefix:** `claude/phase-a-index-grounding-`

## Per-mode skill skips (spec mode)

| Phase | Skill | Status this run |
|-------|-------|-----------------|
| spec (brainstorming) | `superpowers:brainstorming` | ⏭️ SKIPPED — user authored the spec; copied verbatim to `items/001-spec.md`. |
| grill | `grill-with-docs` | ⏭️ PRE-COMPLETED — user-grilled. Orchestrator MUST NOT auto-invoke. Phase-3 run-level doc-sync catches any CONTEXT/ADR gaps. |
| plan | `superpowers:writing-plans` (Opus) | RUNS — ENTRY point. Reads `items/001-spec.md`. |
| implement | `superpowers:subagent-driven-development` (Sonnet) | RUNS |
| drift | in-prompt (Sonnet) | RUNS |
| ship | `/ship` (Sonnet) | RUNS — opens PR + docs + inline review. **NO VERSION bump** (project convention + spec gate #6). |
| verify | `/verify` (Sonnet) | RUNS — non-web XOR branch (NOT `/qa`). |
| pr-review | `/code-review` (Sonnet) | RUNS on open PR. |
| fix | triage + Sonnet fix subagent | conditional |
| merge | `gh pr merge --squash --delete-branch` | RUNS (base = feature branch, non-protected) |

## Constraints carried into every downstream phase

- **TDD mandatory** (global CLAUDE.md + project CLAUDE.md + spec §4 "TDD — gate #1"). Red→green→refactor; test file mirrors source.
- **Functional/immutable** — pure stage cores, effects at edges; no arg mutation.
- **No VERSION bump** (memory: accumulate under CHANGELOG `[Unreleased]`; spec gate #6 confirms).
- **No ADR 0012 addendum** (spec D4 + gate #6 — static→TTM is a bugfix toward the existing PE-TTM requirement; no proxy enters the slot).
- **`基金概况` indicator forbidden** in production fetch code (acceptance test greps the literal).
- **Live tests double-gated**: `pytest.mark.<name>` + `IRC_*=1` env var.
- **Test-suite baseline NOT green on main** (~8 known pre-existing failures + flaky e2e research gate, ~18min full run). Diff-check scope before treating a failure as a regression.

## Deliverable (spec §6)

`docs/2026-06-05-phase-a-broad-grounding/` — before/after table of `valuation_state` + `valuation_percentile_fundamental` (+ NAV percentile + divergence flag) for the ~9 grounded broad funds. This is gate-#5 sign-off evidence. **Distinct dir** from this run dir.
