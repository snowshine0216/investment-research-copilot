# MASTER-PLAN — Execution

## Branching

- Parent feature branch: `claude/trust-check-fixes-2026-05-19` from `main`
- Per-item sub-branches: `claude/trust-check-fixes-2026-05-19-NNN`
- Each sub-branch lands as its own PR into the feature branch (squash merge)
- Final PR: feature → `main`, single integrated commit when ready

## Per-item workflow (per Phase 2 of the autodev-loop skill)

1. Write `items/NNN-spec.md` (already partially captured in MASTER-SPEC)
2. Write `items/NNN-plan.md` (just-in-time, before impl)
3. `git switch -c claude/trust-check-fixes-2026-05-19-NNN feature-branch`
4. Implement (TDD: failing test → minimal code → green → refactor)
5. Push, open PR via `gh pr create`
6. Run focused tests + targeted QA check (orchestrator-side; per-item
   subagents reserved for larger items)
7. Squash-merge PR, delete branch, update PROGRESS.md
8. Loop

For items 001–003 (rendering-only) the orchestrator implements inline
(< 50 LoC each, mostly Python f-strings + tests). For items 004–007
(diagnostic logic touching multiple files), dispatch a Sonnet subagent.

## Acceptance gates for the whole run

- All focused decision/memo unit tests pass (`uv run pytest
  tests/decision/ tests/memo/ tests/commands/`)
- A re-run on 2026-05-19 inputs produces a `decision_report.md` that:
  - Has a "Today's only action" headline (or honestly states none)
  - Surfaces audit P1 in Verdict if present
  - Surfaces drift > 5pp in Verdict if present
  - Has no QDII row marked `buy_candidate` while premium is uncollected
  - Has a Chinese name column for every row
  - Collapses gold-blocked rows when proxy covers them
  - Has a glossary section at the bottom

## Phase 3: cross-cutting validation

After all 7 items merge into the feature branch:

- Run full unit suite, confirm baseline pass count
- Regenerate `outputs/2026-05-19/decision_report.md` via `irc decision`
- Visually inspect against the original trust-check critique; write
  diff in `cross-branch-diff.md`
- Update `CHANGELOG.md` and `VERSION` (bump to v0.8.6)
