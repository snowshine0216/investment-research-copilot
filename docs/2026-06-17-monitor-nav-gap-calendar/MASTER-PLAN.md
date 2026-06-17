# MASTER-PLAN — monitor nav-gap trading-calendar

**Mode:** spec
**Project type:** non-web (Python CLI — `irc`) → post-ship verifier is `/verify` (not `/qa`)
**PR shape:** A (per-item PR; no `--rollup`)
**Base branch:** `main` (protected — no merge-to-main opt-in this turn)
**Feature branch:** `autodev/monitor-nav-gap-calendar-feature` (synthesized off `main`)
**Item branch prefix:** `claude/monitor-nav-gap-calendar-`

## Per-mode skill skips (spec mode)

- `superpowers:brainstorming` — **skipped** (user authored the spec).
- `grill-with-docs` — **pre-completed ⏭️** (user-grilled; orchestrator must not auto-invoke).
- `superpowers:writing-plans` — **runs** (Opus subagent) — ENTRY phase.

## Phase sequence (N=1)

plan (Opus writing-plans) → branch → impl (Sonnet) → drift (Sonnet) → ship (`/ship`)
→ [ verify (`/verify`) ‖ pr-review (`/code-review`) ] + inline review from `/ship`
→ fix loop → merge (squash sub-branch → feature branch).

## Landing

Mode A: item sub-branch PR → feature branch (non-protected, auto-mergeable on green gates).
Phase 3 opens the feature-branch PR → `main` and **leaves it open** for the user
(main is protected; no merge-to-main opt-in this turn).

## Loop exit contract (all three post-ship verdicts)

- `items/001-verify.md` — `Verdict: PASS`
- `items/001-review.md` — `Verdict: PASS|PASS-WITH-NITS` (captured inline by `/ship`)
- `items/001-pr-review.md` — `Verdict: PASS|PASS-WITH-NITS` (`/code-review` on the PR)
