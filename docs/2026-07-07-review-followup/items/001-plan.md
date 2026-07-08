# Data-health notification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface EastMoney/data degradation (board-PE DARK, flow staleness, rotation abstain, stale macro drivers) through the existing `irc notify-status` vertical for the three scheduled surfaces (monitor 12:15, flow-capture 15:45, weekly Sat 09:00), without touching any report/schema/engine.

**Architecture:** A new **pure** module `src/irc/notify/health.py` derives a `HealthDigest` (tuple of `HealthItem`) from already-parsed artifact dicts — no I/O. A new **edge** module `src/irc/commands/notify_health.py` does the file reads and hands dicts to the pure builders. The classifier (`classify.py`) gains a `degraded` severity between `stale` and `action`; `RunOutcome` carries an optional `health` digest + a `force_notify` flag. The `notify_cmd.py` edge attaches the digest per run-kind and adds a `flow-capture` run-kind. One wrapper line + doc syncs complete it.

**Tech Stack:** Python 3.12, frozen dataclasses, Click CLI, pytest, uv. No new dependencies.

## Global Constraints

Copied verbatim from spec §10 (implementation handoff) + repo law. **Every task's requirements implicitly include this section.**

- **Every worker-subagent dispatch carries the literal line `Calling the Agent tool is FORBIDDEN`.** (Meta-delegation trap — MEMORY `feedback_subagent_no_delegation_line`.)
- **Never run `pytest tests/commands/` whole-dir — per-file only** (documented suite-ordering hang). Run `uv run pytest tests/commands/test_notify_cmd.py` explicitly.
- **Fixtures MUST be production-shaped** — derived by copying/reducing the real 2026-07-07 `eval_trace.json` / `rotation_radar.json` / `fund_flow_series.json` and 07-04 `gold_regime.json` (exact commands in Task 1 / Task 4). Do **not** hand-craft artifact dicts (the rotation P0 was masked by a hand-crafted fixture).
- **Signature changes to `RunOutcome` / `classify_run_outcome`: grep ALL test callers** (`tests/notify/`, `tests/commands/test_notify_cmd.py`, `tests/ops/`), not just the mirror file. `RunOutcome` gains only defaulted fields, so existing call sites stay valid — verify with the grep in Task 3.
- **AC1–AC5 are runtime proofs against today's real artifacts**, not just unit tests — capture the rendered severity + body as evidence (Task 7).
- **TDD throughout** (red → run-to-fail → green → commit). **No `VERSION` bump** — accumulate under CHANGELOG `[Unreleased]`.
- **Functional/immutable**: pure builders return new `HealthDigest`/`HealthItem` tuples; no argument mutation; I/O confined to the edge (`notify_cmd.py` / `notify_health.py`). Files < 200 lines ideal, functions < 20 lines ideal.
- **Secrets via `.env` names only** — this feature adds none.
- **ADR 0016 amendment + AC6 doc syncs land in this same branch** (Task 6). `CONTEXT.md` already carries the "Data-health digest" entry (G-Q7) — do **not** re-add it.
- Branch: `autodev/review-followup-feature` (already checked out — do NOT switch/push).
- ⚠️ Ignore the stale worktree at `.claude/worktrees/data-health-notify/` — plan from current main-tree code only.

### Locked decisions carried from spec §9 (do NOT re-open)

- **G-Q2:** precedence `failed > halted > stale > degraded > action > clean`; `degraded ∈ _ALWAYS_NOTIFY`.
- **G-Q6:** board-PE `STALE-1..3` = **info** (no escalation); `DARK` = **warn** (escalate).
- **G-Q5:** monitor flow rule = run-level (newest date + coverage) **PLUS** a per-symbol stale count (any store symbol whose newest row > 3 trading days old → warn).
- **G-Q4:** weekly macro-driver age threshold = **> 7 calendar days**; `drivers_unavailable` relayed as **info**.
- **G-Q3:** 15:45 = silent-on-ok + page-on-degradation + **one-time recovery notice** on abstain→ok; pass flow-capture `$rc`; capture timeout rc=124 now pages `failed`.

### Field-name reconciliation (verified against real 2026-07-07 artifacts)

The spec §2/§3 text says the per-fund status field is `signal.raw_status`. The **on-disk** `eval_trace.json` uses **`signal.status`** (`raw_status` is only the rename in `monitor/eval/forward_log.py`). This plan reads **`signal.status`** and the derived **`published_state == "NO_CALL"`**. This is a field-name correction, not a §9 re-open. Verified: all 10 funds today have `signal.status == "ok"`, `board_pe_freshness == {"state":"STALE","as_of":"2026-07-06","age_td":1}`; flow store has 30 symbols, 29 @ `2026-07-07`, symbol `688072` @ `2026-06-26`; rotation `data_status`: 07-05 `abstain`, 07-06 `ok`, 07-07 `abstain`; gold_regime 07-04 DXY @ `2026-06-16`, `drivers_unavailable == ["etf_holdings_gld"]`.

### ⚠️ AC1 severity reconciliation (read before Task 7)

Spec AC1 literally says monitor severity "stays `clean`". On the **real** 07-07 flow store, symbol `688072` is at `2026-06-26` (> 3 trading days old), so **G-Q5's per-symbol rule fires a `warn`** → the digest has a warning → severity is **`degraded`**, not `clean`. G-Q5 is LAW (§9) and was locked *using this exact symbol* as its motivating case; AC1's "clean" parenthetical only justifies the board-PE STALE decision (G-Q6). **Honor G-Q5**: Task 7's AC1 proof asserts severity `degraded` with the `板块PE: STALE-1` info line AND the flow per-symbol warn line both present. This is documented, not planned-around.

---

## File Structure

**Create:**
- `src/irc/notify/health.py` — pure digest builders + `HealthItem`/`HealthDigest` types (~145 lines).
- `src/irc/commands/notify_health.py` — edge: artifact file reads → pure builders (~70 lines).
- `tests/notify/test_health.py` — pure-builder unit tests.
- `tests/ops/test_launchd_flow_capture.py` — wrapper notify-tail assertions.
- `tests/notify/fixtures/*.json` — production-shaped fixtures (copied/reduced from real artifacts).

**Modify:**
- `src/irc/notify/calendar.py` — add pure `recent_trading_days`.
- `src/irc/notify/types.py` — `Severity` += `degraded`; `RunKind` += `flow-capture`; `RunOutcome` += `health`, `force_notify`.
- `src/irc/notify/classify.py` — `_ALWAYS_NOTIFY` += `degraded`; health append + escalation; `force_notify` in `should_notify`.
- `src/irc/commands/notify_cmd.py` — attach health per run-kind; `flow-capture` outcome branch.
- `src/irc/cli.py` — `--run-kind` Choice += `flow-capture`.
- `ops/launchd/run-flow-capture.sh` — best-effort notify tail + header comment fix.
- `tests/notify/test_calendar.py`, `tests/notify/test_classify.py`, `tests/commands/test_notify_cmd.py` — extend.
- `docs/adr/0016-local-scheduling-and-notification.md`, `ops/launchd/README.md`, `docs/monitor/README.md`, `README.md`, `CHANGELOG.md`, `TODOS.md` — Task 6.

---

## Task 1: Pure `health.py` — types, `recent_trading_days`, `monitor_health`

**Files:**
- Modify: `src/irc/notify/calendar.py`
- Create: `src/irc/notify/health.py`
- Create: `tests/notify/fixtures/` (copied real artifacts)
- Modify/Create test: `tests/notify/test_calendar.py`, `tests/notify/test_health.py`

**Interfaces:**
- Produces: `HealthItem(code: str, level: Literal["info","warn"], text: str)`; `HealthDigest(items: tuple[HealthItem, ...])` with `.has_warnings: bool`.
- Produces: `recent_trading_days(today: date, holidays: frozenset[date]|set[date], n: int) -> tuple[date, ...]` (ascending, most-recent last, ≤ today, skips weekend+holidays).
- Produces: `monitor_health(trace: dict, flow_store: dict, trading_days: tuple[date, ...]) -> HealthDigest`.

- [ ] **Step 1: Create production-shaped fixtures from real artifacts**

