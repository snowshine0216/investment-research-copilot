# 005 — Discovery runner modernization

## Problem

`evals/discovery/runner.py` reads `outputs/discovery/watchlist.json`, a retired path. The current producer (`src/irc/commands/discover_cmd.py`) writes `outputs/<date>/discovered_watchlist.csv`. The runner therefore always FAILs with "missing input" no matter how recent the discovery run was.

## Current producer contract

`discover_cmd` calls `result.watchlist.to_csv(index=False)` where `result.watchlist` is a DataFrame with columns (from `src/irc/discovery/pipeline.py:_WATCHLIST_COLUMNS`):

- `instrument_id`, `ticker`, `market`, `name_cn`, `asset_class`, `currency`
- `tracked_index`, `venue_required`, `role`, `reason_text`, `cited_refs`, `relaxed`

There is no `score` column — score is produced by the downstream `scoring` stage. The existing `filter_integrity` metric defaults to `("ticker", "role", "score")` which silently degrades to `("ticker", "role")` because `score` is filtered out by the existing "skip columns not present" guard. That guard mimics "graceful degradation" but masks the schema mismatch.

## Required behavior

- Locate via `evals._shared.locator.locate(repo_root, ("discovered_watchlist.csv",))`.
- On miss: existing `write_missing_input_report` flow, FAIL.
- On hit: parse CSV with pandas; compute existing metrics; write report via `evals._shared.report_paths.write_report` under the locator-supplied artifact date.
- `filter_integrity` defaults updated to `("instrument_id", "ticker", "role")` to match the producer's actual contract (those three are downstream-required identifiers, none nullable in a healthy run).
- The runner explicitly errors when the CSV is missing one of those three columns (schema-mismatch FAIL), so a future producer refactor that drops a required column produces a loud failure, not a silent 1.0.

## Acceptance criteria

- `evals/discovery/runner.py` reads dated `discovered_watchlist.csv` via the locator and writes the report via `write_report`.
- The `outputs/discovery/watchlist.json` path is removed from the code.
- `filter_integrity`'s default `required_cols` is `("instrument_id", "ticker", "role")`.
- When `discovered_watchlist.csv` is missing required columns, the runner returns FAIL with a `notes` string naming the missing columns — not a 1.0 metric value.
- Existing `tests/evals/test_discovery_runner.py` tests pass after being updated to use the new CSV contract (the old `watchlist.json` fixture is replaced).
- Existing `tests/evals/test_discovery_metrics.py` tests pass (metric functions unchanged in behavior; defaults updated).
- A new test verifies that a CSV missing `instrument_id` produces a FAIL with `notes` naming the missing column.
- A new test verifies that today's CSV is preferred over yesterday's via the shared locator.

## Non-goals

- Do not change the `discovery_diagnostics.csv` / `discovery_rejections.csv` contract.
- Do not change `candidates_per_role`, `dedup`, or `llm_reason_grounding` metric semantics.
- Do not change discovery thresholds.

## Files touched

- `evals/discovery/runner.py` (rewrite)
- `evals/discovery/metrics.py` (update `filter_integrity` default)
- `tests/evals/test_discovery_runner.py` (replace JSON fixture with CSV)
- `tests/evals/test_discovery_metrics.py` (update if default changes affect any test)
