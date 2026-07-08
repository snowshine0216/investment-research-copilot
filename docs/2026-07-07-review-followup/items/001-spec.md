# Data-health notification — design spec

- **Date:** 2026-07-07
- **Status:** GRILLED + LOCKED 2026-07-07 (grill-with-docs, 7 questions — see §9) — ready
  for implementation handoff (§10)
- **Origin:** 2026-07-07 workflow review (`docs/2026-07-07-workflow-review.md` §6) + user
  directive: "for EM block impact it should have some notification to let me know what's
  missing or blocked, currently it's hidden for user."

## 1. Problem & scope

When EastMoney planes are blocked/flaky, the operator finds out only by opening artifacts:
the 12:15 monitor notification says **"clean"** even when board-PE is DARK and flow rows are
stale; the 15:45 flow-capture/rotation chain has **no notification at all** (07-05 and 07-07
rotation abstains were invisible); the Saturday weekly notification is blind to macro-driver
age (DXY has been served 3 weeks stale since 06-16 with zero signal to the user).

**In scope:** surface data degradation through the existing `irc notify-status` vertical
(macOS + Feishu, ADR 0016) for the three scheduled surfaces (monitor 12:15, flow-capture/
rotation 15:45, weekly Sat 09:00).

**Explicitly OUT of scope** (user-locked 2026-07-07):

- Fixing the egress itself — adding a CN proxy or switching the data source to `efinance`
  is a **future, separate decision**. This design must be *source-agnostic*: it reads
  degradation **states** from artifacts, never causes, so it survives that later change
  unmodified.
- The review's M-1/M-2 factor-level freshness fixes (flow age-gating inside the engine,
  real `factor_freshness`). Complementary but separate; see §7 forward-compat.
- Any change to the monitor report (schema 7 locked), memo pillars, engine versions,
  or output artifacts. This is a **notification-layer-only** feature.

## 2. Current state (verified 2026-07-07)

- `irc notify-status --run-kind {daily,weekly,monitor} --last-exit-code N`
  (`src/irc/cli.py:360-368` Click choices; `src/irc/commands/notify_cmd.py`): edge gathers a
  frozen `RunOutcome` → pure `classify_run_outcome` (`src/irc/notify/classify.py`) →
  severity `failed > halted > stale > action > clean` (precedence locked by ADR 0016 §4/§5)
  → `_dispatch` (macOS osascript + optional Feishu via `IRC_FEISHU_WEBHOOK_URL`).
- **monitor** outcome = sentinel + exit code only (`notify_cmd.py:60-76`) — no data health.
- **run-flow-capture.sh** (chains `irc rotation`) makes no notify call.
- `IRC_NOTIFY_ON_CLEAN` default **on** → the monitor notification already fires daily.

