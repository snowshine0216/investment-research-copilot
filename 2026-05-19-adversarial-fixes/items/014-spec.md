# 014 — FX / QDII premium diagnostics

## Why

The adversarial review (§C4, §C5) notes ~25% USD exposure unhedged for a
CNY-based investor, with no diagnostic on USD/CNY trend, QDII NAV+premium
spread risk, or hedge cost. QDII feeders trade at premium/discount to
underlying NAV and can suspend large subscriptions.

## What changes

1. In `src/irc/memo/synthesizer.py`, compute:

```python
qdii_classes = {"us_etf", "hk_etf"}
qdii_weight = sum(
    row.target_weight for row in selected_instruments
    if row.asset_class in qdii_classes
)
```

   If `qdii_weight >= 0.20` (configurable threshold), emit a new
   Section: **"6.x 外汇与QDII敞口"** (FX & QDII exposure) containing:
   - total QDII weight pct and USD-equivalent
   - currency_tolerance from `preferences.yaml`; flag if exceeded
   - per-row, if a `qdii_premium_pct` field is available from the
     fundamentals snapshot, list it; otherwise mark "溢价数据未采集"
   - a one-line cost-of-hedge note when an FX hedge cost field is
     available, otherwise "未对冲" (unhedged)

2. The premium and hedge-cost fields are best-effort: when absent, the
   memo prints the diagnostic anyway with explicit "数据未采集" placeholders
   so the user knows the gap.

3. In `inputs/preferences.yaml`, ensure a `currency_tolerance` block
   exists; if not, add a sensible default:

```yaml
currency_tolerance:
  usd_max_weight: 0.30
  cny_min_weight: 0.50
```

## Acceptance criteria

- Re-running on 2026-05-19 inputs produces a memo containing an "外汇与
  QDII敞口" subsection with: total qdii weight, tolerance check status,
  and either premium data or an explicit "未采集" placeholder.
- For inputs where QDII weight < 0.20, the subsection is omitted.
- Tests verify the threshold logic and tolerance comparison.

## Tests to add

- `tests/memo/test_fx_diagnostics.py`:
  - qdii_weight 0.25, usd_max 0.30 → present, within tolerance
  - qdii_weight 0.35, usd_max 0.30 → present, exceeded
  - qdii_weight 0.10 → block omitted
