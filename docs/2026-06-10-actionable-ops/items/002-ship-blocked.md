# Ship-blocked findings — item 002 (pre-push review round 1)

P0-1 notify_cmd.py:72-74 — summary.get("trim_count", 0) defaults MISSING keys to 0 → legacy
artifact (keys absent, not null) classifies clean instead of action/unknown. ADR 0015
violation. FIX: default None for all three counts; missing key == null == unknown. Test:
summary without the keys → severity action ("sell-side state unknown").

P0-2 wrappers + plists — `uv` resolved via PATH, but launchd PATH is /usr/bin:/bin:/usr/sbin:/sbin
→ exit 127, notify-status also fails, ZERO notification. FIX: install.sh resolves `command -v uv`
at install time and seds an __UV_BIN__ placeholder in the wrappers (alongside __REPO_ROOT__);
wrappers invoke "$UV_BIN" run ...; README documents the precondition. Re-template on re-install.

P0-3 wrappers — no timeout on `uv run irc run`; a hung pipeline (network stall) = launchd never
ends the job, notify-status never runs, total silence. NOTE: macOS has no GNU `timeout`. FIX:
portable bash watchdog in the wrapper (background pipeline + watcher kills after IRC_RUN_TIMEOUT
seconds, default 7200; on kill, rc=124 so notify-status reports failed/timeout). bash -n must pass.

P0-4 notify_cmd.py:45 _load_holidays — malformed cn_market_holidays.yaml raises uncaught
yaml.YAMLError/ValueError → notify-status itself dies before notifying (meta-silent-failure).
FIX: try/except → log warning, return set() (degrade to never-skip); classification proceeds.
Test: malformed YAML file → no raise, decision still produced.

P1-1 notify_cmd.py:71 — actionable_buy_count coerced to 0 when decision_report.json was
present-but-corrupt (_read_summary returned {} after JSONDecodeError) → buys-only run classifies
clean on truncated artifact. FIX: _read_summary returns None on parse error (distinct from {});
parse-error → severity failed ("decision_report.json unreadable"). Test both paths.

P1-2 run-daily.sh:18 — `grep -q "$TODAY"` matches substrings in comments ("# updated 2026-10-01")
→ spurious silent skip. FIX: anchor to list entries: grep -Eq "^[-[:space:]]*[\"']?${TODAY}[\"']?[[:space:]]*$".

P1-3 message.py:_escape — strip \n and \r (replace with space) for osascript safety (defense-in-depth).

Note (no action): osascript failure logged WARNING with exc_info — acceptable per AC8.
