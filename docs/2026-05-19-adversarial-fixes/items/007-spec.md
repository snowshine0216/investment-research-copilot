# 007 — Equity earnings-yield sanity anchor

## Why

The adversarial review (§B3) flags percentile-only valuation as having
known failure modes: US equity at 95th percentile can stay there for
years (1995–2000 lesson). A long-horizon DCA investor told to
underweight a multi-year bull market on percentile grounds loses real
money.

The fix is a second signal: earnings-yield vs real rate. When
`earnings_yield - real_yield > 0`, the equity is offering a positive
expected real return, even if its price percentile is high.

## What changes

1. In `src/irc/opportunity/types.py`, add optional fields to
   `OpportunityInput`:
   - `earnings_yield: float | None` — trailing or forward E/P
   - `real_yield_10y: float | None` — same input the gold model already
     uses (10Y TIPS for US equity, 10Y CGB - 5y5y inflation for CN)
2. In `src/irc/opportunity/states.py`, add a helper
   `expected_real_return_positive(inp) -> bool | None` that returns:
   - `True` if `earnings_yield - real_yield_10y > 0`
   - `False` if it is ≤ 0
   - `None` if either input is missing
3. In the existing `classify_valuation`, retain the percentile bands
   unchanged BUT in the returned rationale string, append a note when
   the equity is `expensive` / `very_expensive` AND
   `expected_real_return_positive=True`:

       「估值百分位 95% 偏高，但实际收益率(earnings_yield - real_yield)
       为正，长期 DCA 仍可视为正期望」

4. Add an `OpportunityRow.expected_return_signal: Literal["positive",
   "negative", "unknown"]` field (or attach to existing diagnostics) so
   the memo synthesizer can surface it.

## Acceptance criteria

- For an equity row with valuation_percentile_self=0.95,
  earnings_yield=0.045, real_yield_10y=0.020, the rationale string
  contains the positive-real-return phrase AND
  `expected_return_signal == "positive"`.
- For an equity row with the same percentile but earnings_yield=0.025,
  real_yield_10y=0.030, `expected_return_signal == "negative"`.
- Missing inputs → `unknown` and no extra phrase added.
- Bond and gold rows are unaffected (only equity asset classes consume
  this signal).

## Tests to add

- `tests/opportunity/test_earnings_yield_anchor.py` covering positive /
  negative / unknown branches and the rationale string side-effect.
