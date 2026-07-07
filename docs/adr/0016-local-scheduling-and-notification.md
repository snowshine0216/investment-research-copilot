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
- **Wrapper robustness (2026-06-30):** the surviving launchd wrappers regained a
  portable wall-clock watchdog (process-group kill → `rc=124`) and per-wrapper
  single-instance locks via the shared `ops/launchd/lib-run.sh`. Design + rationale:
  `docs/2026-06-30-launchd-watchdog/items/001-spec.md` (no standalone ADR — reversible).

## Amendment (2026-07-07): data-health digest, `degraded` severity, `flow-capture` run-kind

Spec: `docs/2026-07-07-data-health-notify/items/001-spec.md` (grilled + locked).

- **New `degraded` severity.** Precedence becomes `failed > halted > stale >
  degraded > action > clean`, and `degraded ∈ _ALWAYS_NOTIFY` — it fires even
  with `IRC_NOTIFY_ON_CLEAN=0` (without that, a clean-run-with-DARK day would be
  silenced, recreating the invisibility this amendment fixes). A clean-or-actionable
  run whose on-disk artifacts show data degradation (board-PE DARK, flow
  staleness, rotation abstain/`degraded_*`, stale macro drivers) is tagged
  `degraded`; the action rollup, when present, stays in the body. `degraded` sits
  above `action` because a trust problem should tag the notification before the
  action it taints. The name matches rotation's `degraded_*` `data_status` family
  (`data_stale` was rejected — it collides with the `stale` severity).
- **Data-health digest (`src/irc/notify/health.py`).** A pure, UNPERSISTED
  derivation of already-written artifacts (`eval_trace.json`,
  `fund_flow_series.json`, `rotation_radar.json`, `gold_regime.json`), gathered
  best-effort at the notify edge and appended to the body. Never an input to
  factor math or any pipeline stage; a missing/corrupt input degrades to a single
  `health_unknown` warn item, never an exception (same degrade-never-crash posture
  as AC8). See CONTEXT.md "Data-health digest".
- **New `flow-capture` run-kind.** The 15:45 `run-flow-capture.sh` wrapper gains a
  best-effort `notify-status --run-kind flow-capture --no-notify-on-clean` tail: a
  fully-ok chain stays silent, degradation/abstain/failure pages `degraded`/
  `failed`, and a one-time recovery notice fires on the abstain→ok transition
  (severity `clean`, forced notify). The tail passes the flow-capture `$rc`; a
  rotation crash is caught via today's `rotation_radar.json` sentinel (written on
  both ok and abstain).
- **Behaviour change:** a capture timeout (`rc=124`) now pages as `failed`,
  superseding the wrapper's prior "a timeout does NOT page" comment — a capture
  timeout means tomorrow's flow is stale, which is exactly what this surfaces.
