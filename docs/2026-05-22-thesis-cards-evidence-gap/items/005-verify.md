Verdict: PASS-WITH-NOTES

Subagent: sonnet (via /verify)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/59
Project type: non-web Python CLI

## Entry-point smoke

Live `irc opportunity` smoke was not run against live AkShare endpoints — the CLI requires network-reachable AkShare and is correctly blocked by missing external state (DuckDB schema, scoring outputs, configured model provider). Instead the fund-level dispatch was driven through the two purpose-built integration tests that exercise `_build_rows` with `_ak_call` fixture-mocked at the seam:

Command: `python -m pytest tests/commands/test_opportunity_cmd_fund_level.py tests/commands/test_opportunity_cmd_fund_level_integration.py -v`
Exit code: 0
Output dir contents: N/A (tmp_path fixtures used)

Spot-check evidence:

- **gold (518880):** `test_build_snapshot_gold_row_emits_fund_level_evidence` + `test_build_rows_routes_fund_level_evidence_into_opportunity_row` confirm `FundLevelSnapshot` with one `citation_kind="data"` record (`NAV=4.5678 @ 2026-03-15`) and ≥1 `citation_kind="information"` record (`summary="[ANREP] title-ANREP"`), all `scope="instrument"`, `owner_instrument_id="518880"`, `url=""`.
- **bond (000001) + cn_etf (510300):** `test_three_row_integration_gold_bond_cn_etf_dual_coverage` confirms both carry `"data"` + `"information"` kinds with `scope="instrument"` and `owner_instrument_id` matching their instrument IDs.
- **QDII (qdii_global):** `test_build_snapshot_qdii_row_emits_sentinel_zero_calls` asserts `evidence_gaps==("qdii_information_unavailable",)` and `_ak_call.call_count==0`.
- **active-fund path (item 003):** `test_build_snapshot_active_fund_path_unchanged` and all 80 regression tests PASS; `_build_active_fund_snapshot` is unmodified.
- **Cache write:** `test_three_row_integration_writes_cache` confirms `data/fundamentals/2026Q1/nav/fund_518880.json` is written with `/nav/` in path.

Note: live AkShare substituted with fixture-mocked integration tests as described. The tests were written as part of this item explicitly for this purpose. The substitute is comprehensive — it drives the full `_build_rows` code path, not just isolated units.

## Acceptance-criteria walkthrough

