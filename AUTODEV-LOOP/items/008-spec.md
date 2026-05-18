# 008 — Trade_plan runner modernization

## Problem

`evals/trade_plan/runner.py` reads `outputs/trade_plan/trades.json` (retired). Current producer (`src/irc/commands/plan_cmd.py`) writes `outputs/<date>/trade_plan.yaml` with shape `{"mode": str, "trades": [TradePlanRow, ...]}`. The historical metrics looked at old field names (`venue`, `instrument_class`, `trigger` singular) that the producer no longer emits.

## Producer's TradePlanRow (`src/irc/trades/pipeline.py:12`)

```python
class TradePlanRow(TypedDict):
    target: str
    asset_class: str
    role: str
    target_weight: float
    intra_class_share: float
    composite_score: float
    buy_method: str
    granularity: str
    venue_compatible: bool
    venue_note: str
    proxy_id: str | None
    triggers: list[dict[str, Any]]
```

## Required behavior

- Locate `trade_plan.yaml` via shared locator.
- Parse YAML; trades list lives at `payload["trades"]`.
- Update metric implementations to read the current field names:
  - `venue_compatibility_marked` → checks `venue_note` is a non-empty string (was: `venue`).
  - `buy_method_class_match` → reads `asset_class` (was: `instrument_class`). Allowed-class map extended for `cn_etf` and `global_etf` (the producer's real asset_class values).
  - `trigger_monitorability` → reads `triggers` list (was: `trigger` string).
- Update metric and runner tests to use TradePlanRow-shaped fixtures.

## Acceptance criteria

- Runner uses locator + `write_report`; the retired JSON path is gone.
- Metric functions read the current field names; behavior is semantically equivalent.
- All targeted tests pass; full evals suite passes; full repo suite still passes.

## Files touched

- `evals/trade_plan/runner.py` (rewrite)
- `evals/trade_plan/metrics.py` (rewrite with new field names)
- `tests/evals/test_trade_plan_runner.py` (YAML fixture + new cases)
- `tests/evals/test_trade_plan_metrics.py` (TradePlanRow-shaped fixture)
