# Item 001 — Plan

## Goal
Make the `weekly_drawdown` branch in `emit_triggers_for_trade` actually fire for CN-side trade rows.

## Steps

### 1. Write the failing test first (RED)

File: `tests/trades/test_triggers.py`

If the file exists, append the new test. If not, create it.

```python
from irc.schemas.triggers import TriggersConfig, Trigger
from irc.trades.triggers import emit_triggers_for_trade


def _cfg() -> TriggersConfig:
    return TriggersConfig(triggers={
        "real_yield_low": Trigger(data_field="macro.real_yield_10y_tips",
                                  comparator="<=", threshold=0.0),
        "vix_high": Trigger(data_field="macro.vix",
                            comparator=">", threshold=25.0),
        "weekly_drawdown_4pct": Trigger(data_field="instrument.weekly_return",
                                        comparator="<=", threshold=-0.04),
    })


def test_cn_etf_emits_weekly_drawdown_trigger():
    out = emit_triggers_for_trade(
        asset_class="cn_etf", buy_method="small_account_anchor", cfg=_cfg(),
    )
    names = [t["name"] for t in out]
    assert "weekly_drawdown_4pct" in names, f"expected weekly_drawdown_4pct in {names}"


def test_us_etf_does_not_emit_weekly_drawdown():
    out = emit_triggers_for_trade(
        asset_class="us_etf", buy_method="small_account_anchor", cfg=_cfg(),
    )
    names = [t["name"] for t in out]
    assert "weekly_drawdown_4pct" not in names
    assert "vix_high" in names


def test_cn_bond_fund_with_dca_emits_drawdown():
    out = emit_triggers_for_trade(
        asset_class="cn_bond_fund", buy_method="dca_normal", cfg=_cfg(),
    )
    names = [t["name"] for t in out]
    assert "weekly_drawdown_4pct" in names
```

Run: `uv run pytest tests/trades/test_triggers.py -x` — confirm the first test fails with `expected weekly_drawdown_4pct in []`.

### 2. Fix the code (GREEN)

File: `src/irc/trades/triggers.py`

Change line 30 from:

```python
or (name == "weekly_drawdown" and _wants_weekly_drawdown(asset_class, buy_method))
```

to:

```python
or (name == "weekly_drawdown_4pct" and _wants_weekly_drawdown(asset_class, buy_method))
```

That's it — single-string change. No new helper, no signature change.

Run: `uv run pytest tests/trades/test_triggers.py -x` — confirm all 3 new tests pass.

### 3. Full suite

```
uv run pytest -x
```

Expect: 1222 collected + 3 new = 1225 tests, all passing. Investigate any regressions before opening the PR.

### 4. Commit + push

```
git switch -c claude/fix-memo-audit-001 main
git add src/irc/trades/triggers.py tests/trades/test_triggers.py
git commit -m "fix(triggers): match config key weekly_drawdown_4pct (001)

Branch in emit_triggers_for_trade matched the literal string
'weekly_drawdown' but the config key is 'weekly_drawdown_4pct',
so CN-side trade rows shipped with no drawdown trigger.

Outputs/2026-05-18/trade_plan.yaml every CN row had triggers: [].
"
git push -u origin claude/fix-memo-audit-001
```

### 5. Orchestrator opens the PR (skill rule — implementation subagent must not).

## Reporting back

Subagent reports: branch name, commit SHA, `uv run pytest tests/trades/test_triggers.py` summary, `uv run pytest` summary, any deviations.
