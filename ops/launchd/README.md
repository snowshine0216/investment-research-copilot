# IRC local scheduler (launchd) — ops runbook

Two user LaunchAgents run the `irc` pipeline unattended and notify on outcome
(macOS notification always; optional Feishu webhook). Architecture: ADR 0016.

| Label | Schedule (machine-local) | Command | Trading-day gate |
|---|---|---|---|
| `com.irc.daily` | Mon–Fri 17:30 | full `irc run` | skips weekends + `config/cn_market_holidays.yaml` |
| `com.irc.weekly-full` | Sat 09:00 | full `irc run` | none (unconditional) |

Both wrappers run the **full** `irc run` (NOT a short `ingest → opportunity →
decision` chain — `irc decision` requires `score`/`allocate`/`plan`/`memo`
artifacts, ADR 0016 §2), capture `$?`, then call `irc notify-status`.

## Install

```bash
bash ops/launchd/install.sh
```

Idempotent: re-running boots out the existing agent first, then bootstraps the
freshly-templated plist. `RunAtLoad=false`, so install never triggers an
immediate run — the first run is at the next scheduled fire.

## Uninstall

```bash
bash ops/launchd/uninstall.sh
```

## Timezone assumption (machine-local)

`StartCalendarInterval` has **no timezone field** — it fires in the machine's
local zone. The 17:30 / Sat-09:00 targets assume the machine is on **UTC+8**
(China), so 17:30 ≈ post-NAV. The pipeline's internal date resolution always
uses UTC+8 (`_china_today`) regardless. **If your machine is NOT on UTC+8,**
edit `Hour`/`Minute` in `com.irc.daily.plist` / `com.irc.weekly-full.plist`
before installing.

> **WARNING — non-CN timezone machines:** the plists fire at *local* 17:30
> Mon–Fri / Sat 09:00, but the daily wrapper's trading-day gate evaluates the
> date in `TZ='Asia/Shanghai'`. On a machine whose local timezone is not UTC+8
> these two clocks disagree: e.g. on PDT (UTC−7) local Friday 17:30 is
> Saturday CN time, so the job fires but the trading-day gate silently exits 0.
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

## Logs

| File | Content |
|---|---|
| `outputs/_logs/launchd-daily.out.log` / `.err.log` | daily job stdout/stderr |
| `outputs/_logs/launchd-weekly.out.log` / `.err.log` | weekly job stdout/stderr |

Inspect a loaded agent: `launchctl print gui/$(id -u)/com.irc.daily`.

## End-to-end dry run (AC11)

```bash
# Clean run against today's outputs (Feishu unset → macOS only):
unset IRC_FEISHU_WEBHOOK_URL
uv run irc notify-status --run-kind daily --last-exit-code 0

# Forced failure class (fetch-budget exceeded):
uv run irc notify-status --run-kind daily --last-exit-code 3

# Missing today-dir → failed notification:
uv run irc notify-status --run-kind daily --last-exit-code 0 --repo-root /tmp/empty-repo
```

A run against a date with no `outputs/<today>/` at all produces a `failed`
notification ("never produced output") — never a `clean` one.

## Validation

```bash
plutil -lint ops/launchd/*.plist        # both must print OK
for s in ops/launchd/*.sh; do bash -n "$s"; done   # no syntax errors
# shellcheck if on PATH: shellcheck ops/launchd/*.sh
```
