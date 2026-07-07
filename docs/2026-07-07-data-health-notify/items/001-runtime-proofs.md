# Task 11 Report — Runtime proofs against real artifacts (AC1–AC5)

## Status: DONE — all 5 ACs PASS

## Branch

`claude/data-health-notify-001` (confirmed via `git branch --show-current`)

## Scope

Evidence-capture only — no files changed, no commit (brief Step 6: "No commit (no files
changed)"). Ran the brief's harnesses verbatim from the worktree root against the real
symlinked `outputs/`/`data/` artifacts (07-04..07-07, retained date-partitions) plus two
committed fixture files for the AC4/AC5 sub-cases. The only `irc` command invoked against
the live artifacts was `uv run irc notify-status ...` (read-only + local macOS
notification only — `.env` has no `IRC_FEISHU_WEBHOOK_URL`).

---

## AC1 — monitor, real 07-07 artifacts (board-PE STALE info + flow line)

Command:
```
uv run python - <<'PY'
... (verbatim brief Step 1 harness) ...
PY
```

Observed:
```
AC1 SEVERITY degraded
AC1 BODY Run completed; nothing actionable. · 板块PE: STALE-1 (07-06) · 资金流: 最新 07-07 · 覆盖 29/30 · 1 只滞后>3td(最旧 06-26)
AC1 OK — severity is degraded because the live store has a >3td stale symbol (688072); board-PE STALE-N does not itself escalate (spec-gap #2)
```

Expected: `AC1 SEVERITY degraded`; BODY contains `板块PE: STALE-1 (07-06)` + a `资金流: ... 滞后>3td ...` line; `AC1 OK`.

**Match: exact.** All three assertions in the harness passed (no `AssertionError`); severity
and both required substrings present verbatim.

CLI proof:
```
uv run irc notify-status --run-kind monitor --last-exit-code 0 --repo-root . 2>&1 | grep -E "severity=" || true
```
Observed:
```
[18:18:13] INFO     notify-status severity=degraded            notify_cmd.py:322
                    notify=True
```
Expected: `notify-status severity=degraded notify=True`. **Match** (log line wraps across
two terminal lines; `severity=degraded` and `notify=True` both present). `check=True` on
the `osascript` `subprocess.run` inside `_send_macos` did not raise → the local macOS
notification fired successfully.

**AC1: PASS**

---

## AC4 — board-PE DARK fixture escalates to `degraded` even with `IRC_NOTIFY_ON_CLEAN=0`

Command: verbatim brief Step 2 harness (tmp tree seeded from
`tests/notify/fixtures/health/eval_trace_dark.json` + `fund_flow_series.json`, cleaned up
via `shutil.rmtree(tmp)` inside the harness itself).

Observed:
```
AC4 SEVERITY degraded NOTIFY True
AC4 BODY Run completed; nothing actionable. · 板块PE: DARK ≥4td — 价值陷阱检测不可用 · 资金流: 最新 07-07 · 覆盖 29/30 · 1 只滞后>3td(最旧 06-26)
AC4 OK
```

Expected: `AC4 SEVERITY degraded NOTIFY True`; BODY contains
`板块PE: DARK ≥4td — 价值陷阱检测不可用`; `AC4 OK`.

