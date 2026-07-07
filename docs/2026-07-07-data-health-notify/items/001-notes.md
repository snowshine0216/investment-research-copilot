# Item 001 — implementation notes / deviations from the plan

## Task 1: Calendar helpers (`previous_trading_day`, `trading_day_age`)

- **Conservative.** The brief's Step 1 test-append block includes a leading
  `from datetime import date` and a standalone
  `from irc.notify.calendar import previous_trading_day, trading_day_age`
  import. `tests/notify/test_calendar.py` already had `from datetime import date`
  and `from irc.notify.calendar import should_skip_daily`. Appending the brief's
  import lines verbatim would have produced a duplicate `date` import (re-binding
  the same name, which `ruff` flags as F811 redefinition) and two separate import
  lines from the same module. Instead, only the new test functions were appended,
  and the new names (`previous_trading_day`, `trading_day_age`) were merged into
  the existing `irc.notify.calendar` import line: `from irc.notify.calendar import
  previous_trading_day, should_skip_daily, trading_day_age`. Test content, names,
  and assertions are byte-identical to the brief otherwise. `ruff check` passes
  clean; all 12 tests (5 existing + 7 new) pass.

## Task 4: `monitor_health` builder

- **Conservative.** The brief's Step 1 test-append block places `import json`,
  `from datetime import date`, `from pathlib import Path`, and
  `from irc.notify.health import monitor_health` mid-file (after the last
  existing test function), which `ruff` flags as E402 (module-level import not
  at top of file) — confirmed via `git stash` that `ruff check tests/notify/`
  was clean before this task's edits. Moved those four import lines to the
  file's existing top-of-file import block, merging `monitor_health` into the
  existing `from irc.notify.health import HealthDigest, HealthItem,
  health_unknown` line rather than a separate statement. Test names, bodies,
  and assertions are byte-identical to the brief otherwise. `ruff check
  src/irc/notify/health.py tests/notify/test_health.py` passes clean; all 12
  tests in `tests/notify/test_health.py` pass (5 pre-existing + 7 new from this
  task; the brief's own count of "12 tests" in Step 4 already anticipated this).
- **Confirmed non-issue, no deviation:** `_MACRO_AGE_LIMIT_DAYS` (forward-declared
  in Task 3) remains unused after Task 4 — verified against `items/001-plan.md`
  Task 6 (`weekly_health`), which is the sole consumer. `src/irc/notify/health.py`
  is 119 lines, well under the 200-line budget; `ruff check` reports zero
  findings (module-level unused constants aren't flagged by the ruleset in use).
- Task 4 review round added 2 coverage tests (conservative; no production change).

## Task 5: `rotation_health` builder (+ `_abstain_streak`)

- **Conservative.** Same import-placement issue as Task 4: the brief's Step 1
  test-append block includes a standalone `from irc.notify.health import
  HealthDigest, rotation_health` line placed mid-file (after the last existing
  test function), which would re-import `HealthDigest` (already imported at
  top of file) and trigger `ruff` E402 (module-level import not at top of
  file). Merged `rotation_health` into the existing top-of-file `from
  irc.notify.health import HealthDigest, HealthItem, health_unknown,
  monitor_health` line instead, and appended only the 7 new test functions
  (byte-identical to the brief otherwise). `ruff check src/irc/notify/health.py
  tests/notify/test_health.py` passes clean.
- **Confirmed non-issue, no deviation:** the brief's Step 4 says "Expected:
  PASS (19 tests)", but the actual pass count is 21. This is not a regression:
  Task 4's own notes record that its review round added 2 extra coverage
  tests beyond the brief's plan (bringing the pre-existing count from 12 to
  14 before this task started); 14 + 7 new tests from this task = 21. Verified
  by re-reading `tests/notify/test_health.py` before editing — 14 tests present
  pre-Task-5, all pass, none touched.
- `rotation_health` and `_abstain_streak` implemented verbatim from the brief
  (no logic changes). `src/irc/notify/health.py` is 153 lines (budget 200);
  `rotation_health`'s body stays under ~15 lines. `ruff check` clean; all 21
  tests in `tests/notify/test_health.py` pass (14 pre-existing + 7 new).
- Task 5 review round — vacuous test replaced with real corrupt-radar test + docstring clarification (conservative).

## Task 6: `weekly_health` builder

- **Conservative, same import-placement pattern as Tasks 4/5.** The brief's
  Step 1 test-append block includes a standalone `from irc.notify.health
  import weekly_health` line, which would shadow-import `weekly_health` mid-file
  (after the top-of-file import block) and trigger `ruff` E402. Merged
  `weekly_health` into the existing top-of-file `from irc.notify.health
  import (...)` line instead (converted to a parenthesized multi-line import
  since it now carries 6 names) and appended only the 4 new test functions,
  byte-identical to the brief otherwise.
- **Confirmed non-issue, no deviation:** the brief's Step 4 says "Expected:
  PASS (23 tests)", but the actual pass count is 25 (21 pre-existing from
  Task 5's review round + 4 new). Consistent with the same stale-count pattern
  documented in Tasks 4 and 5's notes above.
- `weekly_health` implemented verbatim from the brief (no logic changes).
  Used the pre-staged production-shaped fixture `tests/notify/fixtures/health/gold_regime.json`
  (real 07-04 artifact, committed at `26f242b6`) unchanged — DXY @ 2026-06-16
  is 21 calendar days before the test's `today=2026-07-07`, matching the
  locked G-Q4 assertion text verbatim.
- `_MACRO_AGE_LIMIT_DAYS` (forward-declared in Task 3, flagged as
  unused-but-confirmed-non-issue through Tasks 3–5) is now consumed —
  last forward-declared constant resolved.
- `src/irc/notify/health.py` is 174 lines (budget 200); `ruff check
  src/irc/notify/health.py tests/notify/test_health.py` passes clean; all 25
  tests in `tests/notify/test_health.py` pass (21 pre-existing + 4 new).

## Task 8: Edge gathering — `_build_health` per run-kind + flow-capture outcome

- **Conservative, same import-placement pattern as Tasks 1/4/5/6.** The brief's
  Step 1 test-append block places a standalone `from datetime import date` and
  `from irc.notify.classify import classify_run_outcome` mid-file (after the
  last existing test function). `tests/commands/test_notify_cmd.py` already had
  no top-level `datetime`/`classify` import (only inline per-test imports), so
  appending verbatim triggered `ruff` E402. Moved both lines into the file's
  top-of-file import block instead (`from datetime import date` next to
  `from pathlib import Path`; `from irc.notify.classify import
  classify_run_outcome` next to the existing `from irc.notify.types import
  NotificationDecision`) and appended only the new helpers/test functions,
  byte-identical to the brief otherwise. `ruff check src/irc/commands/notify_cmd.py
  tests/commands/test_notify_cmd.py` passes clean.
- **Substantive, spec-locked (not a bug): 3 pre-existing back-compat tests
  needed companion-artifact seeding.** `_build_outcome` now calls
  `_build_monitor_health`/`_build_weekly_health` for every `monitor`/`weekly`
  run, and per spec AC5 ("Corrupt/absent `eval_trace.json` → body contains
  `health unknown`") a *missing* companion artifact is intentionally
  indistinguishable from a corrupt one — both degrade to `health_unknown()`,
  which escalates `clean`/`action` to `degraded` (§3.2). Three tests predate
  Task 8 and asserted `clean`/`action` severity while only ever seeding
  `monitor.json` / `decision_report.json` (never `eval_trace.json`,
  `fund_flow_series.json`, or `gold_regime.json`), so they started asserting a
  severity the new health gate correctly no longer produces:
  `tests/notify/test_monitor_run_kind.py::test_monitor_success_when_monitor_json_present`,
  `tests/notify/test_run_kind_promotions.py::test_promotions_in_summary_page_as_action`,
  `tests/notify/test_run_kind_promotions.py::test_summary_without_promotion_keys_stays_clean`.
  Fixed by seeding a trivially-healthy (empty-shape) companion artifact in each
  — `{"board_pe_freshness": {"state": "FRESH"}, "funds": {}}` for
  `eval_trace.json`, `{}` for `fund_flow_series.json` and `gold_regime.json` —
  so each test's health digest has zero warnings and its original
  severity assertion (which exists to cover the `monitor.json` sentinel /
  promotion-field wiring, not health gathering) holds on its own terms. No
  production-code change; confirmed via `uv run pytest tests/notify/ -q`
  (91 passed) after the fix.
- `_build_monitor_health`, `_build_weekly_health`, `_build_flow_capture_health`,
  `_recent_rotation_statuses`, `_flow_capture_coverage`, `_recovery_notice`,
  `_read_json`, and the three `_build_outcome` edits implemented verbatim from
  the brief (no logic changes). `src/irc/commands/notify_cmd.py` grew from 199
  to 325 lines (over the 200-line "ideal" budget in CLAUDE.md) — all growth is
  the brief's own locked code (six new edge functions + three call-site
  wirings); no further split was in scope for this task. `ruff check
  src/irc/commands/notify_cmd.py` passes clean; `uv run pytest
  tests/commands/test_notify_cmd.py -q` — 35 passed (26 pre-existing + 9 new);
  `uv run pytest tests/notify/ -q` — 91 passed (back-compat sweep, post-fix).

## Task 10: `run-flow-capture.sh` notify tail + comment updates

- **Conservative, brief-internal contradiction.** The brief's Step 4 header
  block text literally includes the substring `` `notify-status --run-kind
  flow-capture` `` inside the *header comment* at the top of the file (before
  the weekend/holiday gates and the rotation step). The brief's Step 1 test
  file uses `text.index("notify-status")` (first occurrence in the whole
  file) to assert the notify tail sits after the trading-day gates
  (`test_flow_capture_notify_after_trading_day_gates`) and after the rotation
  step (`test_flow_capture_notify_after_rotation_step`) — with the header text
  verbatim, the *first* `"notify-status"` occurrence is in the header, before
  either gate, so both ordering tests failed red-for-the-wrong-reason after
  the implementation step. Resolved by rewording the header comment to convey
  the same meaning without the literal token: "as `failed` via the
  flow-capture notify tail below (data-health-notify)" instead of "as `failed`
  via `notify-status --run-kind flow-capture` (data-health-notify)". No other
  wording, mechanics, or locked decisions changed — the actual notify-tail
  invocation (Step 3) is byte-identical to the brief, sits after both gates,
  passes `--last-exit-code "$rc"` (not `$radar_rc`), hardcodes
  `--no-notify-on-clean`, and remains best-effort (`|| echo` breadcrumb, never
  changes `$rc`). Watchdog comment (Step 4, second block) implemented
  verbatim — it does not contain the literal string `notify-status` so no
  analogous issue there.
- `bash -n ops/launchd/run-flow-capture.sh` passes; `uv run pytest
  tests/ops/test_launchd_flow_capture.py -q` — 7 passed; pre-existing
  `bash tests/ops/test_flow_capture_wrapper.sh` (AC10 wrapper chaining) still
  passes unaffected (radar-chain assertions sit before the new notify tail).

## Task 12: Docs, CHANGELOG, TODOS, CONTEXT verify + full affected-test sweep

- **Extra TODOS bullets (per orchestrator instruction, beyond brief's Step 6).**
  Added two additional `## Reliability` deferrals alongside the brief's two:
  `notify flow-capture streak vs crash-gap days` (Task-8 review) and
  `flow-capture wrapper dynamic tests` (Task-10 review). Per orchestrator
  instruction, also appended a one-line amendment note at the end of Task 12's
  section in `items/001-plan.md` documenting that these two came from
  Task-8/Task-10 reviews and were not in the original Step 6 spec text.
- **Commit scope wider than brief's Step 9 `git add` list (per orchestrator
  instruction).** In addition to the brief's six doc files, the commit also
  includes `docs/2026-07-07-data-health-notify/items/001-plan.md` (the Task 12
  amendment note above) and the untracked `items/001-runtime-proofs.md` (Task 11
  evidence copy, a genuine straggler — `git status` showed it untracked at Task
  12 start). `items/001-notes.md` (this file) was already committed pre-existing
  with no pending changes, so it is committed here only insofar as this Task 12
  section is a new edit to it. `docs/2026-07-07-data-health-notify/PROGRESS.md`
  was excluded from the commit per explicit instruction (orchestrator-owned) even
  though it was modified in the working tree at task start.
- **CONTEXT.md verify (Step 7): PASS.** Both `grep -c` checks returned `1` —
  "Data-health digest" and "the outcome-notification layer is the surface that
  names flow staleness" are both already present (grill session additions).
  No edit made, no BLOCKED condition.
- **Test sweep (Step 8): all green, counts match the brief's expected deltas
  exactly.** `tests/notify/{test_calendar,test_health,test_classify,test_types,
  test_message,test_monitor_run_kind,test_run_kind_promotions}.py` — 91 passed;
  `tests/commands/test_notify_cmd.py` — 37 passed; `tests/ops/{test_launchd_
  flow_capture,test_launchd_monitor,test_launchd_weekly,test_wrappers,
  test_run_lib}.py` — 70 passed; `ruff check` — All checks passed. No
  pre-existing test regressed.
