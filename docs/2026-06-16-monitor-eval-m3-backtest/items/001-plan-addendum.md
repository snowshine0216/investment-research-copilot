# Plan addendum — post-review corrections (ship steps 8+9)

The original plan (Phase 8 assembly) under-delivered three spec requirements that the drift check could not catch (drift verifies impl-vs-plan; the plan itself was under-specified). `/ship`'s pre-landing + adversarial review caught them. These corrections amend the plan (drift-check.md "amend the plan when it was under-specified is legal"). See [001-ship-blocked.md](001-ship-blocked.md) for the full findings.

## Corrections applied (commits 5efe3cd..b7ae072)

| # | File | Correction | Spec ref |
|---|------|-----------|----------|
| 1 | `evals/monitor_forward/metrics.py` | Permutation-null `stat` reads `r["label"]` (the shuffled key), not `r["pred"]` — was a no-op, making PASS unreachable + the review-trigger random delta always 0. | §4.4, §6 |
| 2 | `runner.py` + `metrics.py` | **Retro half wired**: runner loads `load_monitor_config` fund set + `cfg.history.minimum_observations`, runs `run_backtest` per fund over its `nav_by_fund` series; retro directional hit-rate surfaced in `raw_composite_directional.details.retro` (labeled "directionally analogous, not directly comparable"; empty→`insufficient_data`). Still 3 MetricReport rows. | §1, §3, §4.1, §5.2, §5.3 |
| 3 | `runner.py` + `metrics.py` | **Momentum baseline computed** (was permanently stubbed): per-row momentum dir from the `<= as_of_date` slice; paired block-bootstrap delta; `momentum_undefined` paired exclusion; `< N_MIN_BLOCKS` survivors → `baseline_unavailable`. `buy_hold` upgraded to the same paired bootstrap. | §4.4 |
| 4 | `runner.py` | Malformed ledger lines skipped+logged (ALL bad → FAIL); `score_forward` `ValueError` (scorer-invariant) → clean rc 2 FAIL, not a traceback. | §8 |
| 5 | `metrics.py` | `_bias_rows` guards unknown `raw_bias` → counted `excluded.unknown_bias`, no KeyError. | §4.1 |
| 6 | `runner.py` | `score_forward` exclusions logged + surfaced in `details.json` (`forward_excluded`). | §5.3 |
| 7 | `monitor_cmd.py` / `nav_history.py` / `backfill_nav_history.py` | Swallow paths log with `exc_info`/narrowed exceptions; backfill returns rc 1 on corrupt trace; `date` import hoisted to module level. | §2.1, §6, §8 |

## Design decision (retro surfacing)
Spec §5.3 pins exactly three MetricReport rows; §4.1 says retro and forward are "directionally analogous, NOT directly comparable." So retro is NOT a 4th row and does NOT change the `raw_composite_directional` row `value` (which stays the FORWARD published-signal hit-rate). It lives in that row's `details.retro` sub-block, labeled. This is the minimal spec-honoring surfacing.

## Verification
`tests/evals/ tests/monitor/eval/` → only the known pre-existing `test_dag_acyclic_check_true_for_valid_imports` fails; monitor-command regression (43) green; ruff clean; runner import triggers no network.
