# 004 — Report-date policy follows source

## Problem

Every runner re-implements its own `_write(repo_root, report, [date])` function with the same shape but subtly different defaults. The `architecture` runner hardcodes today; `discovery`, `memo`, and `news` runners hardcode today; `scoring` and `opportunity` already pass an explicit source date but duplicate the path-building boilerplate. Without a shared helper, items 005–010 would each re-invent this pattern.

Per spec §Make-report-placement-follow-the-source:
- For dated stages, the report belongs under the **artifact** date (so a 2026-05-18 rerun against 2026-05-17 artifacts writes to `outputs/2026-05-17/evals/<stage>/report.json`).
- For mutable non-dated sources (`data/local.duckdb`, `data/research/research_status.json`), reports continue under the run date.

## Required behavior

- A shared `write_report(repo_root, report, *, artifact_date)` helper:
  - Writes `outputs/<artifact_date>/evals/<stage>/report.json`.
  - Uses `atomic_write_text` (existing project convention).
  - Creates parent dirs.
  - Returns the written path.
- A shared `report_dir(repo_root, stage, artifact_date) -> Path` helper for callers that need the path without writing.
- The existing `write_missing_input_report` keeps its public signature (callers pass run-date implicitly) but is rewired to delegate to `write_report` so we have one path-building site, not two.
- The `scoring` runner switches to `locate(...)` + `write_report(..., artifact_date=<locator-date>)`. No metric changes.
- The `opportunity` runner switches to `locate(...)` + `write_report(..., artifact_date=<locator-date>)`. No metric changes.

## Acceptance criteria

- `evals/_shared/report_paths.py` exists with `report_dir` and `write_report`.
- `evals/_shared/missing_input.py` still exposes `write_missing_input_report` with the same signature; internally uses `write_report`.
- `evals/scoring/runner.py` uses `locate` + `write_report`; the bespoke `_load_scores` and `_write` helpers are removed (or replaced by simple parsing).
- `evals/opportunity/runner.py` uses `locate` + `write_report`; the bespoke `_locate_inputs` and `_write` helpers are removed (locator usage requires the report file; cards + md remain optional).
- All existing scoring and opportunity runner tests pass unchanged (they already use dated paths).
- A new `tests/evals/test_report_paths.py` covers `report_dir`, `write_report`, atomic write semantics, and the run-date default behavior via `write_missing_input_report`.
- Full suite passes; ruff is clean on the new module.

## Non-goals

- Do not migrate `data` or `research` runners in this item — their `_write` helpers are correct-by-default (run-date) and changing them is scope creep. Items 005–010 will not touch them either.
- Do not migrate `architecture`, `discovery`, `memo`, `gold_score`, `allocation`, or `trade_plan` here — those are items 005–010.
- Do not change `StageReport` schema or `report_to_dict`.
- Do not change any threshold, metric, or `rc` semantic.

## Edge case — opportunity locator contract

The opportunity runner currently treats `thesis_cards.yaml` and `discipline_report.md` as optional sidecars. The locator should require `opportunity_report.json` only; the runner checks for the optional sidecars on the same dated directory afterward. That preserves today's "fall back if a sidecar is missing" tolerance.

## Files touched

- `evals/_shared/report_paths.py` (new)
- `evals/_shared/missing_input.py` (delegate)
- `evals/scoring/runner.py` (migrate)
- `evals/opportunity/runner.py` (migrate)
- `tests/evals/test_report_paths.py` (new)
