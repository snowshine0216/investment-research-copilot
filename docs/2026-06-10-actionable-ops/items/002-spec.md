# Item 002 — Local scheduler + notifier

Run: `actionable-ops` (backlog). Branch: `autodev/actionable-ops-feature`.
Status: spec. MASTER-SPEC row 002 ("IN").
Consumes: ADR 0015 (`portfolio_action` emission contract) — `decision_report.json`
`summary.{actionable_buy_count, trim_count, exit_count, review_count}`, where the
three sell-side counts are **`null` (not 0)** when the opportunity artifact is
pre-001/stale.

## Goal

Make the headless `irc` pipeline run **unattended on a cadence** on the user's
macOS machine and **notify** them only when there is something to do or something
went wrong, so they can investing-react by opening the report instead of
remembering to run a command. Two scheduled routines are installed via launchd
user LaunchAgents: a **daily-light** run (`irc ingest → irc opportunity → irc
decision`) on CN trading days at ~17:30 China time (after NAV publication), and a
**weekly-full** run (`irc run`) on Saturday morning. After each run a thin notifier
classifies the outcome from the process **exit code** (0 ok / 1 runtime / 2 config
/ 3 fetch-budget / 4 lock / 5 spend-gate) plus the machine-readable artifacts
(`decision_report.json`, `PIPELINE_HALTED.md`, `STALE_INGEST.md`) and emits a
**macOS user notification (always)** plus an **optional Feishu webhook
(env-gated)** when (a) there is an operation to do — actionable buys, trim / exit /
review signals, or **unknown** (`null`) sell-side state; (b) the pipeline halted or
data went stale; or (c) the run failed. A clean run with nothing actionable emits a
quiet (or suppressed) notification so silence means "nothing to do," not "the
schedule broke." The outcome-classification logic is a **pure, unit-tested
function**; only the `osascript` / webhook / file-read calls are effects at the
command edge.

## Approach (chosen)

**`irc notify-status` CLI subcommand wrapping a pure classifier, driven by thin
launchd wrapper scripts** (see Open Questions OQ1, OQ2).

- The launchd LaunchAgent runs a checked-in **wrapper script** (`ops/launchd/run-daily-light.sh`
  / `run-weekly-full.sh`) that: `cd`s to the repo, runs the pipeline commands,
  **captures the exit code**, then calls `irc notify-status --run-kind {daily|weekly}
  --last-exit-code "$rc"`. The wrapper is thin shell (effects only); it carries no
  classification logic.
- `irc notify-status` (new `@main.command`, `src/irc/commands/notify_cmd.py`) reads
  today's `outputs/<YYYY-MM-DD>/` artifacts, builds a `RunOutcome` value, calls the
  **pure** `classify_run_outcome(...) -> NotificationDecision`, then dispatches the
  decision to the macOS notifier and (if `IRC_FEISHU_WEBHOOK_URL` is set) the Feishu
  notifier. It exits 0 on successful dispatch; a notifier transport failure is
  logged and exits non-zero but never raises (a broken webhook must not mask the
  underlying run result).

Rationale for a subcommand over a standalone script: the classify-outcome →
notification-decision step is **pure logic** and the project mandates TDD with
`tests/` mirroring `src/irc/` one-for-one. A subcommand lets the classifier live in
`src/irc/notify/` and be unit-tested without mocks; the artifact-reading helpers
the command needs already exist in the package. A standalone Python/bash script
would either duplicate that reading logic or be untestable to the same standard.

Vertical slice this item delivers:
`launchd plists → wrapper scripts (capture exit code) → irc notify-status → pure
classify_run_outcome → macOS notification + optional Feishu`.

### Components (each single-purpose, files < 200 lines)

```
ops/launchd/
  com.irc.daily-light.plist          # StartCalendarInterval 17:30, Mon–Fri; runs wrapper
  com.irc.weekly-full.plist          # StartCalendarInterval Sat morning; runs wrapper
  run-daily-light.sh                 # cd repo; irc ingest && irc opportunity && irc decision; rc=$?; irc notify-status …
  run-weekly-full.sh                 # cd repo; irc run; rc=$?; irc notify-status …
  install.sh                         # template repo path into plists, copy to ~/Library/LaunchAgents, launchctl bootstrap
  uninstall.sh                       # launchctl bootout, remove plists
  README.md                          # install/uninstall/inspect-logs runbook (ops doc, not user manual)

src/irc/notify/
  __init__.py
  types.py                           # frozen RunOutcome, NotificationDecision, Severity, RunKind
  classify.py                        # PURE classify_run_outcome(outcome) -> NotificationDecision; trading-day skip predicate
  message.py                         # PURE format_macos(decision), format_feishu(decision) -> str / dict payload

src/irc/commands/notify_cmd.py       # EDGE: read artifacts → RunOutcome; call classify; dispatch (osascript, webhook)

config/cn_market_holidays.yaml       # OPTIONAL static holiday list the user maintains yearly (absent ⇒ weekend-only skip)
```