```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
mkdir -p tests/notify/fixtures
# Monitor trace: REDUCE the 2.1 MB real file to only the keys the builder reads,
# preserving real values/shape (board_pe_freshness verbatim + per-fund signal.status
# + published_state). This is a reduction of real data, NOT hand-crafting.
uv run python -c "
import json
t = json.load(open('outputs/2026-07-07/monitor/eval_trace.json'))
red = {k: t[k] for k in ('schema_version','engine_version','run_date','board_pe_freshness')}
red['funds'] = {
    fid: {'signal': {'status': rec.get('signal',{}).get('status')},
          'published_state': rec.get('published_state')}
    for fid, rec in t['funds'].items()
}
json.dump(red, open('tests/notify/fixtures/eval_trace_monitor.json','w'), ensure_ascii=False, indent=1)
print('funds:', len(red['funds']), 'board_pe:', red['board_pe_freshness'])
"
cp data/monitor/fund_flow_series.json tests/notify/fixtures/fund_flow_series.json
cp outputs/2026-07-07/rotation/rotation_radar.json tests/notify/fixtures/rotation_radar_abstain.json
cp outputs/2026-07-05/rotation/rotation_radar.json tests/notify/fixtures/rotation_radar_abstain_0705.json
# OK radar: reduce board_states to 3 entries (board_count only needs len()); keep data_status + diagnostics shape.
uv run python -c "
import json
r = json.load(open('outputs/2026-07-06/rotation/rotation_radar.json'))
r['board_states'] = r['board_states'][:3]
json.dump(r, open('tests/notify/fixtures/rotation_radar_ok.json','w'), ensure_ascii=False, indent=1)
print('data_status:', r['data_status'], 'boards kept:', len(r['board_states']))
"
cp outputs/2026-07-04/gold_regime.json tests/notify/fixtures/gold_regime.json
ls -la tests/notify/fixtures/
```
Expected: 6 fixture files; monitor trace prints `funds: 10 board_pe: {'state': 'STALE', ...}`; ok radar prints `data_status: ok boards kept: 3`.

- [ ] **Step 2: Write the failing test for `recent_trading_days`**

Append to `tests/notify/test_calendar.py`:
```python
from datetime import date

from irc.notify.calendar import recent_trading_days


def test_recent_trading_days_skips_weekend_and_holiday():
    # 2026-07-07 is a Tuesday; 07-04/07-05 are Sat/Sun; make 07-03 a holiday.
    days = recent_trading_days(date(2026, 7, 7), {date(2026, 7, 3)}, 4)
    assert days == (
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 6),
        date(2026, 7, 7),
    )
    assert days[-1] == date(2026, 7, 7)  # ascending, today last
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/notify/test_calendar.py::test_recent_trading_days_skips_weekend_and_holiday -v`
Expected: FAIL — `ImportError: cannot import name 'recent_trading_days'`.

- [ ] **Step 4: Implement `recent_trading_days` in `calendar.py`**

Edit `src/irc/notify/calendar.py` — change the import line and append the function:
```python
from datetime import date, timedelta
```
```python
def recent_trading_days(
    today: date, holidays: frozenset[date] | set[date], n: int
) -> tuple[date, ...]:
    """The n most recent trading days ≤ today, ascending (today last).

    Walks back day by day, skipping Sat/Sun and holidays. n must be ≥ 1.
    """
    out: list[date] = []
    cursor = today
    while len(out) < n:
        if cursor.weekday() < _SATURDAY and cursor not in holidays:
            out.append(cursor)
        cursor = cursor - timedelta(days=1)
    return tuple(reversed(out))
```

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/notify/test_calendar.py -v`
Expected: PASS (all calendar tests).

- [ ] **Step 6: Write failing tests for `monitor_health`**

Create `tests/notify/test_health.py`:
```python
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from irc.notify.health import HealthDigest, monitor_health

_FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


# 2026-07-07 trading-day tuple (Wed..Tue, weekend gap 07-04/05).
_TDAYS = (date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3),
          date(2026, 7, 6), date(2026, 7, 7))


def test_monitor_health_stale_board_pe_is_info():
    trace = _load("eval_trace_monitor.json")
    digest = monitor_health(trace, {}, _TDAYS)
    board = [i for i in digest.items if i.code == "board_pe_stale"]
    assert board and board[0].level == "info"
    assert "STALE-1" in board[0].text and "2026-07-06" in board[0].text


def test_monitor_health_dark_board_pe_is_warn():
    trace = _load("eval_trace_monitor.json")
    trace = {**trace, "board_pe_freshness": {"state": "DARK", "as_of": "2026-07-01", "age_td": 4}}
    digest = monitor_health(trace, {}, _TDAYS)
    dark = [i for i in digest.items if i.code == "board_pe_dark"]
    assert dark and dark[0].level == "warn"
    assert digest.has_warnings is True


def test_monitor_health_per_symbol_stale_is_warn():
    trace = _load("eval_trace_monitor.json")
    flow = _load("fund_flow_series.json")  # real: 688072 @ 2026-06-26 (>3 td)
    digest = monitor_health(trace, flow, _TDAYS)
    stale = [i for i in digest.items if i.code == "flow_symbol_stale"]
    assert stale and stale[0].level == "warn"
    assert "滞后>3td" in stale[0].text and "2026-06-26" in stale[0].text
    assert digest.has_warnings is True


def test_monitor_health_run_level_lag_is_warn():
    trace = _load("eval_trace_monitor.json")
    # All symbols one week stale but uniform → run-level lag, no per-symbol split.
    flow = {"600000": [["2026-06-20", 1.0]], "600036": [["2026-06-20", 2.0]]}
    digest = monitor_health(trace, flow, _TDAYS)
    lag = [i for i in digest.items if i.code == "flow_stale"]
    assert lag and lag[0].level == "warn"


def test_monitor_health_signal_not_ok_is_warn():
    trace = _load("eval_trace_monitor.json")
    funds = {**trace["funds"]}
    fid = next(iter(funds))
    funds[fid] = {"signal": {"status": "gated"}, "published_state": "NO_CALL"}
    trace = {**trace, "funds": funds}
    digest = monitor_health(trace, {}, _TDAYS)
    sig = [i for i in digest.items if i.code == "signal_not_ok"]
    assert sig and sig[0].level == "warn" and fid in sig[0].text


def test_monitor_health_empty_trace_is_health_unknown():
    digest = monitor_health({}, {}, _TDAYS)
    assert digest.items and digest.items[0].code == "health_unknown"
    assert digest.has_warnings is True


def test_monitor_health_clean_when_fresh_and_covered():
    trace = _load("eval_trace_monitor.json")
    trace = {**trace, "board_pe_freshness": {"state": "FRESH", "as_of": "2026-07-07", "age_td": 0}}
    flow = {"600000": [["2026-07-07", 1.0]], "600036": [["2026-07-07", 2.0]]}
    digest = monitor_health(trace, flow, _TDAYS)
    assert digest == HealthDigest(())
```

- [ ] **Step 7: Run to verify they fail**

Run: `uv run pytest tests/notify/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.notify.health'`.

- [ ] **Step 8: Implement `health.py` (types + monitor builder)**

