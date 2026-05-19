# 004 — Surface execution-drift banner in decision_report.md

## Why

Trust-check priority #3 and S5: `proposed_allocation.yaml` for
2026-05-19 has `cash_residual_weight = 0.15` vs target `0.05` = **10pp
of NAV** sitting in cash because `511520/159650` are venue-blocked
and not re-routed. The prior 013 surfaces this in `memo.md` §4 but
`decision_report.md` is silent — the layperson never sees it.

## What changes

`src/irc/decision/report.py`:

1. In `compose_decision_report`:

```python
cash_target = float(
    allocation.get("target_weights_per_class", {}).get("cash") or 0.0
)
cash_residual = float(
    allocation.get("diagnostics", {}).get("cash_residual_weight") or 0.0
)
drift = max(0.0, cash_residual - cash_target)
execution_drift = (
    {"drift_pct": drift, "cash_target": cash_target,
     "cash_residual": cash_residual}
    if drift >= 0.05
    else None
)
```

2. Add `execution_drift` to the report dict.

3. In `render_decision_markdown`, render a banner after the Verdict
   line when `execution_drift` is non-null:

```markdown
> ⚠️ **执行漂移提醒 / Execution drift**: 现金残余权重 15% > 目标 5%
> (drift +10pp). 多个目标未填仓 — 详见 memo.md §4 与
> trade_plan.yaml. 仅做提醒，不阻断本周决策。
```

## Acceptance criteria

- `cash_residual − cash_target >= 0.05` → banner appears in
  rendered markdown.
- Drift < 5pp → no banner.
- `execution_drift` field in report dict is `None` when no drift,
  otherwise a dict with `drift_pct`, `cash_target`, `cash_residual`.
- Existing tests still pass.

## Tests to add

`tests/decision/test_three_section_markdown.py`:

- `test_execution_drift_banner_emitted_when_above_threshold`
- `test_execution_drift_banner_suppressed_when_below_threshold`
- `test_execution_drift_field_in_report_dict`
- `test_execution_drift_handles_missing_diagnostics`
