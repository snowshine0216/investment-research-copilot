# 005 — Plan

## Steps

1. `src/irc/opportunity/types.py`: add `cn_bond_yield_percentile:
   float | None = None` to `OpportunityInput`.
2. `src/irc/opportunity/states.py`:
   - Add `_BOND_ASSET_CLASSES: frozenset[str] = frozenset({"cn_bond_fund"})`.
   - Add `classify_bond_valuation(inp: OpportunityInput) -> tuple[ValuationState, str]`:
     - If `cn_bond_yield_percentile` is None AND nothing else available
       → return `evidence_insufficient`.
     - Otherwise compute on yield-percentile with **inverted bands**:
       low yield-percentile ⇔ yields low ⇔ bonds expensive.
     - Bands (yield_pct):
       - `pct >= 0.80` → cheap
       - `0.60 ≤ pct < 0.80` → reasonable_low
       - `0.30 ≤ pct < 0.60` → fair
       - `0.10 ≤ pct < 0.30` → expensive
       - `pct < 0.10` → very_expensive
   - Modify `classify_valuation` to dispatch: if `inp.asset_class ∈
     _BOND_ASSET_CLASSES`, delegate to `classify_bond_valuation`.
3. `tests/opportunity/test_bond_valuation.py` covers cheap / fair /
   very_expensive / evidence_insufficient paths.
4. Run focused tests.
