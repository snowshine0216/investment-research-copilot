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
