# 007 — Plan

## Steps

1. `src/irc/opportunity/types.py`: add to `OpportunityInput`:
   - `earnings_yield: float | None = None`
   - `real_yield_10y: float | None = None`
2. `src/irc/opportunity/states.py`: add a pure helper
   `expected_real_return_positive(inp)` returning Optional[bool] and a
   `_EQUITY_ASSET_CLASSES` set for dispatch. Append a rationale phrase
   to `classify_valuation` output when the equity is at expensive /
   very_expensive AND `expected_real_return_positive` is True.
3. Tests at `tests/opportunity/test_earnings_yield_anchor.py` cover
   positive / negative / missing branches.

Note: the spec mentioned adding an `expected_return_signal` field to
`OpportunityRow`. Implementation deferred — surfacing the signal in the
existing `opportunity_reason` string is enough to satisfy the
review-driven acceptance criterion ("memo synthesizer can surface it")
without expanding the row schema. If memo synthesizer needs a
structured field later, it can be added in a separate refactor.
