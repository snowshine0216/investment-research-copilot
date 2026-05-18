# Item 002 — Drop `manager_tenure_years` from cn_bond_fund required metrics

## What

`src/irc/decision/completeness.py:46-49` requires `manager_tenure_years` for `cn_bond_fund`. Passive bond ETFs (511010 国债ETF国泰, 511260 十年国债ETF国泰, 511020, 511520, 511220, 511180, 511380, 159650) don't have a meaningful manager and the metric is never ingested. They land at `data_completeness=0.75` (3/4 required fields), one fraction below the 0.80 gate, and end up `blocked: low conviction` in `decision_report.md`.

The same rationale was already applied for gold in `completeness.py:50-61` ("Gold ETFs are physically/passively backed — manager tenure is not a meaningful concept"). Bond ETFs are in the same boat.

Evidence in today's output: `outputs/2026-05-18/decision_report.md:84-91` — 8 bond-ETF instruments blocked with `low / 0.75 / Repair required financial metrics`.

## Files to touch

- `src/irc/decision/completeness.py`
- `tests/decision/test_completeness.py` (add the regression test)

## Acceptance criteria

- Distinguish passive bond ETFs from active bond funds. The clean way: introduce a helper `_is_passive_bond(row)` parallel to the existing `_is_active_fund` (`src/irc/opportunity/states.py:154`). Use `market == "cn_on_exchange"` as the discriminator — that's how the universe encodes ETF vs OTC fund.
- For passive bond ETFs (`asset_class == "cn_bond_fund"` AND `market == "cn_on_exchange"`), the required set drops `manager_tenure_years` in addition to the existing drops (`holdings_concentration_top10`, `downside_capture`).
- For active bond funds (no `market` flag, or `market == "cn_off_exchange"`), keep `manager_tenure_years` required.
- A new test asserts the 8 known passive bond ETFs each reach `data_completeness=1.0` given today's fixtures (no `manager_tenure_years` data).
- An adjacency test asserts an active bond fund WITH a manager_tenure_years value at 0.0 stays at < 1.0.
- The full suite is green.

## Implementation hint

The current `REQUIRED_METRICS_BY_ASSET_CLASS` is a flat dict. Easiest path: keep the dict but add a `required_for_row(row)` function alongside `required_for_asset_class`. The row-aware function lets us branch on `market`. Update `missing_required_fields` and `completeness_ratio` to prefer the row-aware path when `row` is available.

## Out of scope

- Re-classifying any other asset class.
- Backfilling actual manager-tenure data for funds where it exists.
