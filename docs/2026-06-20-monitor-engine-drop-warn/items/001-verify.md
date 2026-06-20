Verdict: PASS

Subagent: sonnet
Source: /verify
Entry point exercised: `evals.monitor_forward.runner.run(tmp_path)` called directly from a Python driver script (three fixture scenarios constructed in `tempfile.TemporaryDirectory()`), matching the pattern used in `tests/evals/test_monitor_forward_runner.py`.

Observed behavior:

  - AC1: 4th metric named `engine_population` present — `metric names = ['raw_composite_directional', 'publishable_bias_directional', 'rank_ic', 'engine_population']` (Scenario A + B + C all produce 4 metrics)

  - AC2 (engine-transition ledger, WARN path): Scenario A — 3 legacy-engine-"0" rows + 1 engine-"2" row. `engine_population` row: `status=WARN`, `details["engine_population"]["state"] == "engine_transition"`, `ci_low: null`, `ci_high: null`. Stage `rc = 1` (WARN). Exact details block observed:
    ```json
    {
      "state": "engine_transition",
      "ci_low": null,
      "ci_high": null,
      "headline_low_n": true,
      "headline_metric": "publishable_bias_directional",
      "headline_state": "insufficient_data",
      "n_excluded": 3,
      "n_total_raw": 4,
      "n_target_raw": 1,
      "value_population": "raw_ledger_target_engine_share",
      "n_observations_population": "matured_target_engine_effective_n_blocks",
      "n_min_blocks": 8
    }
    ```
    `details["excluded_by_engine"] = {"target_engine": "2", "engine_mismatch": 3}`

  - AC3 (single-engine / no mismatch, PASS path): Scenario B — single engine-"1" row. `engine_population` row: `status=PASS`, `state="ok"`. Stage `rc = 1` (WARN) driven by the existing headline metrics (`insufficient_data`), NOT by `engine_population`. Confirms D3: `engine_population` PASS did not further raise or lower stage status.

  - AC4 (sanity — existing 3 metrics unchanged): All three scenarios show `raw_composite_directional`, `publishable_bias_directional`, `rank_ic` present with expected statuses (WARN on thin/empty data). Empty-ledger Scenario C: `engine_population` is `status=PASS`, `value=0.0`, `state="ok"`, `n_target_raw=0`, no ZeroDivisionError, `rc=1` (WARN from headline metrics).

Failures: none

Additional observations:
  - The `_build_retro_points` fallback fires in all tmp-dir scenarios (no `config/monitor.yaml`) and degrades gracefully with a logged warning, not an exception — correct behavior.
  - `details_ref` is repo-relative (`outputs/2026-06-20/evals/monitor_forward/details.json`) on all 4 metric rows, as required by the existing contract.
  - The engine-transition `value` = 0.25 (1 of 4 raw rows on target engine) renders correctly as a 0..1 progress meter per spec §4.
