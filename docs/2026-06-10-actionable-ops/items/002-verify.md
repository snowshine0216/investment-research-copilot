Verdict: PASS

## Subagent
Sonnet 4.6 (claude-sonnet-4-6)

## Source
Branch: `claude/actionable-ops-002` — pulled, confirmed up to date with
`origin/claude/actionable-ops-002`.

## Entry points exercised

| Command | Exit | Observed |
|---|---|---|
| `uv run irc notify-status --help` | 0 | All 4 flags present (`--run-kind`, `--last-exit-code`, `--repo-root`, `--notify-on-clean/--no-notify-on-clean`) |
| `uv run irc --help` | 0 | `notify-status` visible in command list |
| `notify-status --run-kind daily --last-exit-code 0` (no IRC_FEISHU_WEBHOOK_URL) | 0 | `severity=failed notify=True` — today's dir (2026-06-10) absent → branch-0 "run never produced output"; osascript notification fired (acceptable side effect) |
| `notify-status --run-kind daily --last-exit-code 3` | 0 | `severity=failed notify=True` — "fetch-budget exceeded" in title |
| `notify-status --run-kind daily --last-exit-code 124` | 0 | `severity=failed notify=True` — "timeout" in title |
| `uv run pytest tests/notify/ tests/commands/test_notify_cmd.py tests/ops/ -q` | 0 | **67 passed** |
| `plutil -lint com.irc.daily.plist` | 0 | OK |
| `plutil -lint com.irc.weekly-full.plist` | 0 | OK |
| `bash -n` on all 4 shell scripts | 0 | All pass |
| `uv run ruff check` on all new files | 0 | All checks passed |

## install.sh static review

- `sed -e "s#__REPO_ROOT__#...#g" -e "s#__UV_BIN__#...#g"` templates both
  wrappers and both plists before copying to `~/Library/LaunchAgents`.
- `launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true` then
  `launchctl bootstrap "gui/$UID_NUM" "$dest"` — idempotent bootout+bootstrap
  sequence correct.
- `+0800` TZ offset check with `WARNING` emitted when machine offset differs —
  present at lines 57–66.
- `shellcheck` not on PATH — noted, skipped per AC10.

## Observed behavior per AC

**AC1 — `classify_run_outcome` pure, exhaustively table-tested.**
`tests/notify/test_classify.py` covers: exit codes 1–5 (parametrized), 124
(timeout), today_dir_exists=False, pipeline_halted, stale_ingest, null
sell-side counts, single-null among sells, buys-only, sells-only, buys+sells
rollup, all-zero clean, clean+notify_on_clean True/False, precedence
(failed beats halted+action, halted beats stale+action). No filesystem, clock,
or env access inside `classify_run_outcome`. **PASS**

**AC2 — `null` ≠ 0 enforced.**
`test_null_sell_counts_are_action_unknown` asserts severity=`action`, "unknown"
in body, "irc opportunity" in body, and that the body does not contain "0" or
"healthy". `test_all_zero_is_clean` confirms zeroes → `clean`. `test_build_outcome_missing_sell_keys_default_to_none` verifies absent JSON keys default to `None`, not 0. **PASS**

**AC3 — Actionable rollup on buys OR sell-side signals.**
`test_buys_only_is_action`, `test_sell_signals_only_is_action`,
`test_buys_and_sell_signals_rollup`, `test_all_zero_is_clean` cover all
branches. `_rollup_body` confirmed to join non-zero parts with ` · `. **PASS**

**AC4 — `should_skip_daily` pure predicate.**
`tests/notify/test_calendar.py`: weekday+empty-set→False, Saturday→True,
Sunday→True, weekday-in-holidays→True, empty-holidays→False.
`calendar.py` has 14 lines, no I/O. **PASS**

**AC5 — `irc notify-status` registered subcommand with all required options.**
`--help` exit 0; flags `--run-kind`, `--last-exit-code`, `--repo-root`,
`--notify-on-clean/--no-notify-on-clean` all listed. `irc --help` exit 0.
`test_notify_status_help_lists_options` asserts all four options. **PASS**

