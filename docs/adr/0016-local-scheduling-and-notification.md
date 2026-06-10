# ADR 0016 — Local scheduling + outcome notification (`irc notify-status`, launchd)

**Status:** Accepted (2026-06-10, actionable-ops item 002)
**Builds on:** [ADR 0015 — `portfolio_action` emission contract](0015-portfolio-action-emission-contract.md) (the `null`-counts addendum this notifier consumes).
**Spec:** `docs/2026-06-10-actionable-ops/items/002-spec.md`

## Context

The `irc` pipeline is fully headless with distinguishable exit codes (0 ok / 1 runtime
/ 2 config / 3 fetch-budget / 4 lock / 5 spend-gate) and machine-readable artifacts
(`decision_report.json`, `PIPELINE_HALTED.md`, `STALE_INGEST.md`), but nothing runs it
on a cadence or tells the operator when there is something to do. Item 002 adds
unattended scheduling on the user's macOS machine plus an outcome notifier. Several
choices here are hard to reverse, surprising without context, and the product of real
trade-offs, so they are recorded.

## Decision

### 1. launchd user LaunchAgents, not cron

Scheduling is via `~/Library/LaunchAgents` plists (checked into `ops/launchd/`,
installed by `install.sh`). `StartCalendarInterval` catches up missed fires across
sleep/wake; cron is deprecated on macOS and silently drops fires while the machine
sleeps. Two plists/wrappers (daily, weekly), not one parameterized job — the cadences
differ in command chain and trading-day gating, and two single-purpose units match the
size budget. `RunAtLoad=false` (install must not trigger an immediate run);
`StandardOut/ErrorPath` to a per-job log so a `failed` notification has a postmortem
trail; install is idempotent (bootout-then-bootstrap, re-install safe).

### 2. The daily cadence runs the **full** `irc run`, not a short chain

The MASTER-SPEC sketch said daily = `ingest → opportunity → decision`. That is wrong:
`irc decision` requires `scoring.json` / `proposed_allocation.yaml` / `trade_plan.yaml`
/ `memo_traceability.json`, written by the `score` / `allocate` / `plan` / `memo`
stages the short chain skips — so a fresh weekday `outputs/<today>/` would be missing
them and `irc decision` would exit 2 (config error) every day. `irc run` already ends
in `… → opportunity → memo → decision` (`STAGE_NAMES`). The daily/weekly distinction is
therefore **schedule + trading-day gating**, not a different command chain: both
wrappers run the full pipeline; daily skips weekends/holidays before spending budget,
weekly (Saturday) is unconditional.

### 3. Exit code travels via the wrapper; the classifier is a pure function

Exit codes 1–5 are only observable in the invoking process (a runtime exit-1 may leave
no sidecar). The launchd wrapper captures `$?` and threads it into `irc notify-status
--last-exit-code`, which combines it with today's on-disk artifacts into a frozen
`RunOutcome` and calls the pure `classify_run_outcome(outcome) -> NotificationDecision`.
The classifier reads no file, clock, or env — every input arrives on `RunOutcome` —
so it is exhaustively table-testable without mocks. The `osascript` and Feishu-POST
calls are the only effects, at the command edge.

### 4. `null` sell-side counts are an **action**, never silenced

Per the ADR 0015 addendum, `trim/exit/review_count == null` means signals were never
derived (stale artifact) — operationally a reason to act (re-run `irc opportunity`
before trading), not a healthy zero. The classifier maps any `null` to `severity=action`
with a distinct "sell-side state UNKNOWN" body, never folding it into the silent `clean`
path. This is the contract the addendum locked the notifier to.

### 5. Missing `outputs/<today>/` is `failed`, not `clean`; today is UTC+8

If `outputs/<china-today>/` does not exist, the run never started (the wrapper crashed
before `irc`) — the notifier classifies `failed`, so silence still only ever means "the
schedule itself broke." It resolves *today* with the pipeline's own `_china_today()`
(UTC+8) and deliberately does **not** reuse `irc decision`'s `_resolve_output_dir`
latest-dir fallback, which would make a stale prior run masquerade as today's outcome.
A `clean` run otherwise emits a quiet macOS notification by default
(`--no-notify-on-clean` / `IRC_NOTIFY_ON_CLEAN=0` suppresses) so that a *missing*
notification is unambiguously a broken schedule.

### 6. Trading-day awareness: weekend + optional static holiday YAML

`should_skip_daily(today, holidays)` is pure (weekend or `today ∈ holidays`). Holidays
come from a user-maintained `config/cn_market_holidays.yaml` (absent ⇒ weekend-only
skip). A live AkShare exchange-calendar fetch is rejected for a *scheduling* gate that
must be cheap and reliable — running on a CN holiday merely yields a slightly stale
report that `STALE_INGEST.md` already flags. Auto-syncing the official calendar is a
future item.

## Consequences

- `irc notify-status` makes no paid calls and never invokes `preflight_gate` — it
  cannot exit 5. (The spend gate is opt-in per command, so opting out is simply not
  calling it; no new exemption mechanism.)
- `IRC_FEISHU_WEBHOOK_URL` is optional and read by env-var name only, never a CLI arg
  (global CLAUDE.md webhook rule); `Settings` already uses `extra="ignore"`, so adding
  it does not break `irc init` / `config validate` without secrets.
- launchd `StartCalendarInterval` fires in the machine's **local** timezone; the 17:30 /
  Saturday targets are documented as machine-local wall-clock for the operator's own
  zone, while date resolution inside the pipeline stays UTC+8. A non-UTC+8 operator
  adjusts the plist `Hour`/`Minute` per the ops README.
- The wrapper chain is fail-fast (`set -euo pipefail`, `&&`): one pipeline failure ⇒
  one `notify-status` call ⇒ one notification, never three.
- No pipeline exit code or artifact contract changes — item 002 only consumes them.
