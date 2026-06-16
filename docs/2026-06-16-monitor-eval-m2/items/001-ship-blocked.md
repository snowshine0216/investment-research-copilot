# /ship pre-push review findings (step 8) — routed to fix before push

Source: /ship steps 8 (pr-review-toolkit:code-reviewer + silent-failure-hunter)
Branch: claude/monitor-eval-m2-001

The conservative code-reviewer found 0 P0; the silent-failure-hunter flagged 2 P0 + 1 P1.
Orchestrator adjudication: all three are real latent/robustness bugs in the NEW D2 module,
tied to spec intent. Fixed before push (ship.md "review can demand fixes before push").

## Findings to fix (round 1)

- **A (latent bug) — `diff_signal`/`_diff_contributions` mask a MISSING recorded key as a match.**
  `src/irc/monitor/eval/determinism.py:63-70,78,84,86,92`. `rc.get("renorm_weight", 0.0)` /
  `recorded.get("composite", 0.0)` etc. fall back to the default; if the recompute also yields the
  default, an *absent* key passes silently. Spec §1 makes "malformed … persisted trace passing
  unnoticed" the exact gap D2 closes — an absent field IS a mismatch and must FAIL. Treat a missing
  recorded key (float fields + composite/available_weight/signal_confidence + present_families +
  divergence_codes + per-contribution fields) as a diff entry.

- **C (robustness) — panel-only check can crash the whole brief.**
  `src/irc/commands/monitor_cmd.py` `_compute_gates` calls `deterministic_health(fund.id, projection)`
  with no error boundary; a bare `KeyError` (missing `resolved`/`factor_scores`/`signal`) or a
  `compute_signal` raise propagates out of `_compute_gates` and aborts the run with no per-fund log.
  `deterministic_scoring` is panel-only/informational ("no runtime gate") → it must never crash the
  run. Wrap the per-fund call at the EDGE (monitor_cmd.py), log via the module logger, degrade to a
  FAIL `StageHealth` naming the fund. Keep `determinism.py` PURE (no logging there).

- **B (latent trap) — `worst_status` KeyError on `"UNKNOWN"`.**
  `_row` (`determinism.py:130-135`) calls `worst_status(statuses)`; `evals/_shared/status.py` `_RANK`
  has no `"UNKNOWN"`, yet `ValidationPanelRow.status` documents UNKNOWN. Cannot fire today (healths
  only emit PASS/WARN/FAIL) but is a one-refactor-away crash. Add a LOCAL guard in `_row` so an
  unrecognized status does not KeyError. Do NOT modify `evals/_shared/status.py` (shared, out of scope).