**Match: exact.** (The flow-line figures match the AC1 real-store numbers because the
`fund_flow_series.json` fixture was committed as a trim of the real 07-07 artifact —
per Task 2's notes — not a coincidence.)

**AC4: PASS**

---

## AC5 — corrupt `eval_trace.json` → `health unknown`, no crash, run rc preserved

Command: verbatim brief Step 3 harness (tmp tree with `eval_trace.json` = `"{bad json"`).

Observed:
```
AC5 BODY Run completed; nothing actionable. · 数据健康未知 (health unknown)
AC5 OK
TMP /var/folders/p8/j82vcmq17xndjwtkfs5hvtg40000gn/T/tmpt5f3u78b
```

Expected: BODY contains `数据健康未知 (health unknown)`. **Match.**

CLI proof against that same tmp tree:
```
uv run irc notify-status --run-kind monitor --last-exit-code 0 --repo-root "$TMP"; echo "exit=$?"
```
Observed:
```
[18:18:33] INFO     notify-status severity=degraded            notify_cmd.py:322
                    notify=True
exit=0
```
Expected: `exit=0` (macOS notification fires; no crash; run rc not masked). **Match** — no
exception, no non-zero exit despite the malformed JSON in `eval_trace.json`; the corrupt
companion artifact degrades to `health_unknown()` rather than propagating a parse error.

Cleanup: `rm -rf "$TMP"` executed; confirmed removed (`ls "$TMP"` → "No such file or
directory").

**AC5: PASS**

---

## AC2 — flow-capture abstain (real 07-05) + recovery string (real 07-06)

Command: verbatim brief Step 4 harness (pins `_china_today` to 07-05 then 07-06 in
sequence, both reads against the real `.` worktree root).

Observed:
```
AC2-A SEVERITY degraded NOTIFY True
AC2-A BODY Run completed; nothing actionable. · 轮动雷达: 弃权 (连续第 1 日) · flow-capture: 0/30
AC2-C recovery_notice 轮动雷达恢复 ok (200 boards) — 此前弃权 1 日
AC2 A+C OK — note: against the LIVE store, pinning a historical date adds a stale flow-capture coverage warn (every symbol has since advanced past that date); the recovery_notice FIELD is still correctly computed. The silent ok-after-ok sub-case is proven by tests/commands/test_notify_cmd.py::test_flow_capture_silent_when_ok_after_ok.
```

Expected: `AC2-A SEVERITY degraded NOTIFY True`, BODY contains `轮动雷达: 弃权 (连续第 1 日)`;
`AC2-C recovery_notice 轮动雷达恢复 ok (200 boards) — 此前弃权 1 日`.

**Match: exact.**

CLI proof, today's real 07-07 abstain:
```
uv run irc notify-status --run-kind flow-capture --last-exit-code 0 --no-notify-on-clean --repo-root . 2>&1 | grep -E "severity=" || true
```
Observed:
```
[18:18:47] INFO     notify-status severity=degraded            notify_cmd.py:322
                    notify=True
```
Expected: `notify-status severity=degraded notify=True` (today's real 07-07 abstain pages).
**Match.**

**AC2: PASS**

---

## AC3 — weekly, real 07-04 `gold_regime.json` → `DXY 滞后 21d`

Command: verbatim brief Step 5 harness (pure call to `weekly_health` against
`outputs/2026-07-04/gold_regime.json`, `today=date(2026, 7, 7)`).

Observed:
```
AC3 BODY 宏观驱动: DXY 滞后 21d (06-16) · 缺失驱动: etf_holdings_gld
AC3 OK — pure proof against the real 07-04 artifact; the weekly EDGE reads today's gold_regime.json, which on a non-Saturday date does not exist, so the 21d figure is captured by calling weekly_health directly with today=2026-07-07.
```

Expected: BODY contains `宏观驱动: DXY 滞后 21d (06-16)` + `缺失驱动: etf_holdings_gld`;
`AC3 OK`. **Match: exact.**

**AC3: PASS**

---

## Summary table

| AC | Description | Severity observed | should_notify | Result |
|----|---|---|---|---|
| AC1 | monitor, real 07-07 | degraded | True | PASS |
| AC2 | flow-capture abstain (07-05) + recovery (07-06) | degraded (07-05) | True | PASS |
| AC3 | weekly, real 07-04 gold_regime.json | n/a (pure digest, no severity in this call) | n/a | PASS |
| AC4 | board-PE DARK fixture, IRC_NOTIFY_ON_CLEAN=0 | degraded | True | PASS |
| AC5 | corrupt eval_trace.json | degraded | True (exit=0) | PASS |

All 5 acceptance criteria PASS against real artifacts / committed fixtures. No deviations
from the brief's commands — every harness ran verbatim, every printed line matched the
brief's "Expected" text exactly. No files changed (evidence-capture task); no commit made,
consistent with brief Step 6 ("No commit (no files changed)") and the fact that
`.superpowers/sdd/` is entirely gitignored (`.superpowers/` line 50 of `.gitignore`).

## Deviations

None. This report itself is the evidence-of-record; `docs/2026-07-07-data-health-notify/items/001-notes.md`
was not appended to because Task 11 introduced no code/test deviation from the brief (all
commands ran byte-identical to the brief, all assertions passed on the first try).

## Concerns for the run-level roll-up

- Confirms Task 8/plan's spec-gap judgment call #2 in practice: today's (07-07) real
  monitor severity is honestly `degraded` (symbol `688072` stale since 06-26 under the
  locked G-Q5→B per-symbol rule), not `clean` as the original spec §5 AC1 wording assumed.
  This is expected and was already logged in `PROGRESS.md` deviation #2 — Task 11 is the
  runtime confirmation that the wired path produces this result against the live store,
  not a new finding.
- Three local macOS notifications fired during this task (AC1 CLI, AC5 CLI, AC2 CLI) —
  all benign (`notify-status --run-kind {monitor,monitor,flow-capture}`), no Feishu call
  (no webhook configured), consistent with the binding constraint.
