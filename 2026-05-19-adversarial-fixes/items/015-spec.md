# 015 — Sector QDII sizing constraint

## Why

`000369 广发全球医疗保健` was sized at 8.8% target weight as
`satellite_cn_healthcare`. The adversarial review (§C2) flags this as a
sector bet sized like a core holding: `quality=weak`,
`valuation=very_expensive`, but the largest active-equity weight.

Single-sector QDIIs should be sized in the "satellite" band — not be the
biggest active-equity line in the book.

## What changes

In `src/irc/allocation/target_weights.py` (or its caller), apply a per-row
cap: any selected instrument whose `role` starts with `satellite_` AND
whose `asset_class` is `us_etf` or `hk_etf` (QDII proxies) is capped at
`satellite_qdii_max_weight` (default 0.05). The unfilled remainder is
redistributed to the next-highest scorer in the same role bucket (or
falls into the cash residual if none remains).

Add the constant to `config/discovery.yaml` (or wherever role-level caps
live):

```yaml
weight_caps:
  satellite_qdii_max_weight: 0.05
```

## Acceptance criteria

- After re-allocation, no row with role prefix `satellite_` and
  asset_class in `{us_etf, hk_etf}` carries `target_weight > 0.05`.
- Total weight sum + cash_residual still ≈ 1.0.
- Existing tests for target_weights remain green.

## Tests to add

- `tests/allocation/test_satellite_qdii_cap.py`: synthesize an allocation
  where a satellite QDII scores 100 and would naively take 12%; confirm
  cap holds at 0.05 and remainder redistributes.
