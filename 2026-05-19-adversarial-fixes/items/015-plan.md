# 015 — Plan

## Steps

1. Add `cap_satellite_qdii` pure function in `target_weights.py`:
   - Takes (selected rows, cap) and returns (capped rows, shaved_total).
   - For each row where `role` starts with `satellite_` AND `asset_class
     in {us_etf, hk_etf}`, shave `target_weight` down to cap, accumulate
     the excess.
2. Wire into `run_allocation` after the softmax-distribute step:
   - Apply cap.
   - Re-distribute shaved weight to the highest-scored same-class row
     that has remaining headroom. If no headroom, drop to cash_residual.
3. Make cap configurable via the existing class-targets dict as a top-
   level optional key `satellite_qdii_max_weight` (default 0.05). Falls
   back to the constant if not provided.
4. Add `tests/allocation/test_satellite_qdii_cap.py` with three cases:
   - one satellite QDII over cap → capped, remainder to cash
   - two QDIIs both over cap → both capped, remainder to cash
   - non-satellite QDII over 5% → not capped
5. Verify full allocation suite still green.
