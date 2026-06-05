# MASTER-PLAN — Phase B sector expansion (B1)

**Mode:** spec
**Project type:** non-web
**PR shape:** A
**Feature branch:** `claude/relaxed-jemison-629597` (current; non-default, non-protected — sub-branch ships into it)
**Base for final roll-up PR:** `main` (opened, NOT merged — left for user to land)
**Item order:** 001 (only item — N=1)
**Branch prefix:** `claude/phase-b-sector-b1-`

## Per-mode skill skips (spec mode)

| Phase | Skill | This run |
|-------|-------|----------|
| spec (brainstorming) | `superpowers:brainstorming` | **SKIPPED ⏭️** — user authored the spec |
| grill | `grill-with-docs` | **SKIPPED ⏭️** — pre-completed (user-grilled); orchestrator must NOT auto-invoke |
| plan | `superpowers:writing-plans` | **RUNS** (Opus) — ENTRY phase, reads the spec |
| impl | `superpowers:subagent-driven-development` | RUNS (Sonnet) |
| drift | in-prompt diff-vs-plan | RUNS (Sonnet) |
| ship | `/ship` (primary) | RUNS — opens PR, updates docs, captures inline review |
| post-ship verify | `/verify` (non-web XOR — never `/qa`) | RUNS (Sonnet) |
| pr-review | `/code-review` on open PR | RUNS (Sonnet) |
| fix | triage subagent | RUNS if any of 3 post-ship verdicts FAIL |
| merge | `gh pr merge --squash --delete-branch` | pre-merge gate then squash |

## Model contract

- Orchestrator: session default (no override).
- Plan subagent: `model="opus"`.
- impl / drift / verify / pr-review / fix subagents: `model="sonnet"`.

## Loop exit contract (item 001)

Merge only when all three post-ship verdicts are PASS / PASS-WITH-NITS:
1. **verify** (non-web XOR) — `items/001-verify.md` `^Verdict: PASS`.
2. **review** (inline from `/ship` steps 8+9) — `items/001-review.md` `^Verdict: PASS|PASS-WITH-NITS`.
3. **pr-review** (`/code-review`) — `items/001-pr-review.md` `^Verdict: PASS|PASS-WITH-NITS`.

Plus presence: `items/001-spec.md`, `items/001-plan.md`; and `items/001-drift.md` `^Verdict: PASS`. Grill verdict absence-OK in spec mode (PROGRESS ⏭️).

## Plan-phase must-carry constraints (from MASTER-SPEC nuances)

1. Edit the valuation-buckets **template** `src/irc/templates/config/valuation_buckets.yaml` (+ any fixtures), NOT a committed `config/valuation_buckets.yaml` (which `irc init` scaffolds).
2. Non-activated sector slug → full `(None, None, None, None, None)` short-circuit (byte-identity; raw metrics feed `OpportunityInput`).
3. Allowlist threaded keyword-only (`activated_sector_slugs=frozenset()` default) — no module-level/global read (FP rule + focused threading test).
4. The 3 existing metals slugs fold into `SECTOR_INDICES` and are now allowlist-governed (must not auto-activate on maturity).
5. B1 edits NO `config/universe/*.yaml` values — `中证机床ZZ` handled via alias only.
6. TDD throughout (test mirrors source; structural tests no-network; live identity guard double-gated by `IRC_RUN_LIVE_AKSHARE=1` + marker).
7. Every new/edited file < 200 lines, functions < 20 (extract helpers).

## Gate posture for B1

- Gate #3 explicitly **NOT claimed** (grounded = 0 by design) — verify/review must not treat empty grounding as a failure.
- Gate #5 **N/A** — empty before/after diff is *expected* for B1, not a regression.
- Docs (Gate #6): CONTEXT.md "Valuation inputs", CHANGELOG `[Unreleased]`, ROADMAP Phase B → B1 done.
