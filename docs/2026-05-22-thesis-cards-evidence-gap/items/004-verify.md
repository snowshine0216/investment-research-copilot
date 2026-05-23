Verdict: FAIL

Source: live AkShare verification (IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py)
Entry point exercised: ak.fund_announcement_em(symbol=<each of 518880, 000001, 005827>)

## Q4 PREREQUISITE FAILURE

`ak.fund_announcement_em` is missing from the installed AkShare. All 5 live tests on item 004's sub-branch FAIL with `AttributeError: module 'akshare' has no attribute 'fund_announcement_em'`.

Pinned AkShare version: 1.18.63 (confirm with `python -c "import akshare; print(akshare.__version__)"`).

The endpoint named in spec §"In scope" and ADR-implicit assumption for item 005's information leg does not exist in this version. Items 005, 006, 007, 008, 009 — all of which depend on the existence of a fund-level announcement adapter — are blocked until Q4 is re-decided.

## What AkShare 1.18.63 DOES have (alternatives)

Three topic-specific variants, all confirmed present and callable via `hasattr(ak, "...")`:

- `ak.fund_announcement_dividend_em(symbol)` — 分红配送 / dividend & distribution announcements
- `ak.fund_announcement_report_em(symbol)` — 定期报告 / periodic reports (quarterly/semi-annual/annual)
- `ak.fund_announcement_personnel_em(symbol)` — 人员变动 / personnel changes

These can be composed to produce a general fund-announcement stream for the gold/bond/active-fund symbols, but each returns a topic-scoped DataFrame; their column shapes differ slightly and they do not unify on the `{title, type, date, url}` contract item 005 assumed.

## Q4 fallback options (your decision — do NOT auto-select)

Per MASTER-PLAN.md § "Stop conditions (hard)" and MASTER-SPEC.md item 004 description:

**Option (a) — Adapt to the topic-specific endpoints.** Re-spec item 005 (Slice F) to call the 3 topic-specific announcement functions for each fund symbol, union the results, normalize the columns, and treat the unioned stream as the information leg. Costs ~3× the AkShare calls per fund vs. the original plan (well within the 2000 budget per ADR 0002). Preserves the gold + cn_bond_fund + tracked-CN-index information-leg coverage.

**Option (b) — Reuse theme reports with promoted scope.** Drop the fund-level announcement requirement for gold/bond. Use the existing `data/research/` theme reports as the information leg for gold (already produces commentary) + bond (would need a bond-theme report added). Lighter implementation but means information citations are macro-scoped rather than instrument-scoped for these asset classes.

**Option (c) — Exclude gold + cn_bond_fund from V1.** Both asset classes flow only to the discipline failure section; never appear in actionable picks. Cleanest fix, smallest scope. Costs the V1 product surface — gold/bond rows currently in the universe.

## Recommendation

**Option (a)** is the lowest-cost, highest-coverage fallback if the topic-specific endpoints' column shapes are workable. The cost is bounded: the FetchPlan budget gate (ADR 0002 §3) already handles the 3× call multiplier. The downside is that item 005 needs a small re-spec to drive the union/normalize logic. Recommend verifying the column shapes of all 3 endpoints (live call, fixture capture, same approach as this item) before committing.

**Option (c)** is the safest if the user wants to lock the V1 scope quickly without re-spec churn.

**Option (b)** is the riskiest — bond theme report doesn't exist yet, would require new research authoring.

## Test infrastructure landed (item 004 work product)

Even though the live gate FAILED, item 004's test infrastructure is reusable:

- `pyproject.toml` `[tool.pytest.ini_options]` registers `live_akshare` and `integration` markers + `--strict-markers`.
- `tests/fundamentals/test_fund_announcement_em_live.py` — gated by `IRC_RUN_LIVE_AKSHARE=1` env var AND `-m live_akshare` marker. Currently asserts the missing function exists; will need to evolve based on which fallback option is chosen.
- `tests/fundamentals/test_fund_announcement_em_failure_modes.py` — mocked failure-mode tests, 5/5 PASS (runs in default suite).
- `tests/fixtures/akshare/.gitkeep` — fixture directory scaffolded.
- `tests/fundamentals/README-live-tests.md` — run-discipline doc.

## Subagent

sonnet (impl); orchestrator-recorded verdict.

## Run state

- 8 commits on branch `autodev/thesis-evidence-004-live-verify-fund-announcement-em` (committed; pushed for user inspection).
- No PR opened (the 5 currently-failing live tests cannot be merged as-is; the fallback decision dictates how to evolve them).
- Items 005, 006, 007, 008, 009 marked ⚠️ BLOCKED-BY-004 in PROGRESS.md.
- Item 010 (DuckDB ingestor) is INDEPENDENT of the Q4 decision per MASTER-SPEC.md item 010; can land in parallel.

After Q4 is re-decided, this verdict file should be amended with the chosen path and the run can resume from item 005 (per the new spec) with item 004's test infrastructure re-purposed as appropriate.
