# MASTER-PLAN — Decision Confidence Followup

**Mode:** backlog
**Project type:** non-web
**PR shape:** A
**Base branch:** main (protected — no opt-in; synthetic feature branch is mandatory)
**Feature branch (synthesized):** `autodev/decision-confidence-followup-feature`
**Item order:** TBD (set by dependency-scan)
**Sonnet override:** none (N=3 < 5, no cost warning required)

## Per-item branches

Each IN item lands a PR from its sub-branch into `autodev/decision-confidence-followup-feature`.

- 001 → `claude/decision-confidence-followup-001`
- 002 → `claude/decision-confidence-followup-002`
- 003 → `claude/decision-confidence-followup-003`

## Per-mode skill schedule

Backlog mode runs every authoring phase per item:

| Phase     | Skill / dispatch                              | Model  |
|-----------|-----------------------------------------------|--------|
| spec      | `superpowers:brainstorming` (Opus subagent)   | opus   |
| grill     | `grill-with-docs` auto-accept (Opus subagent) | opus   |
| plan      | `superpowers:writing-plans` (Opus subagent)   | opus   |
| impl      | `superpowers:subagent-driven-development`     | sonnet |
| drift     | in-prompt diff vs plan                        | sonnet |
| ship      | `/ship` (review captured inline)              | sonnet |
| verify    | `/verify` (non-web; not `/qa`)                | sonnet |
| pr-review | `/code-review` against open PR                | sonnet |
| fix       | Sonnet fix subagent per failing verdict       | sonnet |

## Run-level gates (Phase 2 end)

1. `run-doc-sync.md` — verifies CONTEXT.md/ADR/README coverage across all merged items
2. `run-final-verify.md` — `/verify` smoke against integrated feature branch

## Exit contract

- Every IN row has 6 verdict files (grill / drift / ship / verify / review / pr-review) + 2 presence files (spec / plan).
- Both run-level gates PASS.
- Feature branch left open (NOT merged into main) for user to land.
- `.autodev-current` deleted in close-out.

## Live PR / merge gate

- Each per-item PR: protected-base check + drift + ship + grill + verify + review + pr-review + fix all green before `gh pr merge`.
- Feature branch PR opens at end of Phase 3 into `main` for user review — **not auto-merged**.
