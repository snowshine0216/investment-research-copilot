# Item 001 — Fix `weekly_drawdown` trigger key mismatch

## What

`config/triggers.yaml` keys the per-instrument drawdown trigger as `weekly_drawdown_4pct`. But `src/irc/trades/triggers.py:30` matches the literal string `weekly_drawdown`. The branch never fires, so every `cn_etf` / `cn_equity_fund` / `cn_bond_fund` row in `trade_plan.yaml` ships with `triggers: []`.

Evidence in today's output: `outputs/2026-05-18/trade_plan.yaml:110, 122, 134, 146, 158, 170, 182, 194, 206, 218, 230, 242` — every CN-side row has `triggers: []`.

## Files to touch

- `src/irc/trades/triggers.py`
- `tests/trades/test_triggers.py` (add the regression test)

## Acceptance criteria

- A new test fails before the change with body "expected 1 trigger, got 0 for a cn_etf/cn_equity_fund/cn_bond_fund row whose `buy_method` is `small_account_anchor` and whose drawdown trigger is configured in `triggers.yaml` as `weekly_drawdown_4pct`".
- After the change the same test passes.
- The fix is a one-string change. Match the config key (`weekly_drawdown_4pct`) inside `triggers.py:30`. Do NOT rename the config key — it's user-facing and may already be in `config/overrides.yaml`.
- The full suite (`uv run pytest`) is green.
- An add-on assertion: every literal key checked inside `emit_triggers_for_trade` must exist in the supplied `cfg.triggers`. Implement as a tiny `_validate_trigger_keys_referenced(cfg)` helper invoked once at module import in tests (skip in prod to avoid module-import side effects).

## Out of scope

- Reshaping `triggers.yaml`. Defer to a future refactor that names triggers semantically (`drawdown_*`, `vol_*`).
- Changing what counts as a `cn_*` trigger candidate.

## Reference snippets

```yaml
# config/triggers.yaml
triggers:
  weekly_drawdown_4pct:
    data_field: instrument.weekly_return
    comparator: "<="
    threshold: -0.04
```

```python
# src/irc/trades/triggers.py:26-31  (current — broken)
for name, t in cfg.triggers.items():
    keep = (
        (name == "vix_high" and _wants_vix(asset_class))
        or (name == "real_yield_low" and _wants_real_yield(asset_class))
        or (name == "weekly_drawdown" and _wants_weekly_drawdown(asset_class, buy_method))
    )
```