### Data flow

```
launchd StartCalendarInterval ─▶ run-{daily,weekly}.sh
                                      │ runs pipeline, captures $rc
                                      ▼
                         irc notify-status --run-kind … --last-exit-code $rc
                                      │  (EDGE: reads today's outputs/)
   decision_report.json summary ─────┤   actionable_buy_count, trim_count,
   PIPELINE_HALTED.md (exists?) ──────┤   exit_count, review_count (int|null)
   STALE_INGEST.md   (exists?) ──────┤
   last-exit-code ───────────────────┘
                                      ▼
                    RunOutcome (frozen) ─▶ classify_run_outcome  (PURE)
                                      ▼
                    NotificationDecision { should_notify, severity, title, body }
                                      │
                  ┌───────────────────┴───────────────────┐
                  ▼                                        ▼
        format_macos → osascript                 format_feishu → POST $IRC_FEISHU_WEBHOOK_URL
        (always, when should_notify)             (only if env var set)
```

### Classification (the pure core)

`classify_run_outcome(outcome: RunOutcome) -> NotificationDecision` decides severity
in this fixed precedence (highest first):

1. `last_exit_code ∈ {1,2,3,4,5}` ⇒ **`failed`** — run did not complete. Title names
   the failure class by exit code (1 runtime / 2 config / 3 fetch-budget / 4 lock /
   5 spend-gate); body points at the artifact (`PIPELINE_HALTED.md` if present).
2. `PIPELINE_HALTED.md` present (even at exit 0 edge cases) ⇒ **`halted`**.
3. `STALE_INGEST.md` present ⇒ **`stale`** — data went stale; report may be built on
   old inputs.
