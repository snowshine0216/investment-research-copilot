Verdict: PASS-WITH-NITS

Source: /code-review skill — independent second-pass, high effort (3 correctness angles + cleanup/efficiency/altitude)
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/96#issuecomment-4601702712

## Findings (1 total)

| # | File:line | Classification | Description |
|---|-----------|----------------|-------------|
| N1 | `src/irc/commands/narrative_cmd.py:168` | nit / stale user message | Error message says "active-fund autobuild" and "Active-fund snapshots are auto-built" (lines 168–169, 176) — now a misnomer since `autobuild_narrative` also builds passive-ETF nav snapshots. A user with an all-passive shortlist who hits `FetchBudgetExceeded` reads guidance that doesn't match their situation. |

## No correctness bugs found

- active/passive eligibility sets are provably disjoint: `cn_equity_fund` routes to `active_fund` kind only; `cn_etf`/`us_etf`/`hk_etf` never reach `_is_eligible`.
- Terminal-default `provider_symbol=""` (falsy) correctly excludes bare `cn_etf` rows (no `tracked_index`/`theme`) from fund-level building in both autobuild and analyze paths.
- Budget math correct: `fund_level_misses * 4` calls, combined with `active_fund_misses * (1 + top_n*3 + 4)` in the shared preflight.
- Cache scan path `*/nav/fund_{fund_id}.json` with `path.parent.parent.name` resolves correctly, consistent with `nav_cache_path` writing to `fundamentals/{quarter}/nav/fund_{fund_id}.json`.
- `QDII_KINDS` and `_FUND_LEVEL_KINDS` are disjoint and together cover the same universe as `build_snapshot`'s dispatch branches.
- Test monkeypatching correctly targets module-level bindings throughout; `_build_input` stub update from `object()` to real `OpportunityInput` is required and correct.
- Removed `_load_latest_nav_cached` from `opportunity_cmd.py` is fully replaced by `snapshot_cache.load_latest_nav_cached`; all importers updated with no dangling references.
