Verdict: FAIL

Source: Independent second-pass /code-review (2026-06-10, claude-sonnet-4-6)
PR comment: https://github.com/snowshine0216/investment-research-copilot/pull/125#issuecomment-4669413961

## Findings

### Latent Bug (blocker)

- `src/irc/notify/classify.py:_decide()` — latent-bug — Any exit code NOT in `_EXIT_LABELS`
  (e.g. 127 = uv entry-point not found, 137 = SIGKILL/OOM, 143 = SIGTERM before watchdog fires)
  falls through all checks and reaches `"clean"` when `outputs/<today>/` already exists from a
  prior run with zero counts. False-clean notification masks a real failure.
  Fix: add a catch-all `if outcome.last_exit_code != 0 and outcome.last_exit_code not in _EXIT_LABELS`
  guard before the `pipeline_halted` branch, returning `severity="failed"`.

### Nits

- `ops/launchd/uninstall.sh` — nit — Removes `*.plist` files but leaves templated
  `run-daily.sh` / `run-weekly-full.sh` wrappers in `~/Library/LaunchAgents/`.
- `src/irc/commands/notify_cmd.py:_resolve_notify_on_clean` — nit — `IRC_NOTIFY_ON_CLEAN=off`
  disables clean notifications (any non-empty string not in `_TRUE` disables). Accepted values
  not documented; a user typing "off" gets the expected behavior but by accident.
- `src/irc/commands/notify_cmd.py:_build_outcome` (32 lines), `_dispatch` (21 lines) — nit —
  Slightly over the CLAUDE.md 20-line function ideal.

## What Looks Good

- httpx token-leak fix (`logging.getLogger("httpx").setLevel(logging.WARNING)`) + root-scoped
  AC7 test with counterfactual verification: solid.
- `set -e` + `wait` adversarial fix (`wait "$_PID" || rc=$?`) with real-wrapper regression test
  in `tests/ops/test_wrappers.py`: load-bearing and proven.
- ADR 0015 null semantics (missing key = `None`, not `0`) correctly propagated end-to-end.
- Pure/impure separation: `classify.py`, `calendar.py`, `message.py`, `types.py` are pure;
  all I/O confined to `notify_cmd.py`. Frozen dataclasses throughout.
- Table-driven tests in `test_classify.py` and `test_wrappers.py` are high quality.
