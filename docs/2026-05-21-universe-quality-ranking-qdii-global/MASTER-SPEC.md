# Master spec — Universe quality-weighted ranking + qdii_global asset class

**Source plan:** `docs/superpowers/plans/2026-05-21-universe-quality-ranking-and-qdii-global.md`
**Mode:** plan (single feature, ready-to-execute, 11 numbered tasks with exact file paths and commands)
**N items:** 1 (single feature spanning 11 tasks)
**PR shape:** A (single PR for the feature)
**Merge target:** main (user opted in this turn)

## In scope

| id  | title | summary |
|-----|-------|---------|
| 001 | universe-quality-ranking-qdii-global | Replace fund_code-ascending tiebreaker in `_candidate_rank` with 1Y-return quality signal (Path A) AND add `qdii_global` asset_class so global-mandate QDII active funds bucket separately (Path C). Two surgical, backward-compatible changes across `cn_fund_universe.py`, `akshare_client.py`, `_types.py`, `universe_cmd.py`, and the regenerated `cn_funds.generated.yaml`. |

## Out of scope

(none — single-feature plan with no skipped items)

## Acceptance (from the plan)

1. `config/universe/cn_funds.generated.yaml` contains an instrument with `instrument_id: '270023'` and `asset_class: qdii_global`.
2. `irc universe build-cn-funds` counts block includes a `qdii_global/NONE: N` line.
3. `tests/integration/test_generated_cn_fund_discovery.py::test_generated_universe_contains_270023_in_qdii_global_bucket` passes.
4. `_apply_caps` with `returns={}` yields the same selection as today (backward-compatible).
5. `fetch_open_fund_ranks()` is lru-cached; failures in `universe_cmd.run_build_cn_funds` degrade gracefully to `returns={}` with stderr warning.
6. No downstream test regression; Task 11 handles any `asset_class` consumers that need explicit `qdii_global` handling.
