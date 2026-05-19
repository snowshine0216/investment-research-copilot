# 013 — Execution-drift alert

## Why

`proposed_allocation.yaml` had cash residual = 0.15 vs cash target = 0.05.
The cn_etf lines (515080, 510050, 512960) and 511520 all collapsed to
0% `target_weight` due to venue mismatch and no proxy. The memo treats
this as "现金弹性" (cash flexibility) — but a 10pp drift into
uncompensated cash is a material risk decision never surfaced to the user.

The adversarial review (§C3 and priority #9) demands an alert when ≥5pp
of target weight can't be filled, with named remediation.

## What changes

1. In `src/irc/decision/report.py` (or wherever the decision diagnostics
   are assembled), compute:

```python
execution_drift = max(0.0, cash_residual_weight - cash_target_weight)
```

   where `cash_target_weight` comes from preferences / discipline.

2. If `execution_drift >= 0.05`, attach an `execution_drift` alert to
   the decision report with:
   - `drift_pct`: pct points
   - `affected_instruments`: list of (instrument_id, name, intended_weight,
     reason) tuples for rows that collapsed to 0
   - `remediation_options`: a constant list:
     - "open the missing brokerage venue"
     - "configure a proxy for affected instruments"
     - "rebalance unfilled weight into compatible substitutes"

3. In `src/irc/memo/synthesizer.py` (and `template.py`), surface the
   alert as a dedicated bullet in Section 4 (资产配置) titled
   **"执行漂移提醒"**.

## Acceptance criteria

- Re-running on the 2026-05-19 inputs produces a memo whose Section 4
  contains an `执行漂移提醒` block listing the four collapsed instruments
  and the 10pp drift.
- For inputs where `execution_drift < 0.05`, the block is omitted.
- Unit tests verify the threshold logic and the list of affected
  instruments.

## Tests to add

- `tests/decision/test_execution_drift.py`:
  - residual 0.15, target 0.05 → drift 0.10, alert emitted
  - residual 0.07, target 0.05 → drift 0.02, no alert
  - residual = target → no alert
