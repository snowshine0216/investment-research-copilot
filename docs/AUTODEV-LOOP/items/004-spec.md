# Item 004 — Gate downstream stages on ingest freshness

## Problem

Today (2026-05-17) the ingest stage halted (PIPELINE_HALTED.md), yet `outputs/2026-05-17/` contains:
- `memo.md` with `regime=unknown / zone=unknown / 仓位倾斜=neutral`
- `decision_report.md` with all rows marked `avoid` based on stale fundamentals
- `opportunity_report.json` with hundreds of "missing data" codes

These artifacts look authoritative but are based on stale data from prior ingests (last good ingest visible in `outputs/2026-05-16/`). With the P0 fix already merged, ingest fails loudly — but if a user runs only `irc memo` or `irc allocate` directly (skipping ingest), the same misleading artifacts are produced silently.

## Approach

Add a small `freshness` module that reads the last-update timestamp from DuckDB (e.g. from the `_ingested_at` column on the `prices` or `nav_history` tables, or from the manifest file `data/.../manifest.json`). Each stage entrypoint that depends on fresh prices/NAV calls a `require_fresh_ingest(max_age=timedelta(hours=24))` helper near the top. If ingest is stale:
- Default: write a `STALE_INGEST.md` marker to `outputs/<date>/` and return rc=1.
- Override: a `--allow-stale` flag (or env var `IRC_ALLOW_STALE=1`) lets the stage proceed but tags every produced artifact with a "STALE INGEST" header.

The 24h window is read from `settings.py` so it's configurable.

## Acceptance criteria

- Three stages get the freshness check: `gold`, `opportunity` (currently invoked from `discover`/`score` paths), `memo`. (`allocate`, `plan` depend on the above — they get the check transitively via their upstream's outputs.)
- A unit test for each gated stage verifies: when DuckDB ingest timestamp is >24h old, the stage exits with rc=1 and writes `STALE_INGEST.md`; with `IRC_ALLOW_STALE=1`, it proceeds and tags the output.
- The check has no effect when ingest is fresh — existing tests continue to pass.
- `STALE_INGEST.md` includes: max_age threshold, observed_age, last_ingest_at, and the override hint.

## Files (expected)

- `src/irc/data/freshness.py` (new) — the `require_fresh_ingest` helper.
- `src/irc/commands/gold_cmd.py`, `opportunity_cmd.py`, `memo_cmd.py` — call the helper at the top.
- `src/irc/settings.py` — add the 24h default.
- `tests/data/test_freshness.py` (new) — for the helper itself.
- `tests/commands/test_gold_cmd.py`, `test_opportunity_cmd.py`, `test_memo_cmd.py` — extend with the gated paths.

## Non-goals

- Changing ingest itself.
- Per-table freshness (single timestamp = last successful akshare ingest is enough).
- Forcing the freshness check on stages that don't read prices/NAV (e.g. `research`).
- Implementing a "partial freshness" mode where some asset_classes can be stale and others fresh.
