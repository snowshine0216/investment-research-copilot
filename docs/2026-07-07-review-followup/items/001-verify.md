Verdict: PASS

Subagent: sonnet

## Source

- Branch confirmed: `claude/review-followup-001` (`git branch --show-current`).
- Spec: `docs/2026-07-07-review-followup/items/001-spec.md` §5 AC1–AC6, §10 constraints.
  Per the plan-locked AC1 reconciliation, the real store has a lagging symbol (688072 @
  2026-06-26) so `degraded` is the correct outcome for AC1, not the spec's illustrative
  "clean".
- Implementation: `src/irc/notify/health.py` (pure builders), `src/irc/notify/classify.py`
  (`degraded` severity + precedence), `src/irc/commands/notify_health.py` (edge reads),
  `src/irc/commands/notify_cmd.py` (`_build_outcome`/`_flow_capture_outcome`/`_dispatch`),
  `ops/launchd/run-flow-capture.sh` (notify tail). Prior evidence
  (`docs/2026-07-07-review-followup/items/001-runtime-proof.md`) was read for context but
  **not reused** — every result below was reproduced independently in this dispatch, and via
  a stricter entry point (see below).

## Entry point exercised

The prior proof (`001-runtime-proof.md`, per `.superpowers/sdd/task-7-brief.md`) called
`_build_outcome` + `classify_run_outcome` directly from a `python -c` snippet — it never went
through the Click CLI or `_dispatch`. This dispatch instead exercises the **real CLI process**,
`uv run irc notify-status --run-kind <kind> --last-exit-code <n> [--no-notify-on-clean]`,
for all four kinds relevant to the ACs (`monitor` ×2, `flow-capture` ×3, `weekly` ×1), through
the full `run_notify_status` → `classify_run_outcome` → `_dispatch` path, including
`_send_macos`.

`--help` confirmed no dry-run flag exists. Read `_dispatch`/`_send_macos`/`_send_feishu`
(`src/irc/commands/notify_cmd.py:177-218`): Feishu is already a safe no-op by default (only
POSTs if `IRC_FEISHU_WEBHOOK_URL` is set, which it never was in this session — confirmed
`env | grep -i FEISHU` empty). macOS has no env gate, so I built a `PATH` shim: a fake
`/…/scratchpad/fakebin/osascript` executable that appends its argv to a capture log and exits
0, placed first on `PATH` for every invocation. This exercises the real subprocess-dispatch
code path (argument construction via `format_macos`) while making the effect harmless — no
real Notification Center banner fired, no Feishu POST ever attempted. `git status --short`
before/after shows no repo mutation (notify-status never writes to disk itself).

## Observed behavior per acceptance criterion

**AC1 — monitor, real 2026-07-07 artifacts.** Ran directly against the real repo root
(`--repo-root .`), no staging:
```
$ PATH="$FAKEBIN:$PATH" uv run irc notify-status --repo-root . --run-kind monitor --last-exit-code 0
[20:53:18] INFO notify-status severity=degraded notify=True
RC=0
osascript CAPTURED ARGS: -e display notification "Run completed; nothing actionable. ·
板块PE: STALE-1 (2026-07-06) · 资金流: 最新 2026-07-07 · 覆盖 29/30 · 1 只滞后>3td(最旧 2026-06-26)"
with title "IRC data degraded"
```
Matches the reconciled AC1: severity `degraded` (per-symbol flow-lag rule fires on real
688072), board-PE `STALE-1` rendered as an info-level line (no separate escalation), flow
line carries the coverage + stale-count substrings verbatim. **PASS.**