Create `src/irc/notify/health.py`:
```python
"""PURE data-health digest builders. No I/O — the notify edge reads the
artifact files and passes already-parsed dicts. Mirrors classify.py
(CONTEXT.md "Data-health digest" / ADR 0016 amendment).

Every builder is TOTAL: a missing/corrupt input dict yields a single `warn`
`health_unknown` item, never an exception (degrade-never-crash, ADR 0016 AC8).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Level = Literal["info", "warn"]

_COVERAGE_FLOOR = 0.80
_MACRO_MAX_AGE_DAYS = 7
_MAX_SIGNAL_IDS = 3


@dataclass(frozen=True)
class HealthItem:
    code: str
    level: Level
    text: str


@dataclass(frozen=True)
class HealthDigest:
    items: tuple[HealthItem, ...]

    @property
    def has_warnings(self) -> bool:
        return any(item.level == "warn" for item in self.items)


_UNKNOWN = HealthDigest(
    (HealthItem("health_unknown", "warn", "health unknown — 健康检查数据缺失/损坏"),)
)  # text carries the literal "health unknown" (AC5) + the CN gloss


def monitor_health(
    trace: dict, flow_store: dict, trading_days: tuple[date, ...]
) -> HealthDigest:
    """Board-PE freshness + flow recency/coverage + per-fund signal status."""
    if not trace or "board_pe_freshness" not in trace:
        return _UNKNOWN
    items = (
        _board_pe_item(trace["board_pe_freshness"])
        + _flow_items(flow_store, trading_days)
        + _signal_items(trace.get("funds", {}))
    )
    return HealthDigest(items)


def _board_pe_item(bpf: dict) -> tuple[HealthItem, ...]:
    state = bpf.get("state")
    if state == "DARK":
        return (HealthItem("board_pe_dark", "warn", "板块PE: DARK ≥4td — 价值陷阱检测不可用"),)
    if state == "STALE":
        return (HealthItem("board_pe_stale", "info",
                           f"板块PE: STALE-{bpf.get('age_td')} ({bpf.get('as_of')})"),)
    return ()


def _newest_by_symbol(flow_store: dict) -> dict[str, str]:
    return {sym: max(row[0] for row in rows) for sym, rows in flow_store.items() if rows}


def _flow_items(flow_store: dict, trading_days: tuple[date, ...]) -> tuple[HealthItem, ...]:
    newest = _newest_by_symbol(flow_store)
    if not newest:
        return ()
    run_newest = max(newest.values())
    total = len(newest)
    at_newest = sum(1 for d in newest.values() if d == run_newest)
    head = f"资金流: 最新 {run_newest} · 覆盖 {at_newest}/{total}"
    stale = _stale_symbols(newest, trading_days)
    if stale:
        oldest = min(newest[sym] for sym in stale)
        return (HealthItem("flow_symbol_stale", "warn",
                           f"{head} · {len(stale)} 只滞后>3td(最旧 {oldest})"),)
    if _run_level_stale(run_newest, at_newest, total, trading_days):
        return (HealthItem("flow_stale", "warn", head),)
    return ()


def _stale_symbols(newest: dict[str, str], trading_days: tuple[date, ...]) -> tuple[str, ...]:
    if len(trading_days) < 4:
        return ()
    cutoff = trading_days[-4].isoformat()  # >3 trading days old ⇒ older than the 4th-recent session
    return tuple(sym for sym, d in newest.items() if d < cutoff)


def _run_level_stale(
    run_newest: str, at_newest: int, total: int, trading_days: tuple[date, ...]
) -> bool:
    lagging = len(trading_days) >= 2 and run_newest < trading_days[-2].isoformat()
    return lagging or (at_newest / total) < _COVERAGE_FLOOR


def _signal_items(funds: dict) -> tuple[HealthItem, ...]:
    if not funds:
        return ()
    bad = tuple(
        fid for fid, rec in funds.items()
        if rec.get("signal", {}).get("status") != "ok"
        or rec.get("published_state") == "NO_CALL"
    )
    if not bad:
        return ()
    listed = ", ".join(bad[:_MAX_SIGNAL_IDS])
    return (HealthItem("signal_not_ok", "warn",
                       f"信号: {len(bad)}/{len(funds)} 非 ok (NO_CALL: {listed})"),)
```

- [ ] **Step 9: Run to verify all Task-1 tests pass**

Run: `uv run pytest tests/notify/test_health.py tests/notify/test_calendar.py -v`
Expected: PASS (all).

- [ ] **Step 10: Lint**

Run: `uv run ruff check src/irc/notify/health.py src/irc/notify/calendar.py tests/notify/test_health.py`
Expected: no errors.

- [ ] **Step 11: Commit**

```bash
git add src/irc/notify/health.py src/irc/notify/calendar.py \
        tests/notify/test_health.py tests/notify/test_calendar.py tests/notify/fixtures/
git commit -m "feat(notify): pure monitor_health digest + recent_trading_days"
```

---

## Task 2: Pure `rotation_health`, `detect_rotation_recovery`, `weekly_health`

**Files:**
- Modify: `src/irc/notify/health.py`
- Modify test: `tests/notify/test_health.py`

**Interfaces:**
- Consumes: `HealthItem`, `HealthDigest` (Task 1).
- Produces: `rotation_health(radar: dict, recent_statuses: tuple[str, ...]) -> HealthDigest`.
- Produces: `detect_rotation_recovery(recent_statuses: tuple[str, ...], board_count: int) -> str | None` — recovery body when today `ok` follows ≥1 abstain/degraded, else `None`.
- Produces: `weekly_health(gold_regime: dict, today: date) -> HealthDigest`.
- `recent_statuses` is ascending (today last).

- [ ] **Step 1: Write failing tests**

Append to `tests/notify/test_health.py`:
```python
from irc.notify.health import (
    detect_rotation_recovery,
    rotation_health,
    weekly_health,
)


def test_rotation_health_abstain_counts_consecutive():
    radar = _load("rotation_radar_abstain.json")  # data_status == "abstain"
    digest = rotation_health(radar, ("ok", "abstain", "abstain"))
    item = digest.items[0]
    assert item.code == "rotation_abstain" and item.level == "warn"
    assert "连续第 2 日" in item.text
    assert digest.has_warnings is True


def test_rotation_health_degraded_prefix_is_warn():
    digest = rotation_health({"data_status": "degraded_flow_dark"}, ("degraded_flow_dark",))
    assert digest.items[0].code == "rotation_degraded"
    assert "degraded_flow_dark" in digest.items[0].text


def test_rotation_health_ok_is_empty():
    radar = _load("rotation_radar_ok.json")  # data_status == "ok"
    assert rotation_health(radar, ("abstain", "ok")) == HealthDigest(())


def test_rotation_health_missing_status_is_unknown():
    digest = rotation_health({}, ())
    assert digest.items[0].code == "health_unknown"


def test_detect_recovery_on_abstain_to_ok():
    radar = _load("rotation_radar_ok.json")
    board_count = len(radar["board_states"])
    text = detect_rotation_recovery(("abstain", "ok"), board_count)
    assert text is not None
    assert f"{board_count} boards" in text and "此前弃权 1 日" in text


def test_detect_recovery_none_when_no_prior_degradation():
    assert detect_rotation_recovery(("ok", "ok"), 200) is None


def test_detect_recovery_none_when_today_not_ok():
    assert detect_rotation_recovery(("abstain", "abstain"), 200) is None


def test_weekly_health_flags_stale_macro_driver():
    gold = _load("gold_regime.json")  # DXY @ 2026-06-16
    digest = weekly_health(gold, date(2026, 7, 7))
    dxy = [i for i in digest.items if i.code == "macro_driver_stale" and "DXY" in i.text]
    assert dxy and dxy[0].level == "warn"
    assert "滞后 21d" in dxy[0].text


def test_weekly_health_relays_unavailable_as_info():
    gold = _load("gold_regime.json")  # drivers_unavailable == ["etf_holdings_gld"]
    digest = weekly_health(gold, date(2026, 7, 7))
    unavail = [i for i in digest.items if i.code == "driver_unavailable"]
    assert unavail and unavail[0].level == "info"
    assert "etf_holdings_gld" in unavail[0].text


def test_weekly_health_empty_is_unknown():
    assert weekly_health({}, date(2026, 7, 7)).items[0].code == "health_unknown"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/notify/test_health.py -v -k "rotation or recovery or weekly"`
Expected: FAIL — `ImportError: cannot import name 'rotation_health'`.

- [ ] **Step 3: Implement the three builders in `health.py`**

