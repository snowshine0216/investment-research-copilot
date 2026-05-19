# 013 — Plan

## Steps

1. New module `src/irc/memo/diagnostics.py` (pure functions):
   - `compose_execution_drift_lines(allocation, cash_target_weight)`:
     returns a 3-line alert tuple when `cash_residual_weight -
     cash_target_weight >= 0.05`, else empty tuple. Lines: drift
     header, affected-instruments detail, remediation options.
2. `src/irc/commands/memo_cmd.py`:
   - Read `bundle.preferences.asset_class_targets["cash"].center` for
     the target.
   - Compute drift lines and prepend to `risk_notes` tuple so they
     reach the LLM skeleton and the audit gate.
3. `tests/memo/test_diagnostics_execution_drift.py`:
   - residual 0.05 / target 0.05 → no alert
   - residual 0.15 / target 0.05 → 3-line alert with "10.0pp" copy
   - lists zero-weight instruments, ignores filled ones
   - missing alloc / missing diagnostics → empty
   - threshold-boundary case (5pp exact) → emits