**AC4 (extra — not in the explicit step list, verified anyway since it's directly adjacent).**
Built a temp root from the real `eval_trace.json` with `board_pe_freshness` mutated to
`{state: DARK, as_of: 2026-07-01, age_td: 4}` (rest of the real trace + real flow store
copied verbatim), ran with `IRC_NOTIFY_ON_CLEAN=0` set as an actual env var (not a Python
kwarg):
```
severity=degraded notify=True   RC=0
BODY … 板块PE: DARK ≥4td — 价值陷阱检测不可用 …
```
`degraded` fires even under `IRC_NOTIFY_ON_CLEAN=0` because `degraded ∈ _ALWAYS_NOTIFY`.
**PASS.**

**AC2 — flow-capture: abstain / ok-after-ok / ok-after-abstain.**
(a) Ran directly against the real repo root — today's real `rotation_radar.json` is
genuinely `abstain` in production (07-07):
```
severity=degraded notify=True   RC=0
BODY … 轮动雷达: 弃权 (连续第 1 日)
```
(b) ok-after-ok: staged a temp root with the real 07-06 `ok` radar JSON copied into both a
07-06 and a 07-07 dir:
```
severity=clean notify=False   RC=0
(no osascript capture file produced — fully silent, as spec'd)
```
(c) ok-after-abstain: staged a temp root with the real 07-05 `abstain` radar JSON as 07-06,
real 07-06 `ok` radar JSON as 07-07:
```
severity=clean notify=True   RC=0
BODY … 轮动雷达恢复 ok (200 boards) — 此前弃权 1 日
```
All three match spec §3.4/AC2: abstain pages `degraded` with `弃权`; silent-on-ok-after-ok;
one-time forced recovery notice containing `恢复`/`弃权` on the transition. **PASS.**

**AC3 — weekly, real 07-04 gold_regime.json.** Staged a temp root (`outputs/2026-07-07/`)
with a minimal `decision_report.json` and the **real** `outputs/2026-07-04/gold_regime.json`
copied in as today's file (weekly is a Saturday cadence; today 07-07 has no real weekly
output of its own, so this is the closest possible "real artifact" placement):
```
severity=degraded notify=True   RC=0
BODY … 宏观驱动: DXY 滞后 21d (2026-06-16) · 缺失驱动: etf_holdings_gld
```
07-07 minus 06-16 = 21 days, correct. Both the macro-age warn and the `drivers_unavailable`
info line render. **PASS.**

**AC5 — corrupt eval_trace.json.** Staged a temp root: `monitor/eval_trace.json` containing
literal `{bad json` and a valid `monitor.json` sentinel; no flow store present.
```
[20:54:29] WARNING data-health: could not read eval_trace.json
severity=degraded notify=True   RC=0
BODY … health unknown — 健康检查数据缺失/损坏 · health unknown — 资金流数据缺失/损坏 …
```
Only a logged WARNING appeared — no traceback, process exited rc=0 normally (Click's
`raise SystemExit(rc)` with `rc=0` from `_dispatch`). The corrupt-trace and missing-flow-store
paths both degraded independently to their own `health_unknown` items rather than crashing.
**PASS.**

**Static wrapper check — `ops/launchd/run-flow-capture.sh`.** Read the file directly: the
notify tail (`"$UV_BIN" run irc notify-status --run-kind flow-capture --last-exit-code "$rc"
--no-notify-on-clean || echo "…"`) runs after both watchdog-wrapped calls
(`irc monitor flow-capture` then `irc rotation`), after the weekend/holiday `exit 0` gates,
passes the flow-capture `$rc` (not `radar_rc`), and is failure-isolated via `|| echo` (not
`|| true`, not bare) so a notify-status crash cannot abort the script under `set -euo
pipefail` nor change the wrapper's own final `exit "$rc"`. Matches spec §3.4 exactly.

**Regression.** `uv run pytest tests/notify/ tests/commands/test_notify_cmd.py
tests/ops/test_launchd_flow_capture.py tests/ops/test_launchd_monitor.py -q` (per-file/
per-dir, never whole `tests/commands/`) → `167 passed in 34.75s`, no failures/errors/skips.

## Failures

None. AC1, AC2 (all 3 sub-scenarios), AC3, AC4, AC5 all reproduced independently through the
real CLI entry point with dispatch safely captured (never a real Feishu POST, never a real
macOS banner); wrapper wiring confirmed statically; regression suite green. AC6 (doc sync)
was spot-checked by grep (ADR 0016 §7 amendment present; `ops/launchd/README.md`,
`docs/monitor/README.md`, root `README.md` all mention the flow-capture notify tail) but not
exhaustively diffed — outside this dispatch's explicit step list.

## Addendum (2026-07-07, post-verify fix rounds 2-3)

Commits `fb9316da` + `d9a06161` landed after this verdict (pr-review nit + Codex findings). Each carries TDD RED→GREEN + a CLI-level subprocess proof for the new flow-capture coverage path (staged 7/30 store → `degraded · flow-capture: 7/30`, notify True). Orchestrator gate re-run at merge time: test_health.py 25, test_notify_cmd.py 43, test_launchd_flow_capture.py 4 — all green. Verdict unchanged: PASS.
