# Ship-blocked — /ship steps 8+9 review found P0 + spec-completeness gaps

`/ship` pre-landing (code-reviewer + silent-failure-hunter) + adversarial review surfaced issues that block the push. Routed through triage-fix BEFORE opening the PR (ship.md "review can demand fixes before push"). Grounded against the actual code (not just the review summaries).

## P0 — must fix
1. **Permutation null is a no-op** — `evals/monitor_forward/metrics.py:51,53`. `stat = lambda rs: hit_rate([r["pred"] for r in rs], ...)` reads `pred`, but `random_null_delta(..., label_key="label")` shuffles `label`. Since `pred==label` per row (both `sign(raw_composite)`), the permuted statistic is constant → `delta==0`, `ci_low==0` → the `ci_low > 0` PASS gate is unreachable AND the review-trigger random delta is always 0. Fix: `stat` reads `r["label"]` (the shuffled key); `pred==label` keeps the metric value/CI unchanged.

## Spec-completeness gaps (documented scope; not silently droppable)
2. **Retro half unwired** — `runner.py:72` passes `retro_points=[]`; `build_metric_reports` ignores the param; `run_backtest` (Phase 4) is never called. Spec §1 ("two halves"), §3, §5.2 ("runner reads ... + retro NAV history") require retro computed + surfaced. Fix: runner loads `load_monitor_config` fund set + `cfg.history.minimum_observations`, runs `run_backtest` per fund over its `nav_by_fund` series, surfaces the retro directional hit-rate in the `raw_composite_directional` details under a labeled `retro` block (§4.1 "directionally analogous, not directly comparable" → labeled, NOT merged into the forward value; stays 3 MetricReport rows per §5.3).
3. **Momentum baseline permanently stubbed** — `metrics.py:63` hardcodes `momentum: {"state": "baseline_unavailable"}`; `momentum_dir`/`momentum_defined` (baselines.py, tested) never called. Spec §4.4 requires the momentum paired-delta computed from the `<= as_of_date` slice, degrading to `baseline_unavailable` only when survivors span `< N_MIN_BLOCKS`. Fix: runner computes per-row momentum dir from `nav_by_fund[fund_id]` sliced at `as_of_date`; metrics computes the paired delta, drops undefined rows under `excluded.momentum_undefined`.

## P1 — runner/edge robustness (spec §5.2/§8)
4. **Ledger parse + scorer-invariant propagate as tracebacks** — `runner.py:66,69`. Malformed ledger line crashes `[json.loads(ln) ...]`; `score_forward` `ValueError` (scorer invariant) bubbles out. Spec §8: malformed lines → skip+log, ALL bad → FAIL; scorer-invariant → FAIL (clean rc 2, not traceback).
5. **`bias_to_sign` KeyError** on an unexpected `raw_bias` enum value — `metrics.py:37`. Guard/skip unknown-bias rows.
6. **`_excl` exclusions discarded** — `runner.py:69` throws away `score_forward`'s exclusion dict; not in details.json, not logged. Surface under details + `_log.info`.
7. **Swallow paths lack logging** — `monitor_cmd.py:_load_details` (no log, over-broad except), `nav_history.py:47` (no exc_info), `scripts/backfill_nav_history.py` (json/ValueError unhandled → no clean rc 1). `_is_stale` imports `date` inside the function body (move to module level).

## Accepted (not fixed)
- 1-bucket bootstrap CI degeneracy (`(v,v)`) — correct-by-design, P2.
- `retro_points` was a dead param — resolved by fix #2.

## Resolution
Fix-1 (this round): #1, #4, #5, #6, #7. Fix-2: #2, #3. Re-run tests + review; then push + open PR; capture the clean review into `001-review.md`.
