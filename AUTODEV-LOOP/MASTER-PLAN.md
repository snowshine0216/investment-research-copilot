# MASTER-PLAN — execution rules

## Phase ordering

```
001 (packaging) ──┐
                  ├──→ 005..010 (runner modernizations, parallel-eligible after foundations land)
002 (registry) ───┤
003 (locator) ────┤
004 (report-date)─┘
```

Items 002/003/004 must land in order (002 before 003/004 not strictly required, but is cleaner since 002 changes the CLI dispatch entry point). Items 005–010 each depend only on the foundation set; they will be implemented serially in this run to keep tracker integrity simple.

## Branching strategy (worktree mode)

We are operating in a Claude Code worktree (`claude/intelligent-shtern-d84f4d`). The standard autodev-loop pattern of sub-branch-per-item + PR-per-item into a remote feature branch does not match the worktree flow.

**Adapted strategy:**
- Each item lands as **a single squashed commit on the worktree branch**.
- Per-item discipline (spec → plan → impl → QA → review → fix → ship) is preserved; only the branching layer is collapsed.
- The QA + review subagents inspect the staged diff before the commit lands.
- At the end of all items + cross-cutting validation, push the worktree branch and open one PR worktree → main.

This trades per-item PR review for a clean per-item commit history that the final reviewer can step through with `git log --oneline` + `git show`.

## Subagent dispatch policy

- All subagents run on Sonnet (per skill).
- Implementation subagent reads `items/<id>-spec.md` and `items/<id>-plan.md` directly — do NOT paste their content into prompts.
- QA + review subagents are dispatched in **parallel** (one message, two tool calls).
- QA subagent: runs tests, runs build, performs adversarial check, verifies acceptance criteria.
- Review subagent: reads staged diff via `git diff --staged` (or `git diff HEAD~1` post-commit), distinguishes blockers / latent bugs / nits.
- Fixes that touch ≤1 file already written: orchestrator inline.
- Fixes that touch multiple files or require new tests: fresh subagent.

## TDD discipline

Per `~/.claude/CLAUDE.md`:
1. Write failing test first.
2. Implement minimum code to make it pass.
3. Refactor with tests green.

The implementation subagent must execute Red-Green-Refactor and report test counts before/after.

## Workflow rules (project-specific)

- Test command: `uv run pytest tests/evals -x` for fast feedback; `uv run pytest -x` for full suite at cross-cutting validation.
- Lint: `uv run ruff check evals src tests`.
- CLI smoke: `uv run irc --help` (already exercised by `tests/test_cli_smoke.py`).
- Pure functions: no module-level mutable state, no `let`-style reassignment in Python, no mutation of dict/list arguments.

## Final validation (Phase 3)

After all 10 items merge:
- Run `uv run pytest -x` — must exit 0.
- Run `uv run ruff check evals src tests` — must exit 0.
- Run `uv run irc --help` — must not raise `ModuleNotFoundError`.
- Verify `irc eval --all` resolves the active suite only (news, queries excluded).
- Write `AUTODEV-LOOP/cross-branch-diff.md` summarizing Phase 1 deltas vs. main.
- Push worktree branch and open PR with link to MASTER-SPEC.md and SKIPPED.md.

## Token budget

Estimate: 10 items × (spec + plan + impl + QA + review + ~0.5 fix) ≈ 45 subagent dispatches + ~200K orchestrator tokens. Pause and report if approaching 600K total before item 010 lands.
