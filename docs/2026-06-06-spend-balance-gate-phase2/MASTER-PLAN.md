# MASTER-PLAN — Spend / Balance Gate Phase 2

**Mode:** plan
**Project type:** non-web  (Python `irc` CLI — post-ship verifier is `/verify`, never `/qa`)
**PR shape:** A  (per-item PR; no `--rollup` opt-in this turn)

## Branch strategy

- **Default/protected base:** `main` (no opt-in to merge here this turn).
- **Feature branch (synthesized):** `autodev/spend-balance-gate-phase2-feature` — cut off `main`. All sub-PRs land here. Phase 3 opens a feature→main roll-up PR and leaves it OPEN for the user.
- **Item sub-branch:** `claude/spend-balance-gate-phase2-001` — cut off the feature branch; PRs into the feature branch.

## Per-mode skill skips (plan mode)

| Phase | Status | Reason |
|-------|--------|--------|
| `superpowers:brainstorming` (spec) | ⏭️ skipped | user-provided plan |
| `grill-with-docs` (grill) | ⏭️ skipped | user-authored input; plan-mode never grills |
| `superpowers:writing-plans` (plan) | ⏭️ skipped | user-provided plan |

Every downstream gate runs unchanged: branch → impl (`superpowers:subagent-driven-development`) → drift → ship (`/ship`, review captured inline) → (`/verify` ‖ `/code-review`) → triage-fix → merge.

## Loop exit contract (item 001)

Three post-ship verdicts must each be `PASS` / `PASS-WITH-NITS`:
1. `items/001-verify.md` (non-web → `/verify`)
2. `items/001-review.md` (captured inline by `/ship` steps 8+9)
3. `items/001-pr-review.md` (`/code-review` on the open PR)

Plus `items/001-drift.md` (PASS) and `items/001-ship.md`. `items/001-grill.md` does NOT exist (pre-skipped — PROGRESS shows ⏭️ note).

## Test-suite baseline caveat

Full `uv run pytest` is ~18 min and NOT green on `main` (≈8 known pre-existing failures + a flaky/hang-prone e2e research gate — see `project_test_suite_baseline` memory). The DoD requires "no NEW failures vs baseline", so I capture the baseline failure set before impl and diff against it, rather than requiring a fully-green suite.
