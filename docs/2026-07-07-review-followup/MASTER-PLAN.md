# MASTER-PLAN — review-followup run (2026-07-07)

Mode: backlog
Project type: non-web        # Python CLI (`irc`) — post-ship verifier is /verify, never /qa
PR shape: A                  # per-item PRs; no --rollup in the user's invocation
Item order: 004, 005, 001, 002, 003   # user-locked in BACKLOG.md with rationale — dependency-scan dispatch skipped (the backlog IS the dependency scan; 002 runs after code items so docs record fixed state; 003 depends on 002)
Sonnet override: none        # authoring stays on Opus (autonomous run; no user opt-in possible; authoring quality prioritized per operating contract)

## Branching

- Feature branch: `autodev/review-followup-feature` (synthesized off `main` — protected-branch rule; user gave no merge-to-main opt-in). Sub-PRs land here; the feature branch is left open at close-out for the user.
- Branch prefix: `claude/review-followup-<id>`.

## Per-item phase adjustments (user-instruction overrides, documented)

| id | spec | grill | plan | rationale |
|----|------|-------|------|-----------|
| 004 | Opus brainstorm (constrained: approach LOCKED — translate at rotation join, NOT store; no radar_version bump) | Opus grill-with-docs auto-accept (must not overturn locked decisions) | Opus writing-plans | full backlog pipeline |
| 005 | Opus brainstorm (constrained: fix = `fresh_slice` skip-set, one line + tests) | Opus grill-with-docs auto-accept | Opus writing-plans | full backlog pipeline |
| 001 | ⏭️ pre-completed — locked spec at `docs/superpowers/specs/2026-07-07-data-health-notify-design.md`; copied/linked as `items/001-spec.md` | ⏭️ pre-completed — GRILLED + LOCKED 2026-07-07 by the user (spec §9/§10); re-grilling would rewrite user-locked intent | Opus writing-plans against the locked spec | user pre-completed authoring |
| 002 | ⏭️ user override — backlog: "No design needed"; work order (D1–D15 + 002-a/b/c/d) copied verbatim as `items/002-spec.md` | ⏭️ same user override; Q-B resolved; the item itself IS the doc-sync | Opus writing-plans (sequence ~15 edits + TDD 002-d) | explicit user instruction |
| 003 | verbatim copy from backlog → `items/003-spec.md` (content fully enumerated by user) | ⏭️ docs-only, content user-locked; grilling CLAUDE.md-convention prose against CLAUDE.md is circular | Opus writing-plans | content pre-authored; sequencing still benefits from a plan |

Pre-completed ⏭️ phases get their PROGRESS cells marked ⏭️ with the reason; the merge gate accepts ⏭️ **only** for these documented user-override rows (001 grill/spec, 002 spec/grill, 003 grill).

## Post-ship gate (identical every item)

drift → /ship (PR + inline review captured to `items/<id>-review.md`) → [/verify ‖ /code-review] → triage-fix loop (exit only when verify + review + pr-review all PASS / PASS-WITH-NITS) → pre-merge gate → `gh pr merge --squash --delete-branch` into the feature branch.

## Worker-dispatch constants (every Agent call)

- Impl/drift/verify/pr-review/fix: `model="sonnet"`. Spec/grill/plan: `model="opus"`.
- Literal line in every worker prompt: **"Calling the Agent tool is FORBIDDEN"**.
- pytest per-file only; never bare `tests/commands/`.
- No VERSION bump; CHANGELOG `[Unreleased]`.

## Cost estimate (N=5 — surfaced per cost-budget.md)

~9 Opus dispatches (004/005 spec+grill+plan = 6; 001/002/003 plan = 3) + ~20–25 Sonnet dispatches (impl/drift/verify/pr-review/fix × 5 + run-level gates) + /ship + /code-review internal fan-out. No Sonnet override taken — the session is autonomous (non-interactive); the user can interrupt and set `Sonnet override: spec, plan` if cost matters more than authoring quality.

## Carried-in working-tree state (committed with design artifacts)

The review session left uncommitted edits that are item-002 INPUT: CLAUDE.md (FACTS pointer), CONTEXT.md (flow-freshness + data-health-digest glossary), README.md (CN-proxy section), untracked FACTS.md + review doc + notify spec. Committed on the feature branch at run start to protect them from sub-branch churn (the documented race recovery is reset-to-reviewed-base — uncommitted state would be lost). Item 002 amends wording on top ("~200 boards" → pagination-cap phrasing, flow-leg proxy wording, FACTS.md F8 section).
