# 012 — Symmetric trim-side discipline triggers

## Why

The adversarial review (§F) flags that all configured triggers
(`real_yield_low`, `vix_high`, `weekly_drawdown_4pct`) are buy-side.
The discipline doc mentions "trim_review when valuation in [expensive,
very_expensive]" — but every equity row in today's memo is already
very_expensive and none carry `risk: none` → trim. The trim path is
unused.

## What changes

1. In `config/triggers.yaml`, add trim-side triggers:

```yaml
triggers:
  # existing buy-side triggers ...
  valuation_very_expensive:
    data_field: instrument.valuation_state
    comparator: "=="
    threshold: "very_expensive"
  heat_crowded:
    data_field: instrument.heat_state
    comparator: "=="
    threshold: "crowded"
  weight_above_band_high:
    data_field: instrument.weight_vs_band_ratio
    comparator: ">="
    threshold: 1.10  # 10% over band high
```

2. In `src/irc/opportunity/discipline.py`,
   `derive_risk_action(row, position)`:
   - Emit `risk: trim_review` (not `none`) when any of the trim triggers
     fires. Today the function only watches `do_not_sell_just_because`
     conditions and ignores trim conditions.
   - Distinguish `trim_review` from `trim_now`: only the
     `weight_above_band_high` trigger goes to `trim_now`. Valuation /
     heat triggers go to `trim_review` (operator decides).

3. In `src/irc/opportunity/cards.py`, the existing `_TRIM_TRIGGERS`
   constant matches the new yaml. Have the card builder include
   `risk_action` derived from the active triggers, not just a static
   list.

## Acceptance criteria

- A row with `valuation_state="very_expensive"`,
  `heat_state="overheated"` emits `risk: trim_review` with a rationale
  string naming the active trigger(s).
- Today's regenerated `trade_plan.yaml` shows `trim_review` rows on
  the equity instruments that flagged very_expensive.
- Buy-side triggers continue to fire unchanged.

## Tests to add

- `tests/opportunity/test_trim_triggers.py`:
  - very_expensive + crowded → trim_review
  - fair + normal → none
  - weight 12% with band high 10% → trim_now
