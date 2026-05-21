# Master plan — Universe quality-weighted ranking + qdii_global asset class

## Mode
- **Detected mode:** plan (user supplied a complete ready-to-execute plan with numbered tasks, exact file paths, commands, and test code)
- Brainstorming: skipped (spec inferred from plan)
- writing-plans: skipped (user-authored plan used verbatim)

## PR shape
- **Mode A** (single PR for the single feature) — N=1 so per-item PRs collapses to one PR
- Sub-branch: `autodev/universe-quality-ranking-qdii-global`
- Base: `main` (user opted in this turn to merge to main)

## Workflow per item

Single item (`001`) walks through the canonical autodev phases:

1. **spec** — skipped task (plan mode); 5-line stub captured in `items/001-spec.md`
2. **plan** — skipped task (plan mode); plan copied verbatim to `items/001-plan.md`
3. **branch** — create `autodev/universe-quality-ranking-qdii-global` off main
4. **impl** — dispatch Sonnet subagent invoking `superpowers:subagent-driven-development` over the 11 plan tasks (TDD per task, frequent commits)
5. **ship** — `gstack-ship` opens PR into `main`
6. **qa + review** — parallel Sonnet subagents (`gstack-qa` + `superpowers:requesting-code-review`) produce verdict files
7. **fix** — triage findings, push fixes to the same branch until QA=PASS AND review zero-blockers/zero-latent-bugs
8. **merge** — pre-merge gate (protected-base + ship + qa + review verdicts present) then `gh pr merge --squash --delete-branch`

## Cross-cutting validation (final phase)

- `pytest -x` runs green
- `git diff main` review against MASTER-SPEC acceptance criteria
- Close-out commit on main updating PROGRESS.md

## Model selection (subagent contract)
- Orchestrator: session default (no override)
- Spec/plan subagents: SKIPPED in plan mode
- Impl, QA, ship, review, fix subagents: `model="sonnet"`
