# Live AkShare tests — run discipline

The tests in `test_fund_announcement_em_live.py` hit the real AkShare network
to verify that the three topic-specific fund-announcement endpoints exist and
return usable data for the three Q4-prerequisite symbols (gold `518880`, bond
`000001`, active fund `005827`):

- `ak.fund_announcement_dividend_em` — 分红配送 / dividend & distribution
- `ak.fund_announcement_report_em` — 定期报告 / periodic reports
- `ak.fund_announcement_personnel_em` — 人员变动 / personnel changes

The original spec targeted a single `ak.fund_announcement_em` adapter, but
AkShare 1.18.63 only exposes the topic-specific variants. The user-authorized
Q4 fallback option (a) on 2026-05-23 substituted the 3 endpoints; item 005
(Slice F) is expected to compose them for its information leg. See
`docs/2026-05-22-thesis-cards-evidence-gap/items/004-verify.md` for the full
pivot rationale.

## How to run

Both the marker AND the env var are required (dual gate):

```bash
IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare \
    tests/fundamentals/test_fund_announcement_em_live.py -v -s
```

Expected: 11 tests pass (1 preflight + 9 per-endpoint × per-symbol + 1
aggregate Q4 gate). Each per-symbol test prints a one-line shape summary;
the aggregate gate prints the AkShare version and the per-symbol coverage
matrix on success.

## Fixture refresh behaviour

Successful per-symbol runs write/overwrite (10 files total — 9
per-endpoint-per-symbol + 1 aggregate summary):

- `tests/fixtures/akshare/fund_announcement_dividend_em_{symbol}.json`
- `tests/fixtures/akshare/fund_announcement_report_em_{symbol}.json`
- `tests/fixtures/akshare/fund_announcement_personnel_em_{symbol}.json`
- `tests/fixtures/akshare/q4_aggregate_gate_summary.json`

Each file carries `columns`, `rows`, `captured_at` (ISO-8601 UTC),
`akshare_version`. Chinese column names are preserved verbatim
(`ensure_ascii=False`). Note that the actual column set across all three
endpoints is `[基金代码, 公告标题, 基金名称, 公告日期, 报告ID]` — there is no
URL column; item 005 will use the opaque `报告ID` reference for the
information-leg citation.

The fixture is **always overwritten** — it is a captured shadow of the
latest live response, not a frozen snapshot. Tests never assert content
equality against the fixture (only column shape + non-empty for the
aggregate gate), so daily content drift is benign.

## What FAILURE means

Any failing test raises with a structured message prefixed
`Q4 PREREQUISITE FAILURE: …`. The aggregate gate FAILs if any symbol has
ZERO non-empty results across all 3 endpoints. Per-endpoint × per-symbol
tests may legitimately report empty (and pass with a documented skip-style
message) for combinations where the symbol genuinely has no events of that
type (e.g. no personnel changes for a passive ETF).

Fall-back options if a future AkShare release breaks the 3 endpoints
(verbatim from `docs/diagnosis-thesis-cards-evidence-gap.md` §5):

- **(a) Pin AkShare** to a version that exposes the 3 topic-specific
  endpoints (currently in effect — 1.18.63 confirmed working).
- **(b) Reuse theme reports with promoted scope** — treat asset-class macro
  citations as information-leg for gold + cn_bond_fund.
- **(c) Exclude gold + cn_bond_fund from V1** — drop those asset classes
  from the actionable opportunity surface.

The autodev orchestrator does NOT auto-select a fall-back; it escalates to
the user with the structured failure message. See
`docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md` §"Stop /
proceed contract" for the operational steps the orchestrator follows on
FAIL.

## Default `pytest` behaviour

Running `pytest` (or `pytest -x`) without the marker AND env var skips
every live test in this file. Zero AkShare calls occur in default suite
runs.

The companion file `test_fund_announcement_em_failure_modes.py` runs in
every default suite invocation — it patches `_ak_call` to lock the
failure-trace tone and does NOT hit the network.
