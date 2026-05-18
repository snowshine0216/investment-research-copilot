# Item 003 — Backfill `name_cn` for 5 instruments

## What

These rows in `outputs/2026-05-18/discipline_report.md` render the instrument ID twice — once as the code, once as the "name" — because `name_cn` is empty in the universe:

- `110022 110022`
- `512960 512960`
- `005827 005827`
- `163417 163417`
- `161005 161005`

That's user-facing and harms credibility.

## Files to touch

- `config/universe/cn_funds.generated.yaml` (or `config/universe/cn_funds.yaml` if the codes live there)
- `tests/discovery/test_universe.py` if needed (add an assertion that name_cn is non-empty for these IDs)

## Acceptance criteria

- Each of the 5 IDs has a non-empty `name_cn` in the universe yaml.
- Names match the akshare `fund_name_em` mapping. Subagent should attempt an akshare lookup via the project's existing `irc.data.akshare` shim. If that's unreachable in the QA environment, fall back to looking up the name in `outputs/2026-05-18/discovered_watchlist.csv` (the `name_cn` column there contains akshare-sourced names). If both routes fail, use the explicit placeholder string `未公开命名` rather than the raw ID.
- A new test (or the discovery test) asserts all 5 IDs are present in the universe AND have non-empty, non-ID `name_cn`.
- The full suite is green.

## Reference: today's known names

Subagent should verify, but as of 2026-05-18 these are widely-known fund names:

- 110022 = 易方达消费行业股票
- 512960 = 央企创新ETF博时 (already appears as the name in `outputs/2026-05-18/memo.md` Section 5)
- 005827 = 易方达蓝筹精选混合
- 163417 = 兴全合润分级混合 (兴全合润灵活配置混合)
- 161005 = 富国天惠成长混合A

Confirm via akshare or the watchlist CSV before writing — don't ship un-validated names.

## Out of scope

- Backfilling names for every fund in the universe. Scope strictly to the 5 IDs that render badly today.
- Restructuring the universe yaml format.
