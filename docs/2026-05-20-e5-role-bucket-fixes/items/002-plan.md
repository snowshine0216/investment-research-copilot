# Item 002 — Add US-bond QDII feeders to `qdii_us.yaml`

## Files

- `src/irc/templates/config/universe/qdii_us.yaml` — **canonical template** (committed)
- `config/universe/qdii_us.yaml` — user's local working copy (gitignored; updated separately for immediate effect on the next `irc run`)
- `tests/discovery/test_universe_completeness.py` — TDD: assert bond feeders are in the template

The `config/universe/*.yaml` files are gitignored per `.gitignore` line 23. The
durable, version-controlled fix lives in the template — precedent: `2026-05-18`
universe-completeness fix did the same (see `tests/discovery/test_universe_completeness.py:11-14`).

## Why

`defensive_us_bond` role bucket returns 0 candidates because `qdii_us.yaml` has
**zero** bond instruments (universe gap, per E5 report). Adding three QDII bond
LOFs gives the role something to surface.

## Predicate constraint

`_is_defensive_us_bond` requires:
```python
r.asset_class == "us_etf" and "bond" in (r.tracked_index or "").lower()
```

Bond LOFs aren't strictly ETFs but the closest matching `asset_class` literal is
`us_etf`. The expense-ratio path in `hard_filter._expense_max` already routes
`us_etf + cn_off_exchange → qdii_feeder_expense_ratio_max: 0.012` which is the
right gate for QDII LOFs.

## Instruments to add (per report)

| ID | Name | Mkt | tracked_index | Venue |
|---|---|---|---|---|
| 161716 | 易方达全球美元债 LOF | cn_off_exchange | "Global USD Bond" | cmb_fund |
| 003719 | 鹏华全球高收益债 | cn_off_exchange | "Global High Yield Bond" | cmb_fund |
| 006308 | 华夏海外收益债 | cn_off_exchange | "Overseas Bond Aggregate" | cmb_fund |

Tracked-index strings each contain "bond" (case-insensitive) so the predicate matches.

## Verification

- `pytest tests/discovery/ -q` — schema validation in fixture loading
- `pytest tests/schemas/ -q` — UniverseConfig parse + no-duplicates check

## Commit message

```
feat(universe): add US-bond QDII feeders to qdii_us.yaml (E5 phase 2)

Rescues the defensive_us_bond role bucket (was 0 candidates, universe gap).
Three CN-domestic QDII bond LOFs added: 161716 易方达全球美元债, 003719
鹏华全球高收益债, 006308 华夏海外收益债.

Tagged as us_etf+cn_off_exchange so they route through qdii_feeder_expense_ratio_max
(0.012) rather than the strict us_etf_expense_ratio_max (0.003), and their
tracked_index contains "bond" so _is_defensive_us_bond picks them up.

Per outputs/2026-05-20/E5_role_bucket_report.md § Phase 2.
```
