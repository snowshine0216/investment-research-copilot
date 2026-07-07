# IRC local scheduler (launchd) — ops runbook

Four user LaunchAgents run the `irc` pipelines unattended and notify on
outcome (macOS notification always; optional Feishu webhook). Architecture: ADR 0016.

| Label | Schedule (Asia/Shanghai) | Command | Gate |
|---|---|---|---|
| `com.irc.monitor` | Daily 12:15 | `irc monitor` | skips weekends + `config/cn_market_holidays.yaml`; once-per-day skip if `monitor.json` already exists |
| `com.irc.flow-capture` | Daily 15:45 (after the 15:00 close) | `irc monitor flow-capture` → `irc rotation` (sector rotation radar, ADR 0023, chained after capture) | skips weekends + CN holidays; single-instance lock `.flow-capture.lock`; best-effort — notifies only on degradation/abstain/failure via `notify-status --run-kind flow-capture --no-notify-on-clean` (silent when fully ok) + a one-time abstain→ok recovery notice; the rotation step is advisory-only (failure logged, never changes the wrapper rc, but a rotation `abstain`/crash IS surfaced by the notify tail) |
| `com.irc.fundamentals-quarterly` | 1st of Jan / Apr / Jul / Oct 08:00 | `irc monitor snapshot` | none (unconditional) |
| `com.irc.weekly` | Saturday 09:00 | `irc run` (full pipeline) → `irc notify-status --run-kind weekly` | once-per-day skip if `decision_report.json` exists; lock `.weekly.lock`; pages on failure/halt/action (incl. **promotions** — funds newly reaching core_dca/accelerate_dca) |

**Previous labels removed:** `com.irc.daily` (Mon–Fri 17:30/20:00/22:30) and
`com.irc.weekly-full` (Sat 09:00) are no longer present. If you have an older
install, run `bash ops/launchd/uninstall.sh` to remove them before installing the
new agents.

**`com.irc.monitor`** captures `$?`, then calls `irc notify-status --run-kind monitor`.
Success detection looks for `outputs/<date>/monitor/monitor.json` — the **last** of
the five atomic writes in `_write_outputs` (`report.html` → `signal.json` →
`impacts.json` → `narrative.json` → `monitor.json`), so it is the only artifact that
proves the **whole** output set was written. It is also the basis of the once-per-day
idempotency skip. Keying on `report.html` (the *first* write) would mis-classify a
partial set — left by a crash after `report.html` but before `monitor.json` — as a
completed run: the notifier would page "success" and the wrapper would skip the day
(now a full 24h wait under the single daily fire). A failed fire leaves no
`monitor.json`, so the next fire re-runs the full job. The wrapper guard and the
notifier sentinel are deliberately kept identical — change one, change the other.
**Per-wrapper single-instance locks** stop a manual run and the scheduled fire (or
any two fires of the same job) from overlapping — chiefly to avoid duplicate paid
LLM spend and wasted concurrent work. `run-monitor.sh` holds
`outputs/_logs/.monitor.lock`; `run-fundamentals.sh` holds
`outputs/_logs/.snapshot.lock`. They are **separate on purpose**: one shared lock
would let an overrunning quarterly snapshot false-skip an entire day's monitor
brief. Each lock is an atomic `mkdir` with stale-holder reclaim and is released by
an `EXIT` trap; contention is a **silent skip** (`exit 0`, no notification — a
skip is not a failure). The lock and the `monitor.json` completion sentinel are
orthogonal: the lock is *concurrency* control, the sentinel is *completion*
detection, and both are retained.
**No same-day retry:** unlike the previous 09:00 + 13:00 pair (where the 13:00 fire
re-ran a failed morning), a single daily fire means a failed 12:15 run leaves **no
brief until the next day's 12:15** — the failure is surfaced immediately via
`notify-status` (any non-zero exit pages), so it is loud, not silent, but same-day
recovery is manual (re-run `irc monitor` by hand). A deliberate trade of redundancy
for one clean daily fire.

**`com.irc.fundamentals-quarterly`** calls `irc monitor snapshot`, which constructs
typed per-fund snapshot targets from each fund's `analysis_profile` in `config/monitor.yaml`
and runs the constituent cache refresh. The daily 12:15 monitor brief reads these caches;
if the quarterly job lapses, affected factors degrade to N/A (surfaced, not silent).

## Watchdog (wall-clock timeout) + notify asymmetry

Each wrapper bounds its run with a wall-clock watchdog (shared
`ops/launchd/lib-run.sh`). The watchdog targets a **non-LLM, non-`cached_fetch`
network call with no timeout** (e.g. an AkShare `requests` call whose default
timeout is `None` can hang a half-open socket forever); LLM calls and
`cached_fetch` are already self-bounded, so the ceilings are generous, not tight.
On overrun the watchdog kills the **whole process group** (`TERM` → 5s grace →
`KILL`) — `uv run` spawns a Python child, so a single-PID kill would orphan the
worker — and reports `rc=124`.

