# Master Spec — Pipeline Required-Outputs + Resume

**Source:** `docs/superpowers/plans/2026-05-20-pipeline-required-outputs-and-resume.md`
**Date:** 2026-05-20
**Feature branch:** `feat/pipeline-required-outputs-resume`

## Goal

Make the `irc run` pipeline fail-fast when a stage exits `rc=0` without producing its required output artifacts, and add `irc run --resume` to pick up automatically from the last halted stage.

## Decomposition strategy

This is **one tightly-coupled feature** broken into 8 TDD slices. Each slice depends on prior slices' merged code (e.g. Task 4 imports `pipeline_outputs` from Task 1; Task 5 imports `pipeline_state` from Task 2). The plan's final integration test (Task 8) requires all prior tasks.

Decomposition: **ONE feature branch, 8 commits, ONE PR.** Per-task review/QA happens at the PR level once all commits land on the branch. The user's instruction "merge the pr once it's safe to merge" confirms this.

## In-scope items

All 8 tasks IN-scope:

| # | Subject | Files |
|---|---|---|
| 001 | Pure `missing_outputs` check module | `src/irc/pipeline_outputs.py`, `tests/test_pipeline_outputs.py` |
| 002 | Persistent `.pipeline_state.json` module | `src/irc/pipeline_state.py`, `tests/test_pipeline_state.py` |
| 003 | Add remediation entry for `missing_required_outputs` | `src/irc/pipeline_halt.py`, `tests/test_pipeline_halt_remediation.py` |
| 004 | Post-stage output validation in `run_pipeline` | `src/irc/commands/run_cmd.py`, `tests/commands/test_run_cmd.py` |
| 005 | Persist state on halt; clear on success | `src/irc/commands/run_cmd.py`, `tests/commands/test_run_cmd.py` |
| 006 | `resume=True` parameter | `src/irc/commands/run_cmd.py`, `tests/commands/test_run_cmd.py` |
| 007 | `--resume` CLI flag | `src/irc/cli.py`, `tests/commands/test_run_cmd.py` |
| 008 | End-to-end integration test + tracker note | `tests/commands/test_run_cmd.py`, `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` |

## Out-of-scope items

None. The plan is self-contained.

## Acceptance criteria (whole feature)

- `.venv/bin/pytest tests/test_pipeline_outputs.py tests/test_pipeline_state.py tests/test_pipeline_halt_remediation.py tests/commands/test_run_cmd.py -v` passes.
- `.venv/bin/ruff check` on touched modules passes.
- `.venv/bin/irc run --help` shows `--resume`.
- `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` updated with the new safety-net entry.
- PR opened against `main`, CI green, merged.
