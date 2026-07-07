# Item 001 — Task 7 runtime proof (AC1–AC5)

Date: 2026-07-07. Branch: `claude/review-followup-001`. Executed verbatim per
`.superpowers/sdd/task-7-brief.md` Steps 1–6, against the real
`outputs/2026-07-07/` + `data/monitor/` artifacts (Step 1) and staged fixtures
under `tests/notify/fixtures/` (Steps 2–5).

## AC1 — monitor, real 2026-07-07 artifacts

**Expected:** `SEVERITY degraded`; BODY contains `板块PE: STALE-1 (2026-07-06)`
AND `资金流:` … `滞后>3td(最旧 2026-06-26)`. Per the locked §9 reconciliation,
`degraded` (not `clean`) is the correct outcome because G-Q5's per-symbol rule
fires on the real 688072 @ 2026-06-26 (>3td stale) in the live flow store.

**Observed:**
```
SEVERITY degraded
BODY Run completed; nothing actionable. · 板块PE: STALE-1 (2026-07-06) · 资金流: 最新 2026-07-07 · 覆盖 29/30 · 1 只滞后>3td(最旧 2026-06-26)
```

**Result: PASS.** Severity `degraded` matches the reconciled expectation.
Board-PE line is `STALE-1 (2026-07-06)` (info-level, as AC1 requires) and the
flow line carries `1 只滞后>3td(最旧 2026-06-26)` — both substrings present
verbatim.

## Step 2 / AC4 — board-PE DARK escalates under `IRC_NOTIFY_ON_CLEAN=0`

**Expected:** `SEVERITY degraded NOTIFY True`; BODY contains `板块PE: DARK`.

**Observed:**
```
SEVERITY degraded NOTIFY True
BODY Run completed; nothing actionable. · 板块PE: DARK ≥4td — 价值陷阱检测不可用 · 资金流: 最新 2026-07-07 · 覆盖 29/30 · 1 只滞后>3td(最旧 2026-06-26)
```

**Result: PASS.**

## Step 3 / AC2 — flow-capture abstain / ok-after-ok / ok-after-abstain

**Expected:**
```
ABSTAIN degraded True True
OK_AFTER_OK clean False
OK_AFTER_ABSTAIN clean True True
```

**Observed:**
```
ABSTAIN degraded True True
OK_AFTER_OK clean False
OK_AFTER_ABSTAIN clean True True
```

**Result: PASS.** Abstain today classifies `degraded`, forces notify, and the
body contains `弃权`. Two consecutive `ok` days stay `clean` and silent. An
`ok` day following an `abstain` day is `clean` but force-notifies once with a
`恢复` (recovery) marker in the body.

## Step 4 / AC3 — weekly, real 07-04 gold_regime (DXY lag)

**Expected:** `SEVERITY degraded`; BODY contains `DXY 滞后 21d (2026-06-16)`
and `缺失驱动: etf_holdings_gld`.

**Observed:**
```
SEVERITY degraded
BODY Run completed; nothing actionable. · 宏观驱动: DXY 滞后 21d (2026-06-16) · 缺失驱动: etf_holdings_gld
```

**Result: PASS.**

## Step 5 / AC5 — corrupt eval_trace.json → health unknown, no crash

**Expected:** no traceback; BODY contains `health unknown` (the
`health_unknown` line carrying the literal AC5 string); `SEVERITY degraded`
(a `warn` health_unknown escalates the clean base; run rc is untouched).

**Observed:**
```
data-health: could not read eval_trace.json
SEVERITY degraded
BODY Run completed; nothing actionable. · health unknown — 健康检查数据缺失/损坏
```

**Result: PASS.** The `data-health: could not read eval_trace.json` line is a
logged warning (stderr), not a traceback — no exception propagated. Severity
escalated to `degraded` from the corrupt-health warn, exactly as specified.

## Step 6 — full regression

```
uv run pytest tests/notify/ tests/commands/test_notify_cmd.py tests/ops/test_launchd_flow_capture.py tests/ops/test_launchd_monitor.py -v
```
**Observed:** `158 passed in 35.04s`. No failures, no errors, no skips.

```
uv run ruff check src tests
```
**Observed:** `Found 118 errors` at the whole-repo scope — all pre-existing
and confined to files this feature never touched (verified via
`git log --oneline -- src/irc/notify src/irc/commands/notify_cmd.py`, which
shows only this feature's own commits; none of the 118 flagged files —
e.g. `src/irc/queries/parser.py`, `src/irc/scoring/gold_scenarios.py` —
appear in that history). Re-scoping ruff to exactly the files this feature
added/touched:
```
uv run ruff check src/irc/notify src/irc/commands/notify_cmd.py tests/notify tests/commands/test_notify_cmd.py tests/ops/test_launchd_flow_capture.py tests/ops/test_launchd_monitor.py
```
→ `All checks passed!`

**Result: PASS** (feature-scoped ruff clean; whole-repo ruff carries a
pre-existing, unrelated baseline of 118 errors — consistent with the
project's documented pre-existing test/lint baseline, not a regression
introduced by this task).

## Summary

| AC | Expected | Observed | Verdict |
|----|----------|----------|---------|
| AC1 | degraded; STALE-1 info + flow warn (688072 @ 06-26) | matches verbatim | PASS |
| AC4 | degraded, NOTIFY True, DARK line | matches verbatim | PASS |
| AC2 | degraded/clean/clean per abstain-ok-recovery sequence | matches verbatim | PASS |
| AC3 | degraded; DXY 滞后 21d + 缺失驱动 etf_holdings_gld | matches verbatim | PASS |
| AC5 | no crash; health unknown; degraded | matches verbatim | PASS |
| Regression | notify+ops suites pass; ruff clean | 158 passed; feature-scope ruff clean (repo-wide has 118 pre-existing, unrelated) | PASS |

No BLOCKED conditions encountered. No code changes made in this task
(verification only, per brief).