Append to `src/irc/notify/health.py`:
```python
def rotation_health(radar: dict, recent_statuses: tuple[str, ...]) -> HealthDigest:
    """Rotation abstain/degraded → warn; ok → empty; missing → unknown."""
    if not radar or "data_status" not in radar:
        return _UNKNOWN
    status = radar["data_status"]
    if status == "abstain":
        consec = _consecutive_degraded(recent_statuses)
        return HealthDigest((HealthItem("rotation_abstain", "warn",
                             f"轮动雷达: 弃权 (连续第 {consec} 日)"),))
    if isinstance(status, str) and status.startswith("degraded_"):
        return HealthDigest((HealthItem("rotation_degraded", "warn",
                             f"轮动雷达: {status}"),))
    return HealthDigest(())


def _is_degraded(status: object) -> bool:
    return status == "abstain" or (isinstance(status, str) and status.startswith("degraded_"))


def _consecutive_degraded(recent_statuses: tuple[str, ...]) -> int:
    count = 0
    for status in reversed(recent_statuses):
        if not _is_degraded(status):
            break
        count += 1
    return count


def detect_rotation_recovery(
    recent_statuses: tuple[str, ...], board_count: int
) -> str | None:
    """Body for the one-time abstain→ok recovery notice, else None."""
    if len(recent_statuses) < 2 or recent_statuses[-1] != "ok":
        return None
    prior_run = _consecutive_degraded(recent_statuses[:-1])
    if prior_run == 0:
        return None
    return f"轮动雷达恢复 ok ({board_count} boards) — 此前弃权 {prior_run} 日"


def weekly_health(gold_regime: dict, today: date) -> HealthDigest:
    """Macro-driver age (>7 calendar days ⇒ warn) + drivers_unavailable (info)."""
    if not gold_regime:
        return _UNKNOWN
    items = _macro_items(gold_regime.get("macro_snapshots", []), today)
    items += _unavailable_items(gold_regime.get("drivers_unavailable", []))
    return HealthDigest(items)


def _macro_items(snapshots: list, today: date) -> tuple[HealthItem, ...]:
    out: list[HealthItem] = []
    for snap in snapshots:
        age = _driver_age(snap.get("date"), today)
        if age is not None and age > _MACRO_MAX_AGE_DAYS:
            out.append(HealthItem("macro_driver_stale", "warn",
                       f"宏观驱动: {snap.get('series_id')} 滞后 {age}d ({snap.get('date')})"))
    return tuple(out)


def _driver_age(raw: object, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(raw))).days
    except (TypeError, ValueError):
        return None


def _unavailable_items(names: list) -> tuple[HealthItem, ...]:
    return tuple(
        HealthItem("driver_unavailable", "info", f"缺失驱动: {name}") for name in names
    )
```

- [ ] **Step 4: Run to verify all `health.py` tests pass**

Run: `uv run pytest tests/notify/test_health.py -v`
Expected: PASS (all).

- [ ] **Step 5: Lint + size check**

Run: `uv run ruff check src/irc/notify/health.py && wc -l src/irc/notify/health.py`
Expected: no errors; line count < 200.

- [ ] **Step 6: Commit**

```bash
git add src/irc/notify/health.py tests/notify/test_health.py
git commit -m "feat(notify): rotation + recovery + weekly health builders"
```

---

## Task 3: Classifier extension — `degraded` severity + `RunOutcome` fields

**Files:**
- Modify: `src/irc/notify/types.py`
- Modify: `src/irc/notify/classify.py`
- Modify test: `tests/notify/test_classify.py`

**Interfaces:**
- Consumes: `HealthDigest` (Task 1).
- Produces: `RunOutcome` with new defaulted fields `health: HealthDigest | None = None`, `force_notify: bool = False`; `Severity` includes `"degraded"`; `RunKind` includes `"flow-capture"`.
- Behavior: `classify_run_outcome` appends `" · "`-joined health item texts to the body; escalates a `clean`/`action` base to `degraded` when `health.has_warnings`; `should_notify` is True when `force_notify`.

- [ ] **Step 1: Grep all `RunOutcome` / `classify_run_outcome` callers (constraint)**

