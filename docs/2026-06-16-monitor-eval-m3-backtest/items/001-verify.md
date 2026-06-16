Verdict: PASS

Subagent: sonnet
Source: /verify

Entry point exercised:
  1. `uv run irc eval monitor_forward` (degraded/no-input path)
  2. `uv run python /tmp/m3_smoke.py` (happy-path with tmp repo_root)
  3. `uv run irc eval --all` (suite exclusion)
  4. `uv run pytest tests/monitor/test_acceptance_predictive.py -q` (never-gates acceptance)

Observed behavior:
  - CLI degraded path (§8 FAIL-on-missing-input) — rc 2, stdout: `monitor_forward eval: FAIL (no forward_ledger.jsonl)`. Confirms CLI wires to the runner and missing input yields FAIL not crash.
  - Happy-path end-to-end — rc 1 (WARN, as expected for thin sample), `report.json` written at `outputs/2026-06-16/evals/monitor_forward/`, `details.json` sibling present. StageReport has exactly 3 metric rows: `['raw_composite_directional', 'publishable_bias_directional', 'rank_ic']`. `raw_composite_directional.baseline_deltas` carries `random`, `momentum`, `buy_hold`. `rank_ic.baseline_deltas` carries `random` ONLY (momentum/buy_hold absent as required). No `published_state` key in report or any metric row.
  - Suite exclusion — `uv run irc eval --all` lists 12 stages (data, research, discovery, scoring, gold_score, allocation, trade_plan, memo, architecture, opportunity, triggers, monitor_signal); `monitor_forward` is entirely absent. Green `--all` suite is not data-dependent.
  - Never-gates invariant — `tests/monitor/test_acceptance_predictive.py` 3 passed (0.11s). No `published_state` field found in `evals/monitor_forward/runner.py`, `metrics.py`, or `evals/_shared/report_schema.py` by grep.

Failures: none
