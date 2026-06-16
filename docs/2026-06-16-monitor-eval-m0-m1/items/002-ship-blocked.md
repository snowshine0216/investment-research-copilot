# 002 ship-blocked — /ship steps 8+9 review findings (pre-push)

`/ship` pre-landing (code-reviewer + silent-failure-hunter) + adversarial review found real P0s.
Fixing before the PR opens (ship.md "review can demand fixes before push"). After fixes + green,
/ship resumes; clean review captured into items/002-review.md.

NOTE on scope: staleness.py is an M0 file but was *build-not-wire* in M0 (OQ3). M1 is the first
consumer (the GATING_STAGES_M1 flip wires resolve_health into the live run), so its latent bugs are
only reachable through M1 — fixing them here is in-scope for M1.

## Must-fix (this fix round)

1. **[P0 · wrong-gate] `src/irc/monitor/eval/staleness.py:15` `resolve_health(None)` hardcodes stage
   `"monitor_suite"`.** `apply_eval_gate` filters `h.stage in gating_stages`; `"monitor_suite"` is
   NOT in `GATING_STAGES_M1 = {monitor_signal, monitor_impact, monitor_narrative}`, so an ABSENT
   suite report is silently dropped → the fund stays `validated` instead of the intended fail-open
   `caveated`. On first deploy (no eval run yet) every fund is falsely `validated` w.r.t. the LLM
   suites. Fix: add a `stage: str` param to `resolve_health` and use it for the `None` (and ideally
   keep `report.stage` for the others); the `_suite_healths` caller in monitor_cmd.py passes the
   queried stage. Tighten the test to assert `badge == "caveated"` for a missing report (NOT
   `in ("caveated","validated")`, which masks this bug).

2. **[P0 · crash] `src/irc/monitor/eval/staleness.py:18` `datetime.fromisoformat(report.ran_at)` is
   unguarded.** A report with `ran_at=""` or any non-ISO value survives `_parse_report` (it only
   catches JSONDecodeError) and raises `ValueError` inside `resolve_health`, which propagates through
   `_suite_healths → _compute_gates → run_monitor`, crashing the daily brief. Spec §5 wants
   corrupt/missing → UNKNOWN/caveated, not a crash. Fix: wrap the parse in try/except →
   `StageHealth(report.stage, "UNKNOWN", ("corrupt_ran_at",))`. Add a regression test.

3. **[P0 · silent false-PASS] scorers count a degraded/empty LLM output as a PASS.**
   `src/irc/monitor/eval/metrics_impact.py` `injection_resistance` (and `magnitude_band_pass`) use
   `all(... for r in _impacts(o))` — when `drive_case` degrades (transport error → appends `{}`),
   `_impacts({})` is `[]` and `all([])` is vacuously True → the failed case counts as a hit. With one
   injection case, a single transport error → `injection_resistance == 1.0` (PASS at fail_below 0.95).
   `metrics_narrative.py` `hallucination_rate`: an all-degraded run → `total == 0` → returns 0.0 →
   PASS. Spec §5: a transport error scores as a CATEGORY FAILURE, never a pass. Fix: a "hit" requires
   the output to actually contain the relevant payload (`_impacts(o)` non-empty / claims present); and
   distinguish "0 cases actually evaluated" from "all passed" — when a category has cases but none
   produced usable output, the metric must be a FAIL (e.g. return 0.0 for resistance / a FAIL sentinel
   for hallucination), not a vacuous pass. Add tests feeding degraded `{}` outputs.

4. **[P0 · crash] live runners call `record_command_run` unguarded.**
   `evals/monitor_impact/runner.py` + `evals/monitor_narrative/runner.py` call `record_command_run`
   as the last statement. On the single-stage path (`irc eval monitor_impact` → `_run_live_gated` →
   runner) there is NO try/except (unlike `_run_active_suite`'s BLE001 guard), so a `record_command_run`
   RuntimeError (corrupt spend_actuals.json) crashes with a traceback AFTER `write_report` succeeded.
   Fix: wrap `record_command_run` in try/except in each runner, log (`exc_info=True`) + continue —
   mirror `monitor_cmd.py`'s `_write_eval_artifacts` degrade-not-crash pattern. Add a test.

5. **[P1 · coverage gap] narrative `injection` corpus case is loaded + billed but NOT scored.**
   `src/irc/monitor/eval/cases/narrative/injection_1.json` has `category == "injection"` but no
   `metrics_narrative.py` scorer filters on it — it only pads the `citation_resolution` denominator.
   Spec §3.1 narrative lists an "injection / directive ignored" category, so this is a missing
   acceptance check. Fix: add a `injection_resistance` scorer to `metrics_narrative.py` (faithful to
   the case's `expected`/`must_ignore`: a resistant output ignores the injected directive — its
   citations stay ⊆ pool and it contains no fabricated numbers / unresolved refs), register it in the
   narrative runner's metrics, and add the threshold (mirror impact: fail_below 0.95). Add tests.

6. **[P1 · latent] `metrics_impact.py:48` `magnitude_band_pass` `exp["max_abs"]` KeyError / ignores
   `max_abs` when both bounds present.** `ok = mag >= exp["min_abs"] if "min_abs" in exp else
   mag <= exp["max_abs"]` raises KeyError if a case has neither bound, and silently ignores `max_abs`
   if a case has both. Fix: defensive `exp.get(...)` and check BOTH bounds when present
   (`(min is None or mag>=min) and (max is None or mag<=max)`). Add a test.

7. **[P1 · observability] `evals/monitor_suite/driver.py` `drive_case` swallows transport/parse
   errors with no logging** (no logger in the module). Fix: add `logging.getLogger(__name__)` and log
   each swallowed error with `exc_info=True` before degrading the case. (Pairs with finding 3 — the
   error must be both LOGGED and scored as a category failure.)

## Rejected (NOT a bug — documented for the record)
- **[adversarial P0 — REJECTED] `worst_status` KeyError on a `SKIPPED` metric.** `classify_status`
  only ever returns PASS/WARN/FAIL (its `fail/warn is not None` guards return PASS otherwise); no
  scorer emits a `SKIPPED` metric status. `SKIPPED` is only ever a whole-stage `overall` (via
  `skipped_report`), never a metric fed to `worst_status` — exactly the M0 design invariant
  (source §2.7). Verified in evals/_shared/status.py. No change.

## Constraints for the fix
- Address ONLY the must-fix list (1–7). Do not refactor adjacent code.
- TDD: write/extend the failing test first for each behavior change (degraded-output FAIL, naive/
  corrupt ran_at, missing-report caveated, runner record guard, narrative injection, band bounds).
- staleness.py changes also require updating its existing tests + the gate-flip test
  (test_gate_flip_m1.py) to assert the corrected `caveated` behavior.
- Keep pure scorers pure; effects (logging, record_command_run) only in driver/runner edges.
- `uv run ruff check src tests evals` clean; the live_llm test stays double-gated (do not unskip).
