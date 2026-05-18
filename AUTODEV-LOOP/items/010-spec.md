# 010 — Architecture runner modernization

## Problem

`evals/architecture/metrics.py:_REQUIRED_OUTPUTS` lists `research_memo.md`; the current producer writes `memo.md`. The architecture runner hardcodes today's date for the output directory and writes the report under today even when it measured yesterday's outputs.

## Required behavior

- `_REQUIRED_OUTPUTS` updated: `research_memo.md` → `memo.md`.
- Runner picks today's `outputs/<date>/` if present, else the latest dated `outputs/<date>/` directory (regardless of file completeness — the completeness IS the metric).
- Report is written under the artifact date of the directory actually evaluated, not today.
- Missing-input FAIL when no dated `outputs/<date>/` directory exists at all.
- `max_file_loc` threshold (`warn_above=400`, `fail_above=600`) stays put — `ingest_cmd.py` at 632 lines is a real Phase 2 product debt and should keep failing.

## Acceptance criteria

- New tests cover: fallback to latest dated dir when today absent; report lands under that date; producer-current `memo.md` counts toward completeness.
- Existing tests updated to the new `memo.md` name.
- All architecture tests pass.

## Non-goals

- Do not touch `max_file_loc` threshold.
- Do not refactor `ingest_cmd.py`.

## Files touched

- `evals/architecture/metrics.py` (rename `research_memo.md` → `memo.md`)
- `evals/architecture/runner.py` (rewrite: latest-dir selection, report under artifact date)
- `tests/evals/test_architecture.py` (rename + 2 new tests)