Run:
```bash
grep -rn "RunOutcome(\|classify_run_outcome(" src tests
```
Expected: call sites in `src/irc/commands/notify_cmd.py`, `src/irc/notify/classify.py`, `tests/notify/test_classify.py`, `tests/commands/test_notify_cmd.py`. Confirm none pass `health`/`force_notify` positionally (they don't) — the new defaulted fields keep every call valid.

- [ ] **Step 2: Write failing tests**

Add to `tests/notify/test_classify.py` (extend `_outcome` helper is not needed — pass new fields as overrides). Append:
```python
from irc.notify.health import HealthDigest, HealthItem

_WARN = HealthDigest((HealthItem("board_pe_dark", "warn", "板块PE: DARK ≥4td"),))
_INFO = HealthDigest((HealthItem("board_pe_stale", "info", "板块PE: STALE-1 (2026-07-06)"),))


def test_clean_with_warning_escalates_to_degraded():
    decision = classify_run_outcome(_outcome(health=_WARN))
    assert decision.severity == "degraded"
    assert decision.should_notify is True  # degraded ∈ _ALWAYS_NOTIFY
    assert "DARK" in decision.body


def test_degraded_fires_even_when_notify_on_clean_false():
    decision = classify_run_outcome(_outcome(health=_WARN), notify_on_clean=False)
    assert decision.severity == "degraded"
    assert decision.should_notify is True


def test_clean_with_info_only_stays_clean_but_appends_body():
    decision = classify_run_outcome(_outcome(health=_INFO))
    assert decision.severity == "clean"
    assert "STALE-1" in decision.body


def test_action_with_warning_becomes_degraded_keeps_rollup():
    decision = classify_run_outcome(_outcome(actionable_buy_count=2, health=_WARN))
    assert decision.severity == "degraded"
    assert "2 buys" in decision.body and "DARK" in decision.body


def test_failed_appends_health_but_stays_failed():
    decision = classify_run_outcome(_outcome(last_exit_code=1, health=_WARN))
    assert decision.severity == "failed"
    assert "DARK" in decision.body


def test_force_notify_sends_clean():
    decision = classify_run_outcome(_outcome(force_notify=True), notify_on_clean=False)
    assert decision.severity == "clean"
    assert decision.should_notify is True


def test_health_none_is_backcompat():
    decision = classify_run_outcome(_outcome())
    assert decision.severity == "clean"
    assert decision.body == "Run completed; nothing actionable."
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/notify/test_classify.py -v -k "degraded or force_notify or health or escalate or info_only"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'health'`.

- [ ] **Step 4: Extend `types.py`**

Edit `src/irc/notify/types.py`:
```python
from irc.notify.health import HealthDigest
```
```python
Severity = Literal["failed", "halted", "stale", "degraded", "action", "clean"]
RunKind = Literal["daily", "weekly", "monitor", "flow-capture"]
```
Append two fields to `RunOutcome` (after `promotion_ids`):
```python
    # Data-health digest derived at the notify edge (ADR 0016 amendment). None
    # keeps every pre-existing call site + test valid. `force_notify` lets the
    # 15:45 abstain→ok recovery notice page despite a clean severity.
    health: HealthDigest | None = None
    force_notify: bool = False
```

- [ ] **Step 5: Extend `classify.py`**

Edit `src/irc/notify/classify.py`:

Change `_ALWAYS_NOTIFY`:
```python
_ALWAYS_NOTIFY = {"failed", "halted", "stale", "degraded", "action"}
```
Replace `classify_run_outcome` body:
```python
def classify_run_outcome(
    outcome: RunOutcome, *, notify_on_clean: bool = True
) -> NotificationDecision:
    """Map a RunOutcome to a NotificationDecision in fixed precedence."""
    severity, title, body = _apply_health(outcome, _decide(outcome))
    should_notify = (
        outcome.force_notify
        or severity in _ALWAYS_NOTIFY
        or (severity == "clean" and notify_on_clean)
    )
    return NotificationDecision(
        should_notify=should_notify, severity=severity, title=title, body=body
    )
```
Add `_apply_health` (leave `_decide` unchanged as the base):
```python
def _apply_health(
    outcome: RunOutcome, base: tuple[str, str, str]
) -> tuple[str, str, str]:
    """Append health lines to the body; escalate clean/action → degraded on a
    warning. failed/halted/stale keep their severity but still show what was
    already degraded (spec §3.2)."""
    base_sev, title, body = base
    health = outcome.health
    if health is None or not health.items:
        return base
    body = f"{body} · " + " · ".join(item.text for item in health.items)
    if health.has_warnings and base_sev in ("clean", "action"):
        title = "IRC data degraded" if base_sev == "clean" else title
        return ("degraded", title, body)
    return (base_sev, title, body)
```

- [ ] **Step 6: Run the whole notify unit suite**

Run: `uv run pytest tests/notify/ -v`
Expected: PASS (all — including the pre-existing `test_classify.py` / `test_types.py` back-compat).

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/irc/notify/`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add src/irc/notify/types.py src/irc/notify/classify.py tests/notify/test_classify.py
git commit -m "feat(notify): degraded severity + health digest on RunOutcome"
```

---

## Task 4: Edge wiring — `notify_health.py` + `notify_cmd.py` + `flow-capture` run-kind

**Files:**
- Create: `src/irc/commands/notify_health.py`
- Modify: `src/irc/commands/notify_cmd.py`
- Modify: `src/irc/cli.py`
- Modify test: `tests/commands/test_notify_cmd.py`

**Interfaces:**
- Consumes: `monitor_health`, `weekly_health`, `rotation_health`, `detect_rotation_recovery`, `recent_trading_days`, `HealthDigest`, `HealthItem`.
- Produces (edge, `notify_health.py`):
  - `read_monitor_health(root: Path, today: date, holidays: set[date]) -> HealthDigest`
  - `read_weekly_health(root: Path, today: date) -> HealthDigest`
  - `read_flow_capture(root: Path, today: date) -> tuple[HealthDigest, bool]` (digest, force_notify)
- Produces (`notify_cmd.py`): `_build_outcome` attaches health for monitor/weekly and dispatches to a new `flow-capture` branch.

- [ ] **Step 1: Write failing edge tests**

Append to `tests/commands/test_notify_cmd.py`:
```python
import shutil
from datetime import date

from irc.commands import notify_health

_FIX = Path(__file__).parents[1] / "notify" / "fixtures"


def _stage_monitor(root: Path, day: str) -> None:
    mon = root / "outputs" / day / "monitor"
    mon.mkdir(parents=True)
    shutil.copy(_FIX / "eval_trace_monitor.json", mon / "eval_trace.json")
    (mon / "monitor.json").write_text("{}", encoding="utf-8")
    (root / "data" / "monitor").mkdir(parents=True)
    shutil.copy(_FIX / "fund_flow_series.json",
                root / "data" / "monitor" / "fund_flow_series.json")


def test_read_monitor_health_flags_stale_board_pe(tmp_path):
    _stage_monitor(tmp_path, "2026-07-07")
    digest = notify_health.read_monitor_health(tmp_path, date(2026, 7, 7), set())
    codes = {i.code for i in digest.items}
    assert "board_pe_stale" in codes
    assert "flow_symbol_stale" in codes  # 688072 @ 2026-06-26


def test_read_monitor_health_corrupt_trace_is_unknown(tmp_path):
    mon = tmp_path / "outputs" / "2026-07-07" / "monitor"
    mon.mkdir(parents=True)
    (mon / "eval_trace.json").write_text("{bad json", encoding="utf-8")
    digest = notify_health.read_monitor_health(tmp_path, date(2026, 7, 7), set())
    assert digest.items[0].code == "health_unknown"


def test_read_weekly_health_flags_dxy(tmp_path):
    out = tmp_path / "outputs" / "2026-07-07"
    out.mkdir(parents=True)
    shutil.copy(_FIX / "gold_regime.json", out / "gold_regime.json")
    digest = notify_health.read_weekly_health(tmp_path, date(2026, 7, 7))
    assert any("DXY" in i.text and "滞后 21d" in i.text for i in digest.items)


def _stage_radar(root: Path, day: str, fixture: str) -> None:
    rot = root / "outputs" / day / "rotation"
    rot.mkdir(parents=True)
    shutil.copy(_FIX / fixture, rot / "rotation_radar.json")


def test_read_flow_capture_abstain_returns_warn(tmp_path):
    _stage_radar(tmp_path, "2026-07-07", "rotation_radar_abstain.json")
    digest, force = notify_health.read_flow_capture(tmp_path, date(2026, 7, 7))
    assert digest.has_warnings is True and force is False
    assert digest.items[0].code == "rotation_abstain"


def test_read_flow_capture_recovery_forces_notify(tmp_path):
    _stage_radar(tmp_path, "2026-07-06", "rotation_radar_abstain.json")
    _stage_radar(tmp_path, "2026-07-07", "rotation_radar_ok.json")
    digest, force = notify_health.read_flow_capture(tmp_path, date(2026, 7, 7))
    assert force is True
    assert digest.items[0].code == "rotation_recovered"


def test_flow_capture_outcome_missing_radar_is_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 7))
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="flow-capture", last_exit_code=0)
    assert outcome.today_dir_exists is False  # no rotation_radar.json ⇒ crash sentinel
    decision = __import__("irc.notify.classify", fromlist=["classify_run_outcome"]).classify_run_outcome(outcome)
    assert decision.severity == "failed"


def test_build_outcome_monitor_attaches_health(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 7))
    _stage_monitor(tmp_path, "2026-07-07")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    assert outcome.health is not None
    assert any(i.code == "board_pe_stale" for i in outcome.health.items)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/commands/test_notify_cmd.py -v -k "monitor_health or weekly_health or flow_capture or attaches_health"`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.commands.notify_health'`.

- [ ] **Step 3: Create `notify_health.py`**

Create `src/irc/commands/notify_health.py`:
```python
"""EDGE: read on-disk artifacts and hand parsed dicts to the pure
`irc.notify.health` builders. All filesystem effects for the data-health
digest live here; the builders stay pure (ADR 0016 amendment)."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.notify.calendar import recent_trading_days
from irc.notify.health import (
    HealthDigest,
    HealthItem,
    detect_rotation_recovery,
    monitor_health,
    rotation_health,
    weekly_health,
)

_log = logging.getLogger(__name__)
_RECENT_RADAR_DAYS = 5
_TRADING_DAY_LOOKBACK = 5


def _read_json(path: Path) -> dict | None:
    """Best-effort JSON read. Missing/unparseable/non-object → None (never raises)."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        _log.warning("data-health: could not read %s", path.name)
        return None
    return data if isinstance(data, dict) else None


def read_monitor_health(root: Path, today: date, holidays: set[date]) -> HealthDigest:
    out = root / "outputs" / today.isoformat()
    trace = _read_json(out / "monitor" / "eval_trace.json") or {}
    flow = _read_json(root / "data" / "monitor" / "fund_flow_series.json") or {}
    tdays = recent_trading_days(today, holidays, _TRADING_DAY_LOOKBACK)
    return monitor_health(trace, flow, tdays)


def read_weekly_health(root: Path, today: date) -> HealthDigest:
    gold = _read_json(root / "outputs" / today.isoformat() / "gold_regime.json") or {}
    return weekly_health(gold, today)


def _recent_rotation_statuses(root: Path, today: date) -> tuple[str, ...]:
    outputs = root / "outputs"
    if not outputs.exists():
        return ()
    dated: list[tuple[str, str]] = []
    for radar in outputs.glob("*/rotation/rotation_radar.json"):
        day = radar.parent.parent.name
        if day > today.isoformat():
            continue
        data = _read_json(radar) or {}
        dated.append((day, str(data.get("data_status", "unknown"))))
    dated.sort(key=lambda pair: pair[0])
    return tuple(status for _, status in dated[-_RECENT_RADAR_DAYS:])


def read_flow_capture(root: Path, today: date) -> tuple[HealthDigest, bool]:
    """Return (digest, force_notify). abstain→ok recovery ⇒ info digest + force."""
    radar = _read_json(root / "outputs" / today.isoformat() / "rotation" / "rotation_radar.json") or {}
    recent = _recent_rotation_statuses(root, today)
    recovery = detect_rotation_recovery(recent, len(radar.get("board_states", [])))
    if recovery is not None:
        return HealthDigest((HealthItem("rotation_recovered", "info", recovery),)), True
    return rotation_health(radar, recent), False
```

- [ ] **Step 4: Wire `notify_cmd.py`**

Edit `src/irc/commands/notify_cmd.py`:

Add imports (after existing `from irc.notify...` block):
```python
import dataclasses

from irc.commands.notify_health import (
    read_flow_capture,
    read_monitor_health,
    read_weekly_health,
)
```

Replace the whole `_build_outcome` function with:
```python
def _build_outcome(root: Path, *, run_kind: str, last_exit_code: int) -> RunOutcome:
    """Gather today's on-disk artifacts into a frozen RunOutcome (no fallback)."""
    today = _china_today()
    out_dir = root / "outputs" / today.isoformat()
    if run_kind == "flow-capture":
        return _flow_capture_outcome(root, today, last_exit_code)
    if run_kind == "monitor":
        sentinel = out_dir / "monitor" / "monitor.json"
        return RunOutcome(
            run_kind=run_kind,
            last_exit_code=last_exit_code,
            today_dir_exists=sentinel.exists(),
            pipeline_halted=False,
            stale_ingest=False,
            actionable_buy_count=0,
            trim_count=0,
            exit_count=0,
            review_count=0,
            health=read_monitor_health(root, today, _load_holidays(root)),
        )
    if not out_dir.exists():
        return RunOutcome(
            run_kind=run_kind,
            last_exit_code=last_exit_code,
            today_dir_exists=False,
            pipeline_halted=False,
            stale_ingest=False,
            actionable_buy_count=0,
            trim_count=0,
            exit_count=0,
            review_count=0,
        )
    summary = _read_summary(out_dir / "decision_report.json")
    unreadable = summary is None
    safe = summary if summary is not None else {}
    outcome = RunOutcome(
        run_kind=run_kind,
        last_exit_code=last_exit_code,
        today_dir_exists=True,
        pipeline_halted=(out_dir / "PIPELINE_HALTED.md").exists(),
        stale_ingest=(out_dir / "STALE_INGEST.md").exists(),
        actionable_buy_count=int(safe.get("actionable_buy_count", 0) or 0),
        trim_count=safe.get("trim_count"),
        exit_count=safe.get("exit_count"),
        review_count=safe.get("review_count"),
        decision_report_unreadable=unreadable,
        promotion_count=_coerce_count(safe.get("promotion_count")),
        promotion_ids=_coerce_ids(safe.get("promotion_ids")),
    )
    if run_kind == "weekly":
        return dataclasses.replace(outcome, health=read_weekly_health(root, today))
    return outcome


def _flow_capture_outcome(root: Path, today: date, last_exit_code: int) -> RunOutcome:
    """Flow-capture: severity is health-driven (abstain/degraded → degraded); a
    rotation crash surfaces as `failed` via the missing radar sentinel. Sell-side
    counts are 0 (not None) so a clean base never reads as 'sell-side UNKNOWN'."""
    sentinel = root / "outputs" / today.isoformat() / "rotation" / "rotation_radar.json"
    digest, force = read_flow_capture(root, today)
    return RunOutcome(
        run_kind="flow-capture",
        last_exit_code=last_exit_code,
        today_dir_exists=sentinel.exists(),
        pipeline_halted=False,
        stale_ingest=False,
        actionable_buy_count=0,
        trim_count=0,
        exit_count=0,
        review_count=0,
        health=digest,
        force_notify=force,
    )
```

- [ ] **Step 5: Add the `flow-capture` CLI choice**

Edit `src/irc/cli.py` — the `--run-kind` option:
```python
    type=click.Choice(["daily", "weekly", "monitor", "flow-capture"]),
```

- [ ] **Step 6: Run the edge tests (per-file — NEVER whole tests/commands/)**

Run: `uv run pytest tests/commands/test_notify_cmd.py -v`
Expected: PASS (all — new edge tests + every pre-existing test).

- [ ] **Step 7: CLI smoke — the new run-kind is accepted**

Run:
```bash
uv run irc notify-status --run-kind flow-capture --last-exit-code 0 --help >/dev/null && echo "choice-ok"
```
Expected: `choice-ok` (no "invalid choice" error).

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/irc/commands/notify_health.py src/irc/commands/notify_cmd.py src/irc/cli.py tests/commands/test_notify_cmd.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add src/irc/commands/notify_health.py src/irc/commands/notify_cmd.py \
        src/irc/cli.py tests/commands/test_notify_cmd.py
git commit -m "feat(notify): edge health reads + flow-capture run-kind"
```

---

## Task 5: `run-flow-capture.sh` notify tail + wrapper test

**Files:**
- Modify: `ops/launchd/run-flow-capture.sh`
- Create: `tests/ops/test_launchd_flow_capture.py`

**Interfaces:**
- Consumes: the `flow-capture` run-kind (Task 4).
- Produces: a best-effort notify tail identical in posture to `run-monitor.sh` but with `--no-notify-on-clean` hardcoded.

- [ ] **Step 1: Write the failing wrapper test**

Create `tests/ops/test_launchd_flow_capture.py`:
```python
"""AC6/§3.4: run-flow-capture.sh gains a best-effort notify tail with the
flow-capture run-kind, --no-notify-on-clean, and the authoritative $rc."""
from __future__ import annotations

import subprocess
from pathlib import Path

_WRAPPER = Path(__file__).parents[2] / "ops" / "launchd" / "run-flow-capture.sh"


def test_wrapper_calls_notify_flow_capture_silent_on_clean():
    text = _WRAPPER.read_text(encoding="utf-8")
    assert '"$UV_BIN" run irc notify-status --run-kind flow-capture' in text
    assert "--no-notify-on-clean" in text
    assert '--last-exit-code "$rc"' in text


def test_wrapper_notify_tail_after_rotation_and_before_exit():
    lines = _WRAPPER.read_text(encoding="utf-8").splitlines()
    notify_idx = next(i for i, ln in enumerate(lines) if "notify-status --run-kind flow-capture" in ln)
    rotation_idx = next(i for i, ln in enumerate(lines) if "irc rotation" in ln and "run_with_watchdog" in ln)
    exit_idx = next(i for i, ln in enumerate(lines) if ln.strip() == 'exit "$rc"')
    assert rotation_idx < notify_idx < exit_idx


def test_wrapper_notify_failure_does_not_abort():
    # Mirror run-monitor.sh: the tail must be `|| echo ...`, never bare, so a
    # notifier failure cannot abort the wrapper under set -e.
    text = _WRAPPER.read_text(encoding="utf-8")
    assert "|| echo" in text
    assert "notify-status failed" in text


def test_wrapper_passes_bash_syntax_check():
    result = subprocess.run(["bash", "-n", str(_WRAPPER)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ops/test_launchd_flow_capture.py -v`
Expected: FAIL — the notify line is absent from the wrapper.

- [ ] **Step 3: Edit the wrapper**

Edit `ops/launchd/run-flow-capture.sh`:

Update the header comment (line ~3) — replace `Protective-only (a timeout does NOT page — capture is best-effort; the` / `12:15 brief already ran).` with:
```bash
# Best-effort data-health notify tail (ADR 0016 amendment): silent on a fully-ok
# chain, pages on rotation abstain/degradation, a capture failure, or a one-time
# abstain→ok recovery. A capture timeout (rc=124) now pages `failed` — a stale
# tomorrow-flow is exactly what that surfaces. StandardOut/ErrPath are /dev/null.
```

Insert BEFORE the final `exit "$rc"` line:
```bash
# Data-health notification (best-effort): pass the flow-capture $rc (authoritative);
# a rotation crash is caught via the missing today's rotation_radar.json sentinel.
# --no-notify-on-clean: a fully-ok 15:45 chain stays silent (no page). `|| echo`
# (not `|| true`) keeps a notifier failure from aborting under set -e while leaving
# a log breadcrumb — never a page.
"$UV_BIN" run irc notify-status --run-kind flow-capture --last-exit-code "$rc" \
  --no-notify-on-clean \
  || echo "[$TODAY] notify-status failed (rc=$?) — flow-capture rc was $rc (see above)"

```

- [ ] **Step 4: Run the wrapper tests + the pre-existing shell-syntax test**

Run:
```bash
uv run pytest tests/ops/test_launchd_flow_capture.py -v
bash tests/ops/test_flow_capture_wrapper.sh
```
Expected: pytest PASS; the shell test prints `PASS: AC10 wrapper chaining`.

- [ ] **Step 5: Confirm the run-monitor assertion suite still holds (the flow-capture wrapper is also checked there)**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -v -k flow_capture`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ops/launchd/run-flow-capture.sh tests/ops/test_launchd_flow_capture.py
git commit -m "feat(ops): flow-capture notify tail (silent-on-ok, page-on-degradation)"
```

---

## Task 6: ADR 0016 amendment + AC6 doc syncs + CHANGELOG + TODOS

**Files:**
- Modify: `docs/adr/0016-local-scheduling-and-notification.md`
- Modify: `ops/launchd/README.md`
- Modify: `docs/monitor/README.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `TODOS.md`

(No tests — verify via grep at the end.)

- [ ] **Step 1: ADR 0016 amendment**

Edit `docs/adr/0016-local-scheduling-and-notification.md` — append a new decision subsection after "### 6. Trading-day awareness…" and before "## Consequences":
```markdown
### 7. Data-health digest + `degraded` severity + `flow-capture` run-kind (amendment 2026-07-07)

The classifier gains a `degraded` severity between `stale` and `action`:
precedence is now `failed > halted > stale > degraded > action > clean`, and
`degraded ∈ _ALWAYS_NOTIFY` (it fires even under `IRC_NOTIFY_ON_CLEAN=0` —
without that, a clean run hiding a DARK board-PE leg would stay invisible, which
is the exact bug this closes). A new pure module `src/irc/notify/health.py`
derives a **data-health digest** (see CONTEXT.md) from already-written artifacts
at the notify edge — never persisted, never an input to factor math. The digest
lines are appended to the body of every severity (a `failed` run still shows what
was already degraded); a `clean`/`action` base with any `warn` item escalates to
`degraded`. A new `flow-capture` run-kind covers the 15:45 chain: it is
silent-on-ok (`--no-notify-on-clean` hardcoded in the wrapper), pages on rotation
`abstain`/`degraded_*`, and fires a one-time recovery notice on the abstain→ok
transition (`force_notify` clean). The flow-capture wrapper passes the
authoritative flow-capture `$rc`, so a capture timeout (rc=124) now pages
`failed` — superseding the wrapper's former "a timeout does NOT page" note.
```

- [ ] **Step 2: `ops/launchd/README.md` schedule row**

Edit `ops/launchd/README.md` line 9 (the `com.irc.flow-capture` row) — replace `best-effort — no notification;` with:
```
best-effort **data-health notify** (`notify-status --run-kind flow-capture --no-notify-on-clean`): silent on a fully-ok chain, pages on rotation abstain/degradation or a capture failure, fires a one-time abstain→ok recovery notice; a capture timeout (rc=124) pages `failed`;
```
Also edit the timeout table (around line 65-69) — add a row:
```markdown
| `run-flow-capture.sh` | `IRC_FLOW_CAPTURE_TIMEOUT` (300s) | `rc=124` → `notify-status --run-kind flow-capture` pages **`failed`** (a stale tomorrow-flow) |
```

- [ ] **Step 3: `docs/monitor/README.md` daily-ops row**

Edit `docs/monitor/README.md` line 44 (the `15:45 daily` row) — append to the end of the cell (before the closing `|`):
```
 **Data-health notify (2026-07-07):** the 15:45 job now ends with a best-effort `notify-status --run-kind flow-capture --no-notify-on-clean` — silent when the chain is fully ok, pages on rotation `abstain`/`degraded_*` (with a `连续第 N 日` counter) or a capture failure, and fires a one-time `轮动雷达恢复 ok` notice on the abstain→ok transition.
```

- [ ] **Step 4: root `README.md` launchd row**

Edit `README.md` line 248 (the `com.irc.flow-capture` row) — replace `(best-effort, no page)` with:
```
(best-effort; data-health notify: silent-on-ok, pages on rotation abstain/degradation, one-time abstain→ok recovery notice)
```

- [ ] **Step 5: CHANGELOG `[Unreleased]`**

Edit `CHANGELOG.md` — add under `## [Unreleased]`, a new `### Added` block ABOVE the existing `### Fixed` (create the `### Added` header if absent):
```markdown
### Added

- **Data-health notifications (workflow-review item 001)**: `irc notify-status`
  now surfaces data degradation for all three scheduled surfaces. A new pure
  `src/irc/notify/health.py` derives a **data-health digest** (board-PE
  DARK/STALE, flow recency + per-symbol staleness, per-fund signal status,
  rotation `abstain`/`degraded_*`, macro-driver age > 7d, `drivers_unavailable`)
  from already-written artifacts at the notify edge — never persisted. A new
  `degraded` severity (`failed > halted > stale > degraded > action > clean`,
  always-notify) tags a run whose data is untrustworthy. New `flow-capture`
  run-kind wires the 15:45 chain: silent-on-ok, pages on rotation abstain, one-
  time abstain→ok recovery notice. Notification-layer only — no report/schema/
  engine change. ADR 0016 amended (§7).
```

- [ ] **Step 6: TODOS deferrals (spec §10.8)**

Edit `TODOS.md` — under the `## Reliability` section, append:
```markdown
- [ ] **Data-health digest trend-persistence (deferred — G-Q7)** — the digest is
  notification-only (no `data_health.json`); Feishu history is the "what was I told
  on day Y" record. *Pick up:* when a health-trend eval is wanted (e.g. "was flow
  DARK ≥3 of the last 5 days") — would need a small state file. (item 001, 2026-07-07)
- [ ] **Monitor DARK→FRESH recovery-notice generalization (deferred — G-Q3)** — the
  one-time abstain→ok recovery notice exists only for the 15:45 rotation surface;
  the 12:15 monitor board-PE has no DARK→FRESH recovery notice. *Pick up:* if
  board-plane flakiness persists after review M-3 lands. (item 001, 2026-07-07)
```

- [ ] **Step 7: Verify all doc edits landed**

Run:
```bash
grep -q "degraded" docs/adr/0016-local-scheduling-and-notification.md && echo "adr-ok"
grep -q "flow-capture --no-notify-on-clean" ops/launchd/README.md && echo "ops-ok"
grep -q "轮动雷达恢复 ok" docs/monitor/README.md && echo "monitor-ok"
grep -q "data-health notify" README.md && echo "readme-ok"
grep -q "Data-health notifications (workflow-review item 001)" CHANGELOG.md && echo "changelog-ok"
grep -q "trend-persistence (deferred — G-Q7)" TODOS.md && echo "todos-ok"
git diff --stat VERSION 2>/dev/null; test -z "$(git diff VERSION)" && echo "VERSION-unbumped-ok"
```
Expected: `adr-ok`, `ops-ok`, `monitor-ok`, `readme-ok`, `changelog-ok`, `todos-ok`, `VERSION-unbumped-ok`.

- [ ] **Step 8: Commit**

```bash
git add docs/adr/0016-local-scheduling-and-notification.md ops/launchd/README.md \
        docs/monitor/README.md README.md CHANGELOG.md TODOS.md
git commit -m "docs(notify): ADR 0016 amendment + data-health doc syncs + TODOS"
```

---

## Task 7: Runtime proof (AC1–AC5 against real / staged artifacts)

**Files:** none (verification only). Capture each rendered severity + body as evidence.

**Interfaces:** consumes the full built feature. Uses `_build_outcome` + `classify_run_outcome` directly to render the body WITHOUT dispatching a real macOS/Feishu notification.

- [ ] **Step 1: AC1 — monitor, real 2026-07-07 artifacts (severity `degraded`, STALE-1 info + flow warn)**

Run (against the real repo root — today is 2026-07-07):
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run python -c "
from pathlib import Path
from irc.commands.notify_cmd import _build_outcome
from irc.notify.classify import classify_run_outcome
o = _build_outcome(Path('.'), run_kind='monitor', last_exit_code=0)
d = classify_run_outcome(o)
print('SEVERITY', d.severity)
print('BODY', d.body)
"
```
Expected: `SEVERITY degraded`; BODY contains `板块PE: STALE-1 (2026-07-06)` AND `资金流:` … `滞后>3td(最旧 2026-06-26)`.
**Note (AC1 reconciliation):** severity is `degraded`, not `clean`, because G-Q5's per-symbol rule fires on the real 688072 @ 2026-06-26. This honors the locked §9 decision; see "AC1 severity reconciliation" in Global Constraints. The board-PE STALE-1 line is `info` as AC1 requires.

- [ ] **Step 2: AC4 — board-PE DARK escalates even with `IRC_NOTIFY_ON_CLEAN=0`**

```bash
uv run python -c "
from pathlib import Path
import tempfile, shutil, json, os
from datetime import date
from irc.commands import notify_cmd
from irc.notify.classify import classify_run_outcome
root = Path(tempfile.mkdtemp())
mon = root / 'outputs' / '2026-07-07' / 'monitor'; mon.mkdir(parents=True)
t = json.load(open('tests/notify/fixtures/eval_trace_monitor.json'))
t['board_pe_freshness'] = {'state':'DARK','as_of':'2026-07-01','age_td':4}
json.dump(t, open(mon/'eval_trace.json','w'))
(mon/'monitor.json').write_text('{}')
(root/'data'/'monitor').mkdir(parents=True)
shutil.copy('tests/notify/fixtures/fund_flow_series.json', root/'data'/'monitor'/'fund_flow_series.json')
notify_cmd._china_today = lambda: date(2026,7,7)
o = notify_cmd._build_outcome(root, run_kind='monitor', last_exit_code=0)
d = classify_run_outcome(o, notify_on_clean=False)
print('SEVERITY', d.severity, 'NOTIFY', d.should_notify)
print('BODY', d.body)
"
```
Expected: `SEVERITY degraded NOTIFY True`; BODY contains `板块PE: DARK`.

- [ ] **Step 3: AC2 — flow-capture abstain (degraded + 弃权), ok-after-ok (silent), ok-after-abstain (recovery once)**

```bash
uv run python -c "
from pathlib import Path
import tempfile, shutil
from datetime import date
from irc.commands import notify_cmd
from irc.notify.classify import classify_run_outcome

def stage(day, fixture, root):
    rot = root / 'outputs' / day / 'rotation'; rot.mkdir(parents=True)
    shutil.copy(f'tests/notify/fixtures/{fixture}', rot/'rotation_radar.json')

# (a) abstain today
r = Path(tempfile.mkdtemp()); stage('2026-07-07','rotation_radar_abstain.json', r)
notify_cmd._china_today = lambda: date(2026,7,7)
d = classify_run_outcome(notify_cmd._build_outcome(r, run_kind='flow-capture', last_exit_code=0), notify_on_clean=False)
print('ABSTAIN', d.severity, d.should_notify, '弃权' in d.body)

# (b) ok today, ok yesterday → silent
r = Path(tempfile.mkdtemp()); stage('2026-07-06','rotation_radar_ok.json', r); stage('2026-07-07','rotation_radar_ok.json', r)
d = classify_run_outcome(notify_cmd._build_outcome(r, run_kind='flow-capture', last_exit_code=0), notify_on_clean=False)
print('OK_AFTER_OK', d.severity, d.should_notify)

# (c) ok today, abstain yesterday → recovery once
r = Path(tempfile.mkdtemp()); stage('2026-07-06','rotation_radar_abstain.json', r); stage('2026-07-07','rotation_radar_ok.json', r)
d = classify_run_outcome(notify_cmd._build_outcome(r, run_kind='flow-capture', last_exit_code=0), notify_on_clean=False)
print('OK_AFTER_ABSTAIN', d.severity, d.should_notify, '恢复' in d.body)
"
```
Expected:
`ABSTAIN degraded True True`
`OK_AFTER_OK clean False`
`OK_AFTER_ABSTAIN clean True True`

- [ ] **Step 4: AC3 — weekly, real 07-04 gold_regime (DXY 滞后 21d)**

```bash
uv run python -c "
from pathlib import Path
import tempfile, shutil
from datetime import date
from irc.commands import notify_cmd
from irc.notify.classify import classify_run_outcome
root = Path(tempfile.mkdtemp())
out = root/'outputs'/'2026-07-07'; out.mkdir(parents=True)
(out/'decision_report.json').write_text('{\"summary\": {\"actionable_buy_count\": 0, \"trim_count\": 0, \"exit_count\": 0, \"review_count\": 0}}')
shutil.copy('tests/notify/fixtures/gold_regime.json', out/'gold_regime.json')
notify_cmd._china_today = lambda: date(2026,7,7)
d = classify_run_outcome(notify_cmd._build_outcome(root, run_kind='weekly', last_exit_code=0))
print('SEVERITY', d.severity)
print('BODY', d.body)
"
```
Expected: `SEVERITY degraded`; BODY contains `DXY 滞后 21d (2026-06-16)` and `缺失驱动: etf_holdings_gld`.

- [ ] **Step 5: AC5 — corrupt eval_trace.json → `health unknown`, no crash**

```bash
uv run python -c "
from pathlib import Path
import tempfile
from datetime import date
from irc.commands import notify_cmd
from irc.notify.classify import classify_run_outcome
root = Path(tempfile.mkdtemp())
mon = root/'outputs'/'2026-07-07'/'monitor'; mon.mkdir(parents=True)
(mon/'eval_trace.json').write_text('{bad json')
(mon/'monitor.json').write_text('{}')
notify_cmd._china_today = lambda: date(2026,7,7)
d = classify_run_outcome(notify_cmd._build_outcome(root, run_kind='monitor', last_exit_code=0))
print('SEVERITY', d.severity)
print('BODY', d.body)
"
```
Expected: no traceback; BODY contains `health unknown` (the `health_unknown` line, which carries the literal AC5 string); `SEVERITY degraded` (a `warn` health_unknown escalates the clean base — the run rc is untouched, matching AC5's "no crash, no masking of the run rc").

- [ ] **Step 6: Full regression — notify + ops suites (per-file, never whole tests/commands/)**

Run:
```bash
uv run pytest tests/notify/ tests/commands/test_notify_cmd.py tests/ops/test_launchd_flow_capture.py tests/ops/test_launchd_monitor.py -v
uv run ruff check src tests
```
Expected: all PASS; ruff clean.

- [ ] **Step 7: Commit the evidence note (optional, if a proof log is captured)**

If you saved the AC1–AC5 captured output to `docs/2026-07-07-review-followup/items/001-runtime-proof.md`, commit it:
```bash
git add docs/2026-07-07-review-followup/items/001-runtime-proof.md
git commit -m "docs(001): data-health runtime proof AC1-AC5"
```
(If no separate proof file, skip — the ship step re-runs these captures.)

---

## Self-Review (author checklist — completed)

**Spec coverage:** §3.1 health.py builders → Tasks 1–2; §3.2 classifier `degraded` → Task 3; §3.3 edge reads → Task 4; §3.4 flow-capture run-kind + wrapper + recovery → Tasks 4–5; §3.5 noise policy (no state file) → implicit (nothing to build; `连续第 N 日` counter is in `rotation_health`); §5 AC1–AC6 → Task 7 (AC1–AC5) + Task 6 (AC6); §6 test plan → Tasks 1–5 test steps; §7 forward-compat → no code (documented in ADR); §10 constraints → Global Constraints + per-task per-file pytest.

**Placeholder scan:** none — every code/test/doc step carries literal content.

**Type consistency:** `HealthItem(code, level, text)` / `HealthDigest(items).has_warnings` / `monitor_health(trace, flow_store, trading_days)` / `rotation_health(radar, recent_statuses)` / `detect_rotation_recovery(recent_statuses, board_count)` / `weekly_health(gold_regime, today)` / `read_monitor_health(root, today, holidays)` / `read_weekly_health(root, today)` / `read_flow_capture(root, today)` — used identically across Tasks 1→7. `RunOutcome.health` / `.force_notify` names consistent Task 3→4→7.

**Known reconciliations flagged inline:** field name `signal.status` (not `raw_status`); AC1 severity `degraded` (not `clean`) under G-Q5.
