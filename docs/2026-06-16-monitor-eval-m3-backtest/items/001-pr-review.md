Verdict: PASS-WITH-NITS
Source: /code-review on PR #138 (manual diff review — /code-review skill has no GitHub connector; --comment not posted)
PR comment URL: not posted
Findings: 3
  - evals/monitor_forward/metrics.py:167-170 — nit — rank_ic details carry ci_low=ci_high=value (no IC bootstrap); the panel renders [+0.xxx, +0.xxx] which looks like a real CI interval. Intentional placeholder but mildly misleading to human reviewers. No correctness impact.
  - evals/monitor_forward/metrics.py:166 — nit — _ic_report computes effective_n over _composite_rows(rows) (all forward_rows, any status) but only ok-status rows feed the day_ics calculation. So n_observations for rank_ic (=defined IC-day count) and effective_n in details use different populations. Both are advisory/diagnostic only; no gate or metric value is affected.
  - evals/monitor_forward/runner.py:76 — nit — momentum_dir/momentum_defined are imported inside _build_momentum_by_key rather than at module top-level; baselines.py is a pure module with no side effects so this is harmless (no circular-import issue) but unconventional and not consistent with the project's module-level import style.

Context (already fixed pre-PR; NOT re-flagged):
  - P0 permutation no-op (stat read pred not label) — fixed 5efe3cd
  - Retro half unwired — fixed b7ae072
  - Momentum baseline hardcoded stub — fixed b7ae072
  - Runner malformed-ledger / scorer-invariant / bias KeyError / exclusions discarded / swallow-path logging — fixed 38a41f9, c7a6524, e0ac9f2, 534ba67
  - buy_hold_dir() called twice in _buy_hold_delta_paired — fixed (frozen once per row)
