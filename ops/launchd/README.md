# IRC local scheduler (launchd) — ops runbook

Two user LaunchAgents run the `irc` pipeline unattended and notify on outcome
(macOS notification always; optional Feishu webhook). Architecture: ADR 0016.

| Label | Schedule (Asia/Shanghai) | Command | Gate |
|---|---|---|---|
| `com.irc.monitor` | Mon–Fri 09:00 (primary) + 13:00 (retry) | `irc monitor` | skips weekends + `config/cn_market_holidays.yaml`; retry skips if `report.html` already exists |
| `com.irc.fundamentals-quarterly` | 1st of Jan / Apr / Jul / Oct 06:00 | `irc monitor snapshot` | none (unconditional) |

**Previous labels removed:** `com.irc.daily` (Mon–Fri 17:30/20:00/22:30) and
`com.irc.weekly-full` (Sat 09:00) are no longer present. If you have an older
install, run `bash ops/launchd/uninstall.sh` to remove them before installing the
new agents.

**`com.irc.monitor`** captures `$?`, then calls `irc notify-status --run-kind monitor`.
Success detection looks for `outputs/<date>/monitor/report.html` — that is the atomic
end-of-run artifact; a failed fire leaves none, so the 13:00 retry fires the full job.
A **single-instance lock** (`outputs/_logs/.run.lock`) stops two runs from overlapping.

**`com.irc.fundamentals-quarterly`** calls `irc monitor snapshot`, which constructs
typed per-fund snapshot targets from each fund's `analysis_profile` in `config/monitor.yaml`
and runs the constituent cache refresh. The 09:00/13:00 monitor brief reads these caches;
if the quarterly job lapses, affected factors degrade to N/A (surfaced, not silent).

## Install

```bash
# 1. Cold-start: populate per-fund constituent caches so day-one briefs are not half-empty
uv run irc monitor snapshot

# 2. Install launchd agents (idempotent — boots out any prior agent first)
bash ops/launchd/install.sh
```

`RunAtLoad=false`, so install never triggers an immediate run — the first monitor
run is at the next 09:00 fire. The cold-start `irc monitor snapshot` (step 1) is
required because the per-profile factor weights (`valuation`, `constituent`) rely
on data that comes only from the snapshot; without it, those factors degrade to N/A
until the first quarterly job fires.

## Uninstall

```bash
bash ops/launchd/uninstall.sh
```

## Timezone assumption (machine-local)

`StartCalendarInterval` has **no timezone field** — it fires in the machine's
local zone. The 09:00 target assumes the machine is on **UTC+8** (China), so
09:00 ≈ morning brief after overnight NAV publication. The pipeline's internal
date resolution always uses UTC+8 (`_china_today`) regardless. **If your machine
is NOT on UTC+8,** edit `Hour`/`Minute` in `com.irc.monitor.plist` before
installing.

> **WARNING — non-CN timezone machines:** the plist fires at *local* 09:00
> Mon–Fri, but the monitor wrapper's trading-day gate evaluates the date in
> `TZ='Asia/Shanghai'`. On a machine whose local timezone is not UTC+8 these
> two clocks disagree: e.g. on PDT (UTC−7) local Friday 09:00 is Friday CN
> time but the NAV that arrives at CN evening is not yet available. Adjust `Hour`
> accordingly.
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