**AC6 — macOS notification always fires when `should_notify`.**
`format_macos` pure formatter tested in `test_message.py` for correct
title/body, double-quote escaping, and newline stripping. The `osascript` edge
(`_send_macos`) exercised in the live end-to-end runs above (notifications
observed firing for each `--last-exit-code` variant). **PASS**

**AC7 — Feishu env-gated and secret-safe.**
`test_dispatch_feishu_skipped_when_env_unset` asserts no POST when
`IRC_FEISHU_WEBHOOK_URL` unset. `test_feishu_post_does_not_log_full_url`
(via `respx`) verifies "SECRET-TOKEN-1234" absent from all log records across
all loggers. `httpx` INFO logger silenced at module level in `notify_cmd.py`
(line 30) to prevent request-URL leakage. URL never a CLI arg — confirmed by
reading `notify_cmd.py`: env read only via `os.environ.get(_FEISHU_ENV)`. **PASS**

**AC8 — Transport failure never masks run result.**
`test_dispatch_continues_when_macos_fails` stubs osascript to raise; asserts
Feishu still attempted AND rc≠0. `test_dispatch_skips_everything_when_should_not_notify`
confirms no channel called when `should_notify=False`. `_dispatch` confirmed to
catch `Exception` on each channel independently and return 1 without raising.
**PASS**

**AC9 — launchd plists valid and lint-clean.**
`plutil -lint` passes for both. `com.irc.daily.plist`: `StartCalendarInterval`
array of 5 weekday entries (Mon=1…Fri=5) at Hour=17 Minute=30;
`RunAtLoad=false`; `StandardOutPath`/`StandardErrorPath` to
`outputs/_logs/launchd-daily.{out,err}.log`; Label=`com.irc.daily`. Weekend
skip delegated to `run-daily.sh` trading-day gate (documented approach per spec
Resolved Q6). `com.irc.weekly-full.plist`: Weekday=6 Hour=9 Minute=0;
`RunAtLoad=false`; log paths set; Label=`com.irc.weekly-full`. **PASS**

**AC10 — install/uninstall idempotent, shellcheck (if available), set -euo pipefail.**
All 4 scripts have `set -euo pipefail`. `bash -n` passes all 4.
`install.sh`: `bootout||true` + `bootstrap` sequence, sed templating of
`__REPO_ROOT__`/`__UV_BIN__`, `command -v uv` guard with `exit 1`. 
`uninstall.sh`: `bootout||true` + `rm -f`. `shellcheck` not on PATH — noted.
`test_all_shell_scripts_pass_bash_syntax_check` and
`test_install_sh_aborts_if_uv_absent` pass in suite. **PASS** (shellcheck
skipped/unavailable — per AC10 language "skipped with a note")

**AC11 — End-to-end dry run.**
`--last-exit-code 0` with no today-dir: severity=`failed`, exit 0 — correctly
identifies missing outputs dir as "run never produced output" (branch 0 fires
before exit-code check, as specified in Resolved Q3). `--last-exit-code 3`:
severity=`failed`, title names "fetch-budget exceeded". `--last-exit-code 124`:
severity=`failed`, title names "timeout". No Feishu POST (env unset — no
network call). **PASS**

**AC12 — Lint + size budget.**
`ruff check` passes on all new files (exit 0). File sizes: `classify.py` 99 L,
`message.py` 30 L, `calendar.py` 14 L, `types.py` 46 L, `notify_cmd.py` 165 L
— all under 200 lines. Functions scanned: longest is `_decide` (~40 lines) and
`_build_outcome` (~30 lines) — above the 20-line ideal but within spec's "ideal"
qualifier; all other functions are well under 20 lines. VERSION unchanged at
0.9.3; CHANGELOG has `[Unreleased]` section with item 002 description. **PASS**

## Failures

None. All 12 ACs verified. 67/67 tests pass.