| # | AC (paraphrased) | Approach | Evidence | Result |
|---|------------------|----------|----------|--------|
| 1 | F1: `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot` frozen dataclasses in `types.py` with `__post_init__` validation; in `__all__` | code inspection + test_types.py (26 tests, all PASS) | `types.py:205-294`; all three classes frozen, validations present; all in `__all__` | PASS |
| 2 | F1: `FundNavReport.__post_init__` — non-empty fund_id, latest_nav>0, ISO date, non-empty history, history[-1] matches latest, quarter YYYYQ[1-4] | test_types.py 7 FundNavReport tests | `test_types.py` all 7 tests PASS | PASS |
| 3 | F1: Quarter derivation uses calendar logic (`_infer_quarter_from_date` in `akshare_fundamentals.py`), NOT earnings quarter | code inspection | `akshare_fundamentals.py:467-479` uses `(month-1)//3+1` calendar formula; separate from `_parse_quarter_column` earnings logic | PASS |
| 4 | F2: `fetch_fund_announcements` calls 3 endpoints in `dividend→report→personnel` order | code + test | `akshare_fundamentals.py:535-538` `_FUND_ANN_TOPIC_FNS` tuple; `test_fetch_fund_announcements.py::test_calls_3_endpoints_in_order` PASS | PASS |
| 5 | F2: Dedup key `(fund_id, report_id)`, first-observed topic wins; sort `date desc, report_id asc` | code + test | `akshare_fundamentals.py:597-609`; `test_dedup_by_report_id` + `test_sorted_by_date_desc_report_id_asc` PASS | PASS |
| 6 | F2: Never raises; per-endpoint exception degrades to empty | code + test | `akshare_fundamentals.py:598-602` try/except/continue; `test_endpoint_exception_degrades_to_empty` + `test_all_endpoints_fail` PASS | PASS |
| 7 | F3: `build_snapshot` dispatch order: active_fund → QDII sentinel → fund-level (kind in `_FUND_LEVEL_KINDS` + non-empty provider_symbol) → legacy | code + test | `snapshot.py:263-269`; tests for each branch PASS (60 tests in `test_fund_level_snapshot.py`) | PASS |
| 8 | F3: `map_lookthrough` populates `provider_symbol` for gold/cn_bond_fund/cn_etf | code + test | `lookthrough.py:96-147`; `test_map_lookthrough_gold_populates_provider_symbol` + `test_cn_bond_fund_populates_provider_symbol` + `test_cn_etf_tracked_index_populates_provider_symbol` PASS | PASS |
| 9 | F4: QDII sentinel unconditional (no provider_symbol gate); zero AkShare calls | code + test | `snapshot.py:265-266` checks kind in `("qdii_us","qdii_hk","qdii_global")` BEFORE fund-level check; `test_qdii_sentinel_zero_fetch` for all 3 kinds PASS; `test_build_snapshot_qdii_row_emits_sentinel_zero_calls` mock call_count==0 PASS | PASS |
| 10 | F5: `"基金概况"` not in `akshare_fundamentals.py` or `snapshot.py` production code | grep | `grep -rn "基金概况" src/` → exit 1 (zero matches); `test_static_profile_invariant.py` 2 tests PASS | PASS |
| 11 | ADR 0001 §2: announcement evidence has `url=""`, `summary=f"[{report_id}] {title}"` | runtime exercise | live construction produces `url=''`, `summary='[AN202407240003689710] 年度报告'` (verified via direct invocation with mock) | PASS |
| 12 | ADR 0001 §2: citation_ids deterministic; different `report_id` → different `citation_id` | test | `test_fund_level_snapshot_citation_ids.py` all 3 tests PASS | PASS |
| 13 | Cache layout: `data/fundamentals/{quarter}/nav/fund_{fund_id}.json`; atomic write; reader returns None on missing/malformed | code + test | `snapshot_cache.py:247-248`; 6 nav-cache tests PASS including atomic-write and skip-QDII-sentinel | PASS |
| 14 | QDII sentinel NOT written to disk | code + test | `snapshot_cache.py:347` skips when `"qdii_information_unavailable" in snap.evidence_gaps`; `test_write_nav_cache_skips_qdii_sentinel` PASS | PASS |
| 15 | Integration: gold/bond/cn_etf produce `thesis_evidence` with `data`+`information` legs, `scope="instrument"` | integration test | `test_three_row_integration_gold_bond_cn_etf_dual_coverage` PASS | PASS |
| 16 | Regression: `_build_active_fund_snapshot` untouched; cn_equity_fund routes to active_fund | code + test | `snapshot.py:437-485` unmodified; `test_build_snapshot_active_fund_path_unchanged` PASS; all 80 regression tests PASS | PASS |
| 17 | Existing passive/display-only tests pass (`test_snapshot.py`) | test | 80 tests PASS including legacy snapshot path | PASS |
| 18 | Preflight budget: fund-level calls included (4 per fund); `FetchPlan` extended | code + test | `opportunity_cmd.py:69-90` `fund_level_misses/stale` fields; `test_fetch_plan_includes_fund_level_costs` + `test_preflight_does_not_exceed_budget_for_v1_universe` PASS | PASS |
| 19 | No new ADR; ADR 0002 §5 extended | docs | `docs/adr/0002-active-fund-fetch-engine.md` contains §5 | PASS |

Total ACs verified: 19/19

## Regression checks

- Active-fund path (item 003) untouched: **PASS** — `_build_active_fund_snapshot` not in diff for snapshot.py; all 80 tests (snapshot + lookthrough + opportunity_cmd) PASS without modification.
- Pre-existing test failures: 0 — full suite clean on this branch.

## Probes

- `build_snapshot(LookthroughTarget(kind="broad_index", provider_symbol=""))` → falls through to legacy (dispatch condition `target.kind in _FUND_LEVEL_KINDS and target.provider_symbol` evaluates False when provider_symbol empty) — correct.
- `build_snapshot(LookthroughTarget(kind="qdii_us", provider_symbol="159612"))` → QDII sentinel (not fund-level), because QDII check precedes fund-level check — correct per spec F4 "unconditional".
- `grep -rn "基金概况" src/` → exit 1 (zero matches in production code).
