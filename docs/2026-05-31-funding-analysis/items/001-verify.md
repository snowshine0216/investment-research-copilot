Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct uv run python -c / uv run pytest / uv run ruff check / uv run irc --help

Entry point exercised:
  - `uv run python -c "from irc.fundamentals.consensus import consensus_upside_pct; ..."`
  - `uv run python -c "from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation, _extract_latest_value; ..."`
  - `uv run python -c "from irc.opportunity.types import OpportunityInput; ..."`
  - `uv run irc --help` / `uv run irc opportunity --help`
  - `uv run pytest tests/fundamentals/test_consensus.py tests/fundamentals/test_akshare_index_valuation.py tests/opportunity/test_inputs_loader.py tests/opportunity/test_opportunity_input_fields.py -q`
  - `uv run pytest tests/fundamentals/ tests/opportunity/ -q`
  - `uv run ruff check <new/modified files>`

Observed behavior:
  - AC1 pure helper — `consensus_upside_pct((), 100.0)` → `None`; `median([120])/100−1` → `0.19999999999999996` (≈0.20); `latest_close=None` → `None`; `latest_close=float('nan')` → `None` (A1 NaN guard active); `latest_close=0.0` → `None`; even count `median([120,140])/100−1` → `0.30000000000000004` (≈0.30); NaN-only target → `None`
  - AC2 field wiring — `OpportunityInput(instrument_id='x', asset_class='cn_equity', market='cn').consensus_upside_pct` is `None`; `pe_ttm`, `pb`, `dividend_yield` also default `None`; all 4 fields confirmed via `dataclasses.fields`
  - AC3 fetcher — `fetch_cn_index_valuation` callable; `_extract_latest_value(fixture_pe, ...)` picks latest-date row correctly (12.8 from 2024-12-01 row); `_extract_latest_value(pd.DataFrame(), ...)` → `None`; unknown key `'not_a_real_key'` → `None` without network call
  - AC4 inertness lock — `test_population_is_inert_classify_valuation_byte_identical` present and green (confirmed in 33-test run); `classify_valuation` output byte-identical for bare vs. populated `OpportunityInput`
  - AC5 target_price — `akshare_filing.py:88` retains `target_price=None` with comment citing ADR 0009; `tests/fundamentals/test_akshare_fundamentals.py:372` asserts `target_price is None` — green in full suite run
  - AC6 no regression — 33 tests across the 4 spec-named files: 33 passed; full `tests/fundamentals/ tests/opportunity/` suite: 657 passed, 13 skipped; `uv run irc --help` and `uv run irc opportunity --help` boot cleanly; ruff on new/modified files: `All checks passed!`; new file line counts: `consensus.py` 37, `akshare_index_valuation.py` 102, `index_valuation_types.py` 17 — all under 200-line budget
  - AC7 live-test gating — `tests/fundamentals/test_index_valuation_live.py` carries both `pytest.mark.live_akshare` marker and `IRC_RUN_LIVE_AKSHARE=1` env guard; skipped in normal pytest run

Failures: none
