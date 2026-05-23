Verdict: PASS

Source: live AkShare verification — pivoted to Q4 option (a) on 2026-05-23
Entry points exercised: ak.fund_announcement_{dividend,report,personnel}_em(symbol=<each of 518880, 000001, 005827>)

## Q4 fallback option (a) — adopted

`fund_announcement_em` was confirmed absent in AkShare 1.18.63. The user chose option (a) on 2026-05-23: adapt to the 3 topic-specific announcement endpoints. The live gate was re-run with 11 pivoted tests and all 11 PASS.

All three endpoints share the same column schema:
`['基金代码', '公告标题', '基金名称', '公告日期', '报告ID']`

Key differences from the original `fund_announcement_em` spec:
- No `公告类型` (type) column
- No `公告链接` (url) column — `报告ID` is the opaque reference identifier
- `公告日期` is a Python `datetime.date` object (not a string)

## Test results

Per-endpoint × per-symbol matrix (11 live tests, AkShare 1.18.63):

| Endpoint | 518880 | 000001 | 005827 |
|---|---|---|---|
| `fund_announcement_dividend_em` | 4 rows ✓ | 15 rows ✓ | 1 row ✓ |
| `fund_announcement_report_em` | 94 rows ✓ | 100 rows ✓ | 50 rows ✓ |
| `fund_announcement_personnel_em` | 2 rows ✓ | 14 rows ✓ | 2 rows ✓ |

All 9 cells: PASS (non-empty, title+date columns resolve, row 0 non-null).

## Aggregate gate

PASS — all 3 symbols have non-empty data from all 3 endpoints (9/9 cells non-empty in this run). Gate condition (at least 1 endpoint per symbol) is easily satisfied.

## Fixtures captured

9 endpoint × symbol fixture files:

- `tests/fixtures/akshare/fund_announcement_dividend_em_518880.json` (1.4 KB, 4 rows)
- `tests/fixtures/akshare/fund_announcement_dividend_em_000001.json` (3.9 KB, 15 rows)
- `tests/fixtures/akshare/fund_announcement_dividend_em_005827.json` (0.5 KB, 1 row)
- `tests/fixtures/akshare/fund_announcement_report_em_518880.json` (25.4 KB, 94 rows)
- `tests/fixtures/akshare/fund_announcement_report_em_000001.json` (24.6 KB, 100 rows)
- `tests/fixtures/akshare/fund_announcement_report_em_005827.json` (13.8 KB, 50 rows)
- `tests/fixtures/akshare/fund_announcement_personnel_em_518880.json` (0.7 KB, 2 rows)
- `tests/fixtures/akshare/fund_announcement_personnel_em_000001.json` (4.2 KB, 14 rows)
- `tests/fixtures/akshare/fund_announcement_personnel_em_005827.json` (0.8 KB, 2 rows)

Plus `tests/fixtures/akshare/q4_aggregate_gate_summary.json` (aggregate gate structured summary).

Total: 10 new fixture files. Total size: ~75 KB.

## Downstream impact for item 005

Item 005 (Slice F) must:

1. Call all 3 topic-specific endpoints per fund symbol (3× AkShare calls per symbol, within ADR 0002 FetchPlan budget).
2. Union the 3 DataFrames per symbol; normalize columns to `{title, date, id}` (no `url` — `报告ID` serves as the opaque reference).
3. Handle `datetime.date` objects in `公告日期` (not strings) — AkShare returns Python date objects.
4. The `citation_kind="information"` leg now emits union rows across 3 announcement topics rather than a single unified stream.
5. The 9 fixture files above are the canonical column-shape reference for item 005's mocked unit tests.

## Failure-mode companion

`tests/fundamentals/test_fund_announcement_em_failure_modes.py` still 5/5 PASS. The legacy helpers `_assert_announcement_df` and `_call_fund_announcement_em` are preserved in the live test file to maintain companion compatibility.

## Subagent

sonnet (impl); orchestrator-recorded verdict.

## Run state

- Pivot commits on branch `autodev/thesis-evidence-004-live-verify-fund-announcement-em`:
  - `20c59f1` docs(autodev/004): explore AkShare 1.18.63 topic-specific endpoint shapes + pivot spec/plan
  - `2c24edd` test(fundamentals): rewrite live tests for the 3 topic-specific announcement endpoints (Q4 pivot)
  - `f2bdf2a` test(fundamentals): capture topic-specific endpoint fixtures (Q4 pivot)
- 11 live tests: 11/11 PASS
- 5 failure-mode tests: 5/5 PASS
- Q4 aggregate gate: PASS
- Ready for PR against `autodev/thesis-cards-evidence-gap`.
- Items 005, 006, 007, 008, 009: UNBLOCKED — proceed with item 005 per updated spec.

---

## Prior Q4 FAIL verdict (resolved by pivot)

Preserved for historical context.

**Original verdict: FAIL**

`ak.fund_announcement_em` raised `AttributeError: module 'akshare' has no attribute 'fund_announcement_em'` in AkShare 1.18.63 for all 3 symbols (518880, 000001, 005827). All 5 original live tests failed.

**Three fallback options presented to user:**

- **(a)** Adapt to the 3 topic-specific endpoints: `fund_announcement_{dividend,report,personnel}_em`. → **User chose this option on 2026-05-23.**
- **(b)** Reuse theme reports with promoted scope (treat asset-class macro citations as information-leg for gold + cn_bond_fund).
- **(c)** Exclude gold + cn_bond_fund from V1.

**Resolution:** Option (a) verified and PASS above.
