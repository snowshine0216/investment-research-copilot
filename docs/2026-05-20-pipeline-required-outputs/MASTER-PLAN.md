# Master Plan — Pipeline Required-Outputs + Resume

## Workflow

1. Create feature branch `feat/pipeline-required-outputs-resume` off `main`.
2. Commit per task (8 commits total), each touching only its declared files.
3. Each task: write failing tests → minimal impl → verify pass → ruff → commit (TDD-strict per the source plan).
4. After all 8 tasks land on the branch, run final whole-suite + lint validation.
5. Open ONE PR titled `feat(pipeline): fail-fast on missing required outputs + --resume`.
6. Dispatch QA + review subagents in parallel against the PR.
7. Triage findings; ship fixes; re-verify.
8. Merge once green and update `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` if not already done by Task 8.

## Branch strategy

- Single branch `feat/pipeline-required-outputs-resume` (since slices depend on prior slices on disk).
- No sub-branches per task — the source plan's commit boundaries become git commits, not separate PRs.

## TDD discipline

Each task strictly follows Red-Green-Refactor:
- Red: write failing test, confirm it fails for the *expected* reason (ModuleNotFoundError, AssertionError, TypeError).
- Green: minimal impl per the plan code blocks.
- Refactor: only if needed for ruff cleanliness.

## Stop conditions

- Any task's tests fail after impl matches the plan: STOP and investigate (likely environmental).
- `ruff check` fails: fix inline (it's a style issue, not a design one).
- `.venv/bin/pytest` for the full project regresses (a previously-passing test breaks): STOP.

## Deliverables

- 8 commits on `feat/pipeline-required-outputs-resume`.
- PR opened against `main`.
- Tracker updated.
- PR merged.