4. Any sell-side count is **`null`** (signals unavailable / pre-001 stale artifact)
   ⇒ **`action`** with an explicit **"sell-side state UNKNOWN — re-run `irc
   opportunity`"** body. **`null` is never treated as 0 and never silently
   suppressed** (ADR 0015 addendum, MUST).
5. `actionable_buy_count > 0` **OR** `(trim_count + exit_count + review_count) > 0`
   ⇒ **`action`** — there is an operation to do; body rolls up the counts
   (e.g. "2 buys · 1 trim · 1 exit").
6. else ⇒ **`clean`** — nothing to do.

`should_notify` is True for `failed | halted | stale | action`; for `clean` it is
governed by `--notify-on-clean / IRC_NOTIFY_ON_CLEAN` (default: a quiet macOS
notification confirming the run completed with nothing actionable, so a missing
notification unambiguously means the schedule itself failed). The classifier never
reads files, the clock, or env — every input arrives on `RunOutcome`; it is fully
deterministic and table-testable.

### Trading-day awareness (pure predicate)

`should_skip_daily(today, holidays) -> bool` returns True on Saturday/Sunday
(deterministic) or when `today` is in the supplied `holidays` set. The wrapper reads
`config/cn_market_holidays.yaml` (a flat list of `YYYY-MM-DD` strings the user
maintains yearly; **absent ⇒ empty set ⇒ weekend-only skip**, documented) and the
CN-local date (UTC+8, reusing the existing `_china_today` pattern), then short-circuits
the daily-light run on a skipped day **before** spending any paid-API budget. The
weekly-full run is unconditional (Saturday is intentional). The skip predicate is
pure; reading the YAML and the clock is the edge.

## Acceptance criteria

Each criterion is independently verifiable by a test, a lint/validation step, or
inspecting committed files.

1. **`classify_run_outcome` is pure and exhaustively table-tested.** Given a
   `RunOutcome`, it returns a `NotificationDecision` obeying the precedence in
   §Classification. Unit tests cover every branch: each non-zero exit code (1–5),
   `PIPELINE_HALTED.md` present, `STALE_INGEST.md` present, a `null` sell-side count,
   a positive buy count, a positive trim/exit/review rollup, and the all-zero clean
   case. No mocks; no filesystem, clock, or env access inside the function.

2. **`null` ≠ 0 is enforced.** A `RunOutcome` with `trim_count = exit_count =
   review_count = None` (pre-001 / stale artifact) classifies as `action` with
   severity reflecting "unknown sell-side state" and a body string that names it as
   **unknown** (not "0" / not "healthy"). A separate test asserts that
   `trim_count = exit_count = review_count = 0` with no buys classifies as `clean`.
   (Locks the ADR 0015 addendum MUST at the notifier boundary.)

3. **The actionable rollup fires on buys OR sell-side signals.** Tests assert
   `action` when only `actionable_buy_count > 0`, when only one of
   trim/exit/review > 0, and when both; and `clean` when all are 0 and no
   halt/stale/failure. The body string contains a human rollup of the non-zero
   counts.

4. **`should_skip_daily(today, holidays)` is a pure predicate.** Returns True for any
   Saturday or Sunday and for any date in `holidays`; False otherwise. Unit-tested on
   a weekday, a weekend, a holiday-set hit, and an empty holiday set. (No network, no
   file read inside the function.)

5. **`irc notify-status` exists as a registered subcommand** with options
   `--run-kind {daily|weekly}`, `--last-exit-code <int>`, `--repo-root`, and a
   clean-suppression flag (`--notify-on-clean/--no-notify-on-clean`, env-overridable
   via `IRC_NOTIFY_ON_CLEAN`). It reads today's `outputs/<date>/` artifacts, builds a
   `RunOutcome`, calls `classify_run_outcome`, and dispatches. `irc notify-status
   --help` lists the options. (CLI smoke test.)

6. **macOS notification always fires when `should_notify`.** The command issues a
   user notification via `osascript -e 'display notification …'` (the I/O edge);
   the title/body come from the pure `format_macos(decision)`. A test asserts the
   formatted title/body for representative decisions (failed / stale / action /
   action-unknown); the `osascript` call itself is the un-unit-tested edge, exercised
   only by the manual end-to-end check (AC11).

7. **Feishu is env-gated and secret-safe.** When `IRC_FEISHU_WEBHOOK_URL` is set, the
   command POSTs the `format_feishu(decision)` JSON payload to that URL; when unset,
   the Feishu leg is skipped and the macOS notification still fires. The webhook URL
   is read **only** from the env var — never accepted as a CLI positional/option
   argument (global CLAUDE.md rule: no webhook URLs as CLI args). A test asserts the
   payload shape from the pure formatter and that an unset env var yields no POST. The
   URL never appears in logs (a test greps the log line for the literal env value and
   asserts absence, or asserts the dispatcher logs only the host, not the path/token).

8. **A notifier transport failure never masks the run result.** If the `osascript`
   or webhook call raises/returns non-zero, `irc notify-status` logs it and exits
   non-zero **without raising**, and the failure of one channel does not prevent the
   other from being attempted. (Test on the dispatcher with both channels stubbed to
   fail.)

9. **launchd plists are valid and lint-clean.** `com.irc.daily-light.plist` and
   `com.irc.weekly-full.plist` pass `plutil -lint`. Daily uses
   `StartCalendarInterval` at 17:30 for weekdays (Mon–Fri via per-weekday entries or
   a documented weekend-skip-in-wrapper); weekly uses a Saturday-morning
   `StartCalendarInterval`. Each plist sets `StandardOutPath` / `StandardErrorPath`
   to a log file under the repo (or `~/Library/Logs`), `RunAtLoad=false`, and a label
   matching its filename. (Validation step: `plutil -lint` on both; documented in the
   ops README.)

10. **Install / uninstall scripts are idempotent and pass shellcheck (if available).**
    `install.sh` templates the absolute repo path into the plists, copies them to
    `~/Library/LaunchAgents`, and `launchctl bootstrap`s them (re-running is safe —
    it bootouts first or no-ops). `uninstall.sh` `launchctl bootout`s and removes the
    plists. All wrapper/install/uninstall scripts pass `shellcheck` when it is on PATH
    (skipped with a note otherwise); all run `set -euo pipefail`. (Validation step.)

11. **End-to-end dry run.** Running `irc notify-status --run-kind daily
    --last-exit-code 0` against the current `outputs/<latest>/` issues a real macOS
    notification (or, if `--no-notify-on-clean` and the run is clean, suppresses it),
    exits 0, and performs no network call when `IRC_FEISHU_WEBHOOK_URL` is unset.
    Forcing `--last-exit-code 3` produces a `failed` notification naming the
    fetch-budget class. (Manual check; documented in the ops README; no automated
    network.)

12. **Lint + size budget.** `uv run ruff check src tests` passes on all new files;
    every new source file is < 200 lines and every new function < 20 lines (ideal),
    helpers extracted otherwise. No VERSION bump; changes accumulate under CHANGELOG
    `[Unreleased]`.

## Non-goals

- **A general notification framework / pluggable channels beyond macOS + Feishu.**
  Exactly two channels (macOS always, Feishu optional). Slack / email / SMS / desktop
  toast on other OSes are out of scope (the user's machine is macOS).
- **Cross-platform scheduling.** launchd only; no cron, no systemd, no Windows Task
  Scheduler. (cron is deprecated on macOS and does not handle sleep/wake catch-up;
  launchd's `StartCalendarInterval` does.)
- **A cloud scheduler / CI runner.** No `.github/workflows`, no remote agent. The
  routine runs on the user's local machine against the local repo and `.env`.
- **Changing pipeline exit codes or artifact contracts.** This item *consumes* the
  exit codes (0–5) and the `decision_report.json` / `PIPELINE_HALTED.md` /
  `STALE_INGEST.md` contracts as-is; it does not add or rename any.
- **Computing or re-deriving sell-side counts.** The notifier reads
  `summary.{trim,exit,review}_count` produced by item 001; it never recomputes them
  and never "fills in" a `null` as 0.
- **A bundled, always-current CN holiday calendar / akshare trade-calendar fetch.**
  The holiday YAML is a static, user-maintained file; auto-syncing the official CN
  exchange calendar is a future item (see OQ3). Absent file ⇒ weekend-only skip.
- **Retry / backoff of failed scheduled runs inside the notifier.** The notifier
  reports the failure; launchd's next scheduled fire is the "retry." (A
  failed-run auto-rerun policy is out of scope.)
- **Live-NAV / market-value re-pricing or any change to what the report contains.**
  Item 002 is purely scheduling + notification; the report is item 001's surface.

## Constraints

- **TDD mandatory.** Red → green → refactor for all pure logic
  (`classify_run_outcome`, `should_skip_daily`, `format_macos`, `format_feishu`).
  `tests/` mirrors `src/irc/` one-for-one
  (`src/irc/notify/classify.py` → `tests/notify/test_classify.py`, etc.). Plists and
  shell scripts get **validation steps** instead of unit tests (`plutil -lint`,
  `shellcheck`).
- **Effects at edges.** All I/O — reading `outputs/<date>/` artifacts and
  `config/cn_market_holidays.yaml`, reading the clock, the `osascript` call, the
  Feishu HTTP POST — lives in `notify_cmd.py` and the wrapper scripts. `notify/`
  modules (`classify`, `message`, the skip predicate) are pure, deterministic, and
  testable without mocks. The pure functions receive every input as an argument; they
  never read env, clock, or filesystem.
- **Functional / immutable.** `RunOutcome` and `NotificationDecision` are frozen
  dataclasses; no argument mutation; transforms return new values. No shared mutable
  module state; dependencies passed explicitly through signatures.
- **Secrets in `.env` only (`IRC_FEISHU_WEBHOOK_URL`).** The webhook URL is referenced
  by env-var **name**, never inlined in YAML and never passed as a CLI positional/option
  argument — passing a webhook URL as a CLI arg is explicitly forbidden (bearer-token
  exposure, global CLAUDE.md). The URL must not be logged in full.
- **`null` sell-side counts are surfaced as "unknown," never as 0 or "healthy"**
  (ADR 0015 addendum, MUST). The classifier treats any `null` among
  trim/exit/review_count as an `action`-worthy "signals unavailable — re-run `irc
  opportunity`" condition.
- **launchd, not cron.** Scheduling is via user LaunchAgents in
  `~/Library/LaunchAgents`, installed from plists checked into `ops/launchd/` by an
  install script. `StartCalendarInterval` handles sleep/wake catch-up.
- **File / function size budget.** Files < 200 lines, functions < 20 lines (ideal);
  extract helpers rather than nest > 3 levels.
- **No new heavy dependencies.** The Feishu POST uses the HTTP client already in the
  dependency set (e.g. `httpx`/`requests` as already vendored — confirm at plan time
  and reuse, do not add a new one); YAML parsing reuses the existing loader. macOS
  notification uses `osascript` via `subprocess` (no new dep).
- **No VERSION bump.** Accumulate under CHANGELOG `[Unreleased]` per the project
  versioning convention.
- **Headless / non-interactive.** `irc notify-status` adds **zero** interactive
  prompts; it is invoked by a non-interactive launchd job. All inputs come from
  flags, env, and on-disk artifacts.

## Open questions resolved during brainstorming

*(Autonomy override in effect — no user in loop; each answer is the recommended
resolution with rationale, recorded here.)*

- **OQ1 — `irc notify-status` subcommand vs. standalone script for the notifier?**
  **Resolved: a `irc notify-status` subcommand wrapping a pure classifier.** Rationale:
  the outcome → notification-decision logic is pure and the project mandates TDD with
  `tests/` mirroring `src/irc/`. A subcommand lets the classifier live in
  `src/irc/notify/` and be unit-tested without mocks, reusing the package's
  artifact-reading helpers; a standalone script would either duplicate that logic or
  resist the same test standard. The launchd wrapper stays thin (run pipeline →
  capture `$rc` → call `irc notify-status`).

- **OQ2 — How does the notifier learn the run's exit code?** **Resolved: the launchd
  wrapper captures `$?` after the pipeline and passes it as
  `--last-exit-code`.** Rationale: exit codes 1–5 are only observable in the
  invoking process; they are not all written to an artifact (e.g. exit 1 runtime may
  leave no sidecar). The wrapper is the only place that sees the real code, so it
  threads it into `notify-status`, which combines it with the on-disk artifacts. This
  keeps the classifier pure (the code is just another `RunOutcome` field).

- **OQ3 — CN trading-day awareness: weekend-only, static holiday YAML, or live
  exchange-calendar fetch?** **Resolved: weekend skip (deterministic) + an optional
  static `config/cn_market_holidays.yaml` the user maintains yearly; absent ⇒
  weekend-only skip, documented.** Rationale: weekends are deterministic and cover
  most non-trading days; CN public holidays have no closed-form rule and no bundled
  offline source in-repo. A live AkShare `tool_trade_date_hist_sina` fetch would add
  a network dependency and a failure mode to a *scheduling* gate that must be cheap and
  reliable — and the cost of running the daily-light pipeline on a CN holiday is low
  (it just produces a slightly stale report, and `STALE_INGEST.md` already flags
  staleness). A self-maintained YAML is dependency-free, transparent, and easy to
  update once a year. Auto-syncing the official calendar is recorded as a future
  item, not built here.

- **OQ4 — Should a clean run (nothing actionable) notify at all?** **Resolved: emit a
  quiet macOS notification by default, suppressible via
  `--no-notify-on-clean` / `IRC_NOTIFY_ON_CLEAN=0`.** Rationale: if a clean run is
  silent, the user cannot distinguish "nothing to do" from "the schedule broke and
  nothing ran." A quiet confirmation makes silence diagnostic. Power users who find
  it noisy can suppress it; the default favors trust in the automation.

- **OQ5 — How is a `null` sell-side count notified?** **Resolved: as an `action` with
  an explicit "sell-side state UNKNOWN — re-run `irc opportunity`" message.**
  Rationale: ADR 0015 addendum is a MUST — `null` means signals were never derived
  (stale artifact), which is *operationally* a reason to act (re-run before trading),
  not a healthy zero. Folding it into the silent/clean path would violate the
  contract and hide a real "your sell signals are stale" condition. It is distinct
  from a normal buy/trim/exit `action` (different body text) so the user knows the
  required action is "refresh," not "trade."

- **OQ6 — Two separate plists/wrappers (daily, weekly) or one parameterized job?**
  **Resolved: two plists + two wrapper scripts.** Rationale: launchd
  `StartCalendarInterval` schedules are per-LaunchAgent; the two cadences run
  different command chains (`ingest → opportunity → decision` vs. `run`) and have
  different trading-day gating (daily skips weekends/holidays; weekly is
  unconditional Saturday). Two small, single-purpose plists/wrappers are clearer than
  one branchy parameterized job and match the size-budget / single-purpose
  conventions. The shared notify step is factored into `irc notify-status`, so the
  wrappers stay thin.

- **OQ7 — Where do scheduled-run logs go?** **Resolved: plist `StandardOutPath` /
  `StandardErrorPath` to a per-job log file (under the repo's `outputs/` log area or
  `~/Library/Logs/irc/`), documented in the ops README.** Rationale: launchd jobs are
  non-interactive; without redirected stdio the only trace of a failed run is the
  notification. A persistent log gives the user something to inspect after a `failed`
  alert. The exact path is finalized at plan time; it must not contain secrets.

### No unresolved questions

All open questions were resolvable from MASTER-SPEC + ADR 0015 + the README cadence
section + the verified-headless CLI surface. The judgement calls (OQ3 holiday
strategy, OQ4 clean-run notification, OQ5 null handling) are recorded with rationale;
the implementer should treat the `irc notify-status` subcommand, the
exit-code-via-wrapper threading, and the weekend+static-YAML trading-day gate as
canonical.