Degradation signals already on disk (all verified against today's real artifacts):

| Signal | Artifact | Field |
|---|---|---|
| Board-PE freshness | `outputs/<date>/monitor/eval_trace.json` | run-level `board_pe_freshness` `{state: FRESH\|STALE\|DARK, as_of, age_td}` (schema 7) |
| Flow store recency/coverage | `data/monitor/fund_flow_series.json` | per-symbol dated rows → newest date + symbols-at-newest count (07-07: 29/30 @ 07-06, one symbol 06-26) |
| Per-fund signal status / NO_CALL | `eval_trace.json` `funds.<id>.signal` / `gate` | `raw_status`, availability |
| Rotation day status | `outputs/<date>/rotation/rotation_radar.json` | `data_status: ok\|degraded_*\|abstain`, `dark_legs` (07-05 abstain / 07-06 ok / 07-07 abstain) |
| Macro driver age | `outputs/<date>/gold_regime.json` | `macro_snapshots[].{series_id,date}` (DXY `2026-06-16` today) |

## 3. Design

### 3.1 New pure module: `src/irc/notify/health.py`

Frozen types + pure builders (no I/O — mirrors the `classify.py` pattern):

```
@dataclass(frozen=True)
class HealthItem:
    code: str          # e.g. "board_pe_dark", "flow_stale", "rotation_abstain", "macro_driver_stale"
    level: Literal["info", "warn"]
    text: str          # rendered CN one-liner, e.g. "板块PE: STALE-1 (07-06)"

@dataclass(frozen=True)
class HealthDigest:
    items: tuple[HealthItem, ...]
    @property def has_warnings(self) -> bool
```

Pure builders per run-kind, taking already-parsed dicts (edge does the file reads):
`monitor_health(trace: dict, flow_store: dict, trading_days) -> HealthDigest`,
`rotation_health(radar: dict, recent_statuses: tuple[str, ...]) -> HealthDigest`,
`weekly_health(gold_regime: dict, today) -> HealthDigest`.

Warn rules (v1):

| Run-kind | warn when | rendered example |
|---|---|---|
| monitor | `board_pe_freshness.state == "DARK"` | `板块PE: DARK ≥4td — 价值陷阱检测不可用` |
| monitor | board-PE `STALE` | **info** (within ≤3-td policy): `板块PE: STALE-1 (07-06)` |
| monitor | flow newest date < previous trading day, OR symbols-at-newest < 80% | `资金流: 最新 07-02 (滞后 3td), 覆盖 3/30` |
| monitor | any store symbol's newest row > 3 trading days old (G-Q5→B: the store's symbol set IS the top-5 capture union, so any stale symbol = some fund's flow input violating the no-silent-stale contract) | `资金流: 最新 07-06 · 覆盖 29/30 · 1 只滞后>3td(最旧 06-26)` |
| monitor | any fund `signal.raw_status != "ok"` or NO_CALL | `信号: 2/10 非 ok (NO_CALL: 009225)` |
| rotation | `data_status == "abstain"` (+ consecutive count from `recent_statuses`) | `轮动雷达: 弃权 (连续第 2 日)` |
| rotation | `data_status` startswith `degraded_` | `轮动雷达: degraded_flow_dark` |
| rotation | flow-capture appended < 80% of union symbols (from wrapper-passed count or store delta) | `flow-capture: 7/30` |
| weekly | any `macro_snapshots` driver age > 7 calendar days | `宏观驱动: DXY 滞后 21d (06-16)` |
| weekly | driver listed in `drivers_unavailable` | **info**: `缺失驱动: etf_holdings_gld` (pipeline already degraded honestly — relay, don't escalate) |

Every builder is total: missing/corrupt input dict → single `warn` item
`health_unknown`, never an exception (degrade-never-crash, same posture as ADR 0016 AC8).

### 3.2 Classifier extension — new severity `degraded` (ADR 0016 amendment)

- `Severity` gains `"degraded"`; precedence becomes
  **`failed > halted > stale > degraded > action > clean`** and `degraded ∈ _ALWAYS_NOTIFY`
  (fires even with `IRC_NOTIFY_ON_CLEAN=0`).
- Rationale for `degraded > action`: a buy/sell action derived from degraded data should be
  tagged by its trust problem first; the action rollup still appears in the body.
- `RunOutcome` gains `health: HealthDigest | None = None` (default keeps every existing
  test/callsite valid). `_decide` appends the rendered health lines to the **body of every
  severity** when warnings exist (a `failed` run also shows what was already degraded), and
  returns `degraded` when it would otherwise return `action`/`clean` but
  `health.has_warnings`.
- Feishu/macOS formatters unchanged in signature; body just gets ` · ` -joined health lines
  appended (macOS body is single-line by existing `_escape`).

### 3.3 Edge gathering (`notify_cmd.py`)

`_build_outcome` gains a best-effort `_build_health(root, run_kind)` step:

- **monitor**: read today's `eval_trace.json` + `data/monitor/fund_flow_series.json`;
  previous-trading-day from the existing `_load_holidays` + weekday logic (reuse
  `notify/calendar.py`).
- **flow-capture** (new run-kind, §3.4): read today's `rotation_radar.json` + the radar
  jsons of the last 5 date dirs for the consecutive-abstain count + flow store delta.
- **weekly**: read today's `gold_regime.json`.

All reads wrapped: unreadable → `health_unknown` item; **notify must never fail or block on
health gathering**.

### 3.4 New run-kind `flow-capture` + wrapper line

- `cli.py` Click choice + `RunKind` Literal gain `"flow-capture"`.
- `ops/launchd/run-flow-capture.sh` gains the same best-effort tail the other wrappers have:
  `"$UV_BIN" run irc notify-status --run-kind flow-capture --last-exit-code "$rc" --no-notify-on-clean || echo ...`
- `--no-notify-on-clean` hardcoded in the wrapper: a fully-ok 15:45 chain stays **silent**
  (preserves the documented "best-effort, no page" character); it pages only on
  degradation/abstain/failure — **plus a one-time recovery notice** (G-Q3→C): when today's
  `data_status == "ok"` and the previous radar date's status was abstain/degraded, fire once
  with severity `clean` + forced `should_notify`, body `轮动雷达恢复 ok (N boards) — 此前弃权
  M 日`. Detected from the same `recent_statuses` read the consecutive-abstain counter uses.
  Monitor/weekly keep their current default-on behavior.
- Wrapper mechanics (verified against `ops/launchd/run-flow-capture.sh`): the notify tail
  goes AFTER the weekend/holiday gates (which `exit 0` first → no non-trading-day noise) and
  passes the flow-capture `$rc` (authoritative), NOT the advisory `radar_rc` — a rotation
  *crash* is still caught because the sentinel is today's `rotation_radar.json` (written on
  both ok and abstain paths, `rotation_cmd.py:158-167`; absent only on a real crash).
  **Behavior change:** a capture timeout (rc=124) now pages as `failed`, superseding the
  wrapper's "a timeout does NOT page" comment — deliberate: a capture timeout means
  tomorrow's flow is stale, which is exactly what this feature surfaces. Update the wrapper
  comment + ops/launchd/README accordingly (AC6).
- `_build_outcome` for `flow-capture`: severity from health (abstain/degraded →
  `degraded`) — note **abstain is exit-0 by design**, so `last_exit_code` alone can never
  surface it.

### 3.5 Noise policy (v1)

While a condition persists, the daily monitor notification repeats the health line daily
(it already fires daily) and the 15:45 notification repeats on each abstain day with an
incrementing `连续第 N 日` counter. No transition-state tracking in v1 — deferred until
repetition is observed to be annoying in practice (would need a small state file; contradicts
nothing).

## 4. What this does NOT change

- No monitor report/schema/engine change; no rotation `radar_version` change; no new
  fetches (health reads only files already written); no DuckDB access from notify.
- No change to existing `daily`/`weekly`/`monitor` severity outcomes when health is clean —
  every current test must keep passing with `health=None`.

## 5. Acceptance criteria (runtime proof required)

- **AC1** With today's real 2026-07-07 artifacts: `uv run irc notify-status --run-kind
  monitor --last-exit-code 0` body contains `板块PE: STALE-1` (info) and the flow line;
  severity stays `clean` (STALE within policy) — verified by capturing the rendered body.
- **AC2** With 07-05-style artifacts (rotation abstain): `--run-kind flow-capture` fires
  severity `degraded`, body contains `弃权` + consecutive count; with 07-06 artifacts
  (`data_status: ok`) after a plain-ok prior day it sends **nothing** (dispatch
  short-circuit logged); with ok-after-abstain artifacts it fires the one-time recovery
  notice exactly once.
- **AC3** With the real 07-04 `gold_regime.json`: weekly body contains `DXY 滞后 21d`.
- **AC4** Board-PE DARK fixture → monitor severity `degraded` even with
  `IRC_NOTIFY_ON_CLEAN=0`.
- **AC5** Corrupt/absent `eval_trace.json` → body contains `health unknown`, notify exits
  per its normal contract (no crash, no masking of the run rc).
- **AC6** Docs synced: ADR 0016 amendment (severity + run-kind), `ops/launchd/README.md`
  schedule table (15:45 row gains "notify on degradation"), `docs/monitor/README.md`
  daily-ops section, root README launchd row.

## 6. Test plan (TDD, per-file runs — never whole `tests/commands/`)

- `tests/notify/test_health.py` — pure builders: each warn rule, info-vs-warn split,
  total-function behavior on empty/corrupt dicts, consecutive-abstain counting.
- `tests/notify/test_classify.py` — extend: `degraded` precedence (vs action, vs stale),
  `_ALWAYS_NOTIFY` membership, body append on `failed`+warnings, `health=None` back-compat.
- `tests/commands/test_notify_cmd.py` — edge: `_build_health` per run-kind against fixture
  artifact files (copy real 07-07 trace/radar shapes — production-shaped fixtures per the
  review's Opus guidance), corrupt-file degrade, `flow-capture` sentinel logic.
- `tests/ops/test_launchd_flow_capture.py` — wrapper contains the notify tail with
  `--no-notify-on-clean` (mirror of existing run-monitor.sh assertions).

## 7. Forward-compat notes

- When review item **M-1** (flow freshness inside the engine) lands, `monitor_health`
  switches its flow rule to read the factor's own freshness field from the trace instead of
  re-deriving age from the store file — one function body, no interface change.
- When the user later adds a CN proxy **or switches to efinance**, nothing here changes:
  health reads `board_pe_freshness`/`data_status`/dates, which the new source populates
  identically. If efinance lights the board plane permanently, the DARK/abstain rules simply
  stop firing.

## 8. Open decisions — ALL RESOLVED by the 2026-07-07 grill (§9)

Q1 → G-Q3 (C: silent-on-ok + recovery notice) · Q2 → G-Q2 (degraded above action) ·
Q3 → G-Q4 (>7d + drivers_unavailable info) · Q4 → G-Q6 (STALE info, DARK escalates).
Original text retained below for traceability.

### Original open decisions (superseded)

- **Q1 15:45 silence policy** — A (recommended): silent when ok, page on degradation only
  (as specced). B: always notify at 15:45 like monitor.
- **Q2 severity precedence** — A (recommended): `degraded` ABOVE `action` (trust problem
  tags the notification; actions stay in the body). B: below `action`.
- **Q3 macro-driver age threshold** — A (recommended): warn at >7 calendar days. B: another
  threshold.
- **Q4 monitor STALE-1..3 board-PE** — A (recommended): info line only, no severity
  escalation (within ADR 0020's tolerated window); DARK escalates. B: STALE also escalates.

Effort: **S–M** (1 new ~150-line pure module + classifier delta + edge reads + 1 wrapper
line + tests + ADR amendment + doc sync).

## 9. Grill log — locked decisions (2026-07-07 grill-with-docs)

- **G-Q1 → A (locked):** interim divergence accepted — the notification computes flow
  staleness at the notify edge and may contradict the report's hardcoded "fresh" until
  M-1 lands; §7's switch-to-trace-field commitment stands. CONTEXT.md *Flow freshness
  state* corrected to stop claiming "no silent stale holds throughout" (now: contract
  documented, engine enforcement pending M-1, notification is the interim surface).
- **G-Q2 → A (locked):** `degraded` severity contract — precedence `failed > halted >
  stale > degraded > action > clean`; `degraded ∈ _ALWAYS_NOTIFY` (load-bearing: without
  it, `IRC_NOTIFY_ON_CLEAN=0` would silence a clean-run-with-DARK day, recreating the
  invisibility this feature fixes); name kept (`degraded` is the same semantic family as
  rotation's `degraded_*` data_status — a rotation `degraded_*` day producing a `degraded`
  notification reads coherently; `data_stale` rejected, collides with the `stale`
  severity). All three go into the ADR 0016 amendment.
- **G-Q7 → agreed (locked):** digest is **notification-only** — no `data_health.json`.
  It is a pure derivation of on-disk artifacts (recomputable by anyone incl. a future
  eval); a persisted copy adds only drift surface. Feishu history is the "what was I told
  on day Y" record. Trend-persistence DEFERRED to TODOS with trigger "when a health-trend
  eval is wanted". **Data-health digest** added to CONTEXT.md as the canonical term.
- **G-Q6 → A (locked):** board-PE STALE-1..3 = **info** line only (working-as-designed,
  report already renders the age tag, feeds factor math within ADR 0020's tolerated
  window); **DARK = warn/escalate** (clamp silently dies — review M-3 — and the report has
  no marker until M-3 lands). STALE-3 pre-warning (A+) rejected: no actionable lead time,
  blurs "warn = outside policy" semantics. Escalation currency stays high.
- **G-Q5 → B (locked):** monitor flow rule = run-level (newest date + coverage) PLUS a
  per-symbol stale count (symbols whose newest row >3 td old; warn when >0). Rationale:
  the run-level rule alone misses today's real live case (29/30 fresh but one symbol at
  06-26 → its fund is STALE-7 under the CONTEXT contract). Per-fund oldest-of-top-5 at
  the notify edge REJECTED — that's M-1's in-engine job; the notify edge stays a thin
  artifact reader.
- **G-Q4 → agreed (locked):** weekly macro-driver age threshold = **>7 calendar days**
  (business-daily series + Saturday cadence → healthy data is 1–3d old, holiday max ~5d;
  7d never false-fires, catches a dead route by the first/second Saturday). Plus:
  `drivers_unavailable` relayed as **info** items (pipeline already degraded honestly).
- **G-Q3 → C (locked):** 15:45 delivery = silent-on-ok + page-on-degradation + a one-time
  recovery notice on the abstain→ok transition (spec'd in §3.4). Rationale: pure
  silent-on-ok leaves recovery invisible (the F8 stale-mental-model trap — the block
  lifted 07-06 and nothing announced it); always-notify is ~250 pages/year of noise.
  Mechanical facts locked alongside: notify tail after the trading-day gates; pass
  flow-capture `$rc` (radar crash caught via the radar-json sentinel); capture timeout
  rc=124 now pages `failed` (supersedes the wrapper's no-page comment — doc update in
  AC6).

## 10. Implementation handoff

Run in a **fresh session** (design/implementation separation):

```
/autodev /Users/snow/Documents/Repository/investment-research-copilot/docs/superpowers/specs/2026-07-07-data-health-notify-design.md
```

Constraints the implementing session must carry (repo scar tissue):

1. Every worker-subagent dispatch carries the literal line **"Calling the Agent tool is
   FORBIDDEN"** (meta-delegation trap).
2. **Never run `pytest tests/commands/` whole-dir** — per-file only (documented hang).
3. Fixtures for `_build_health` MUST be **production-shaped**: copy the real 2026-07-07
   `eval_trace.json` / `rotation_radar.json` / `fund_flow_series.json` / 07-04
   `gold_regime.json` shapes — do not hand-craft (workflow-review Opus guidance; the
   rotation P0 was masked by a hand-crafted fixture).
4. Signature changes to `RunOutcome` / `classify_run_outcome`: grep ALL test callers
   (`tests/notify/`, `tests/commands/test_notify_cmd.py`, `tests/ops/`), not just the
   mirror file.
5. AC1–AC5 are **runtime proofs against today's real artifacts**, not just unit tests —
   capture the rendered notification bodies as evidence before claiming done.
6. TDD throughout; no `VERSION` bump (accumulate under CHANGELOG `[Unreleased]`).
7. ADR 0016 amendment + AC6 doc syncs land in the same branch as the code.
8. TODOS additions on completion: trend-persistence deferral (G-Q7, trigger "health-trend
   eval wanted"); monitor DARK→FRESH recovery-notice generalization (G-Q3, trigger "if
   board-plane flakiness persists after M-3").

---

*(autodev run note: this file is a verbatim copy of `docs/superpowers/specs/2026-07-07-data-health-notify-design.md`, the user-authored spec — GRILLED + LOCKED 2026-07-07. The canonical spec remains the original path; autodev copies it into the run dir for resumability. Spec + grill phases are ⏭️ pre-completed by the user; do not re-open §9 decisions.)*