| Wrapper | Timeout env (default) | On timeout |
|---|---|---|
| `run-monitor.sh` | `IRC_MONITOR_TIMEOUT` (1800s / 30 min) | `rc=124` → `notify-status` pages **"timeout"** (`classify` maps 124) |
| `run-flow-capture.sh` | `IRC_FLOW_CAPTURE_TIMEOUT` (300s / 5 min) | `rc=124` → `notify-status --run-kind flow-capture` pages **"failed"** (a capture timeout ⇒ tomorrow's flow is stale — data-health-notify) |
| `run-flow-capture.sh` — rotation step | `IRC_ROTATION_TIMEOUT` (300s / 5 min) | rc logged, does NOT page directly (advisory; wrapper rc unchanged) — but a kill/crash that leaves today's `rotation_radar.json` unwritten pages **failed** via the flow-capture notify tail's sentinel check |
| `run-fundamentals.sh` | `IRC_SNAPSHOT_TIMEOUT` (3600s / 60 min) | `rc=124` **logged loudly, does NOT page** (protective-only) |
| `run-weekly.sh` | `IRC_WEEKLY_TIMEOUT` (7200s / 2h) | `rc=124` → `notify-status --run-kind weekly` pages **"timeout"** |
| `run-weekly.sh` — eval-refresh step | `IRC_WEEKLY_EVAL_TIMEOUT` (900s per suite) | `rc=124` **logged, does NOT page** (best-effort; runs after notify; wrapper rc unchanged) |

**`com.irc.weekly`** restores the weekly full-pipeline schedule removed with the
legacy `com.irc.weekly-full` (2026-06-15). Completion sentinel is
`outputs/<date>/decision_report.json` (the LAST stage's output — the only
artifact proving the whole chain completed); `run --resume` remains the manual
same-day recovery after a halt. The wrapper does not force `RESEARCH_ENABLED` —
set it in `.env` for research-backed weekly runs. Its per-run logs are
`outputs/_logs/run-weekly.<ts>.log`.

After notify, the wrapper best-effort refreshes the two live LLM eval suites
(`env IRC_RUN_LIVE_LLM_EVAL=1 "$UV_BIN" run irc eval monitor_impact` /
`monitor_narrative`) under per-run `IRC_WEEKLY_EVAL_TIMEOUT` watchdogs —
failures/timeouts are logged, never paged, and never alter the wrapper's exit
code (OD-3, report v4 item 001; the `env` prefix is required because
`run_with_watchdog` execs its argv — a bare `VAR=1` word would be run as a
command name).

**Why the asymmetry.** The monitor job has a single `monitor.json` completion
sentinel, so a timeout is a clean pageable outcome. The snapshot job has **no
single completion-sentinel artifact** (it refreshes constituent caches under
`data/…`), so there is nothing for a notification run-kind to test for success; a
snapshot timeout is logged in `outputs/_logs/run-fundamentals.<ts>.log` and is
already surfaced indirectly — the next daily monitor brief degrades the affected
factors to N/A within ~a day. The watchdog there is purely protective: kill the
stuck constituent socket and free the `.snapshot.lock`.

`notify-status` is best-effort: a failure of the notifier itself does **not** page
(it can't — the notifier is the thing that broke) and does **not** change the
wrapper's exit code, but it is logged as a breadcrumb (`notify-status failed …`) in
`outputs/_logs/run-monitor.<ts>.log` so a missing page can be traced.

## Install

> **Before installing:** set `MINIMAX_MODEL` in `.env` to a **fast, non-reasoning
> chat model** (e.g. `MiniMax-Text-01`). A reasoning model (`MiniMax-M3`) overruns the
> per-call deadline and the scheduled brief degrades to `NO_CALL` — see the main README
> "Model choice". `install.sh` also boots out the legacy `com.irc.daily` /
> `com.irc.weekly-full` jobs this vertical replaces.

```bash
# 0. (one-time) ensure MINIMAX_MODEL=MiniMax-Text-01 (or another fast model) in .env

# 1. Install launchd agents (idempotent — boots out prior + legacy agents; runs a
#    one-time cold-start `irc monitor snapshot` at the end so day-one briefs aren't half-empty)
bash ops/launchd/install.sh
```

`RunAtLoad=false`, so install never triggers an immediate run — the first monitor
run is at the next 12:15 fire. The cold-start `irc monitor snapshot` (step 1) is
required because the per-profile factor weights (`valuation`, `constituent`) rely
on data that comes only from the snapshot; without it, those factors degrade to N/A
until the first quarterly job fires.

## Uninstall

```bash
bash ops/launchd/uninstall.sh
```

## Timezone assumption (machine-local)

`StartCalendarInterval` has **no timezone field** — it fires in the machine's
local zone. The 12:15 target assumes the machine is on **UTC+8** (China), so it
lands around the CN midday session break. The pipeline's internal date resolution
always uses UTC+8 (`_china_today`) regardless. **If your machine is NOT on UTC+8,**
edit `Hour`/`Minute` in `com.irc.monitor.plist` before installing.

> **WARNING — non-CN timezone machines:** the plist fires at *local* 12:15
> daily, but the monitor wrapper's trading-day gate evaluates the date in
> `TZ='Asia/Shanghai'`. On a machine whose local timezone is not UTC+8 these
> two clocks disagree: local 12:15 may land on a different CN calendar day than
> the gate expects, so a run may skip or shift. Adjust `Hour` accordingly.
> `install.sh` will print a warning when `date +%z` is not `+0800`.
> (Documented in ADR 0016.)

## Holiday calendar

`config/cn_market_holidays.yaml` is a flat user-maintained list of
`YYYY-MM-DD` strings (refresh yearly). **Absent ⇒ weekend-only skip.** The
daily wrapper greps it before spending any paid-API budget.

## Feishu webhook (optional)

Set `IRC_FEISHU_WEBHOOK_URL` in your `.env`. Unset ⇒ macOS-only. The URL is
read from the env var by name only, never passed as a CLI arg, never logged in
full.

## Clean-run notification

By default, a clean run (nothing actionable) emits a quiet macOS notification
so that a *missing* notification unambiguously means the schedule itself broke.
To suppress clean-run notifications: set `IRC_NOTIFY_ON_CLEAN=0` in `.env` or
pass `--no-notify-on-clean` to `irc notify-status` manually.

`IRC_NOTIFY_ON_CLEAN` accepted values:
- **truthy** (notify on clean): `1`, `true`, `yes`, `on` (case-insensitive)
- **falsy** (suppress clean notifications): any other non-empty value (e.g. `0`, `false`, `no`, `off`)
- **unset / empty**: defaults to **truthy** (notify on clean)

The `--notify-on-clean` / `--no-notify-on-clean` CLI flag takes precedence
over the env var when passed explicitly.

## Logs (and why launchd writes to `/dev/null`)

The plists set `StandardOutPath`/`StandardErrorPath` to **`/dev/null`**, and each
wrapper writes its **own fresh per-run log** instead:

| File | Content |
|---|---|
| `outputs/_logs/run-monitor.<YYYYMMDD-HHMMSS>.log` | one file per monitor fire (stdout+stderr) |

Each wrapper prunes its own logs older than 14 days.

> **Why not a stable launchd log file?** When launchd owns a persistent
> `StandardOutPath`, the first run's `uv run irc monitor` writes to it and macOS
> tags the file with the protected `com.apple.provenance` xattr. On the **next**
> spawn launchd (a different responsible-app context) is **denied reopening** that
> tagged file, so the job dies with **`EX_CONFIG` (78) before bash even runs** —
> zero output, and *no scheduled fire ever executes again* after the first. The
> xattr cannot be stripped (`xattr -d` is a silent no-op on it). Pointing launchd
> at `/dev/null` (never tagged, never fails to open) and having the wrapper create
> a brand-new file each run avoids the reopen entirely. Symptom to recognise:
> `launchctl print gui/$(id -u)/com.irc.monitor` shows `last exit code = 78:
> EX_CONFIG` with `runs` incrementing but the log files untouched.

Inspect a loaded agent: `launchctl print gui/$(id -u)/com.irc.monitor`
(look for `last exit code` and the armed `StartCalendarInterval` triggers).

## End-to-end dry run (AC11)

```bash
# Clean run against today's outputs (Feishu unset → macOS only):
unset IRC_FEISHU_WEBHOOK_URL
uv run irc notify-status --run-kind monitor --last-exit-code 0

# Forced failure class (fetch-budget exceeded):
uv run irc notify-status --run-kind monitor --last-exit-code 3

# Missing today-dir → failed notification:
uv run irc notify-status --run-kind monitor --last-exit-code 0 --repo-root /tmp/empty-repo
```

A run against a date with no `outputs/<today>/` at all produces a `failed`
notification ("never produced output") — never a `clean` one.

## Validation

```bash
plutil -lint ops/launchd/*.plist        # all plists must print OK
for s in ops/launchd/*.sh; do bash -n "$s"; done   # no syntax errors
# shellcheck if on PATH: shellcheck ops/launchd/*.sh
```
