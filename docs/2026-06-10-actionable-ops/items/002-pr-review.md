Verdict: PASS-WITH-NITS

Source: Independent second-pass /code-review (2026-06-10, claude-sonnet-4-6)
PR comment: https://github.com/snowshine0216/investment-research-copilot/pull/125#issuecomment-4669413961
Fix round: dc731b9 — re-verified 2026-06-10 (tests re-run + direct repro confirmation)

## Findings (all addressed in dc731b9 unless noted)

### Latent Bug (blocker) — FIXED (dc731b9)

- `src/irc/notify/classify.py:_decide()` — latent-bug — Any exit code NOT in `_EXIT_LABELS`
  (e.g. 127 = uv entry-point not found, 137 = SIGKILL/OOM, 143 = SIGTERM before watchdog fires)
  fell through all checks and reached `"clean"` when `outputs/<today>/` already existed from a
  prior run with zero counts. False-clean notification masked a real failure.
  **Fix verified:** catch-all `if outcome.last_exit_code != 0` guard with
  `_EXIT_LABELS.get(code, f"exit {code}")` fallback, placed before the halted/stale/action
  branches. Six new tests (127/137/143/99 parametrized + precedence-over-halted/stale +
  never-clean) — all green. Direct re-verification: exit 137 + existing today-dir with zero
  counts → `severity='failed'`, `notify=True`, title "IRC run failed — exit 137"; exit 0
  still flows to clean. False-clean path confirmed dead.

### Nits

- `ops/launchd/uninstall.sh` — nit — FIXED (dc731b9): now mirrors install.sh's WRAPPERS
  array and removes the templated `run-daily.sh` / `run-weekly-full.sh` copies from
  `~/Library/LaunchAgents/` alongside the plists.
- `src/irc/commands/notify_cmd.py:_resolve_notify_on_clean` — nit — FIXED (dc731b9):
  `IRC_NOTIFY_ON_CLEAN` accepted truthy/falsy values now documented in
  `ops/launchd/README.md` (truthy: 1/true/yes/on; any other non-empty value falsy;
  unset/empty defaults truthy) and in the expanded `--notify-on-clean` CLI --help string.
- `src/irc/commands/notify_cmd.py:_build_outcome` (32 lines), `_dispatch` (21 lines) — nit —
  SKIPPED WITH REASON: cohesive edge functions (I/O gathering / two-channel dispatch);
  splitting would not improve clarity. Accepted; remains the only open nit.

## Re-verification gates (2026-06-10, post-dc731b9)

- `uv run pytest tests/notify/ -q` → 40 passed
- `uv run pytest tests/notify/ tests/commands/test_notify_cmd.py tests/ops/ -q` → 73 passed
- Direct repro script: exit 137 / 127 with stale today-dir → `failed`; exit 0 → `clean`

## What Looks Good

- httpx token-leak fix (`logging.getLogger("httpx").setLevel(logging.WARNING)`) + root-scoped
  AC7 test with counterfactual verification: solid.
- `set -e` + `wait` adversarial fix (`wait "$_PID" || rc=$?`) with real-wrapper regression test
  in `tests/ops/test_wrappers.py`: load-bearing and proven.
- ADR 0015 null semantics (missing key = `None`, not `0`) correctly propagated end-to-end.
- Pure/impure separation: `classify.py`, `calendar.py`, `message.py`, `types.py` are pure;
  all I/O confined to `notify_cmd.py`. Frozen dataclasses throughout.
- Table-driven tests in `test_classify.py` and `test_wrappers.py` are high quality.
