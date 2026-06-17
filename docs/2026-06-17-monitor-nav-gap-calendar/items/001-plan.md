# Calendar-grounded `nav_quality` NAV-gap check — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the calendar-day NAV-gap heuristic (PR #158) with a ground-truth check: a NAV gap caveats a fund only when it spans ≥2 *trading days the SSE was actually open*, sourced from a real CN trading calendar; the #158 heuristic survives as the degraded fallback when the calendar is unavailable.

**Architecture:** A new AkShare wrapper `fetch_trade_calendar` (the only new import site) and a thin caching edge `trading_calendar.load_trading_days(today)` provide a `frozenset[date] | None`. A new pure metric `trace._missing_trading_days` counts open trading dates strictly inside each recent inter-observation gap; `_nav` threads it into the trace as `missing_trading_days`. The pure `structural.nav_quality` gate WARNs on `missing_trading_days >= 2`, falling back to `max_gap_days > 8` only when the calendar is `None`. `monitor_cmd` loads the calendar once per run and passes it into both `build_eval_trace` call sites. Pure functions never do I/O (ADR 0017 §3.3); the calendar is passed as a parameter.

**Tech Stack:** Python 3.12, uv, pytest, AkShare (`tool_trade_date_hist_sina`), pandas, frozen dataclasses, atomic `.tmp → os.replace` writes via `irc.io_utils.atomic_write_text`.

---

## Context the engineer needs before starting

Read these first; they are the source of truth and the files you will touch:

- **Spec:** `docs/2026-06-17-monitor-nav-gap-calendar/items/001-spec.md` (the authority).
- **ADR 0017 §3.3** (`docs/adr/0017-monitor-evidence-isolation.md`): pure functions in `trace.py` / `structural.py` do **no I/O**; the calendar enters as a parameter.
- **ADR 0018 "D3"** (`docs/adr/0018-monitor-scoring-rationale-and-governance.md`, the last "Consequences" bullet, lines ~167–180): the PR #158 pragmatic fix this supersedes — you will update it in Task 7.
- **`src/irc/data/akshare_client.py`** — the AkShare boundary. `_ak_call(fn_name, **kwargs)` (lines 29–33) is the single indirection point all AkShare calls and their tests go through.
- **`src/irc/monitor/trading_calendar.py`** — NEW file you create (Task 2).
- **`src/irc/monitor/eval/trace.py`** — `_max_gap_days` (lines 43–54, `window=_RECENT_GAP_WINDOW` default), `_RECENT_GAP_WINDOW = 20` (line 40), `_nav` (lines 57–67), `_fund_entry` (lines 104–121), `build_eval_trace` (lines 124–134), `_SCHEMA_VERSION = "1"` (line 12).
- **`src/irc/monitor/eval/structural.py`** — `_WARN_GAP_DAYS = 8` (line 14), `nav_quality` (lines 68–85), `monitor_signal_health` (lines 88–99).
- **`src/irc/commands/monitor_cmd.py`** — `_compute_gates` (lines 378–416, call site line 393), `_write_eval_artifacts` (lines 419–449, call site line 426), `run_monitor` (lines 601–638).
- **`src/irc/io_utils.py`** — `atomic_write_text(path, content)` (lines 9–28): the existing atomic `.tmp → os.replace` helper. **Reuse it**; do not reinvent.

**Series shape (load-bearing):** A NAV series is `tuple[tuple[str, float], ...]`, date-ascending, dates ISO `YYYY-MM-DD` strings (`render_types.FundView.nav_series`, `fetch.NavFetchResult.acc_series`). `trace._parse(d)` (lines 28–32) parses an ISO string → `date | None`.

**Constants (do not duplicate; locate the existing definition):**
- `_RECENT_GAP_WINDOW = 20` — already in `trace.py:40`. **Retained**; role changes from holiday-dodging to relevance-scoping. Do **not** redefine.
- `_WARN_GAP_DAYS = 8` — already in `structural.py:14`. **Retained** as the fallback threshold. Do **not** redefine.
- `_MISSING_TRADING_WARN = 2` — **NEW**, you add it to `structural.py` (Task 5).

**TDD is mandatory** (CLAUDE.md "Conventions"): every step is RED (failing test) → GREEN (minimal impl) → verify → commit. Files <200 lines, functions <20 lines.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `src/irc/data/akshare_client.py` | Modify (append `fetch_trade_calendar`) | The ONLY new AkShare import site; SSE trade-date frame → ascending `tuple[date, ...]`. |
| `tests/data/test_akshare_client.py` | Modify (add tests) | Mocked-frame shape test + double-gated live test. |
| `src/irc/monitor/trading_calendar.py` | **Create** | Thin edge: `load_trading_days(today) -> frozenset[date] \| None`; cache `data/monitor/trade_calendar.json`; refetch once per calendar day; degrade to `None`. |
| `tests/monitor/test_trading_calendar.py` | **Create** | Mocked-I/O edge tests (cache hit / stale / missing / failure / atomic). |
| `src/irc/monitor/eval/trace.py` | Modify | `_missing_trading_days` pure metric; `_nav` gains `trading_days` param + `missing_trading_days` key; `_fund_entry`/`build_eval_trace` thread `trading_days`; bump `_SCHEMA_VERSION` "1"→"2". |
| `tests/monitor/eval/test_trace.py` | Modify | `_missing_trading_days` unit tests; nav-key-set + schema_version updates. |
| `src/irc/monitor/eval/structural.py` | Modify | Add `_MISSING_TRADING_WARN = 2`; `nav_quality` gains the `md` branch with `max_gap_days` fallback. |
| `tests/monitor/eval/test_structural.py` | Modify | `nav_quality` branch unit tests (no mocks). |
| `src/irc/commands/monitor_cmd.py` | Modify | Call `load_trading_days(date.today())` once in `run_monitor`; thread `trading_days` into `_compute_gates` + `_write_eval_artifacts` → both `build_eval_trace` calls. |
| `tests/monitor/test_acceptance_eval.py` | Modify | §6 acceptance: Spring-Festival fixture incl. day-after run → `missing_trading_days = 0` → `validated`. |
| `docs/adr/0018-monitor-scoring-rationale-and-governance.md` | Modify | Update D3 consequence bullet to point at this calendar-grounded successor. |

---

## Task 1: `fetch_trade_calendar` — AkShare SSE trade-date wrapper

**Files:**
- Modify: `src/irc/data/akshare_client.py` (append a new function at end of file, after line 621)
- Test: `tests/data/test_akshare_client.py`

`tool_trade_date_hist_sina()` is the AkShare SSE trade-date history call. It returns a DataFrame with a single `trade_date` column whose values are `datetime.date` objects (some AkShare versions return ISO strings). The wrapper must coerce both forms to `date`, sort ascending, and return a `tuple[date, ...]`. It routes through `_ak_call` so tests mock it the same way every other call is mocked.

- [ ] **Step 1: Write the failing mocked-frame test**

Add to `tests/data/test_akshare_client.py` (top-level, after the existing NAV tests):

```python
def test_fetch_trade_calendar_returns_sorted_date_tuple() -> None:
    import datetime as _dt
    # AkShare's tool_trade_date_hist_sina returns a single `trade_date` column;
    # provide it out of order and as date objects to prove we sort + coerce.
    fake = pd.DataFrame({"trade_date": [
        _dt.date(2026, 2, 17), _dt.date(2026, 2, 13), _dt.date(2026, 2, 16),
    ]})
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_trade_calendar()
    assert mocked.call_args[0][0] == "tool_trade_date_hist_sina"
    assert out == (_dt.date(2026, 2, 13), _dt.date(2026, 2, 16), _dt.date(2026, 2, 17))


def test_fetch_trade_calendar_coerces_iso_strings() -> None:
    import datetime as _dt
    fake = pd.DataFrame({"trade_date": ["2026-02-16", "2026-02-13"]})
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_trade_calendar()
    assert out == (_dt.date(2026, 2, 13), _dt.date(2026, 2, 16))
```

Add `fetch_trade_calendar` to the import block at the top of the test file (the `from irc.data.akshare_client import (...)` list).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_trade_calendar_returns_sorted_date_tuple tests/data/test_akshare_client.py::test_fetch_trade_calendar_coerces_iso_strings -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_trade_calendar'`.

- [ ] **Step 3: Implement `fetch_trade_calendar`**

Append to `src/irc/data/akshare_client.py`:

```python
def fetch_trade_calendar() -> tuple[date, ...]:
    """SSE trade-date history via AkShare ``tool_trade_date_hist_sina``.

    Returns the full list of Shanghai-exchange trading dates, sorted ascending,
    as a ``tuple[date, ...]``. The frame carries one ``trade_date`` column whose
    cells are ``datetime.date`` (newer AkShare) or ISO ``YYYY-MM-DD`` strings
    (older); both are coerced. This is the ONLY new AkShare import site for the
    monitor calendar (spec §3.1)."""
    df = _ak_call("tool_trade_date_hist_sina")
    parsed = pd.to_datetime(df["trade_date"]).dt.date
    return tuple(sorted(parsed))
```

Add `from datetime import date` to the imports at the top of `akshare_client.py` (it is not currently imported — confirm and add it to the `from __future__ import annotations`-adjacent import block, e.g. after `import time`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_trade_calendar_returns_sorted_date_tuple tests/data/test_akshare_client.py::test_fetch_trade_calendar_coerces_iso_strings -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Add the double-gated live test**

Append to `tests/data/test_akshare_client.py`:

```python
@pytest.mark.live_akshare
@pytest.mark.skipif(
    _os_live.environ.get("IRC_RUN_LIVE_AKSHARE") != "1",
    reason="double-gated: set IRC_RUN_LIVE_AKSHARE=1 to hit AkShare",
)
def test_fetch_trade_calendar_live_is_sorted_and_contains_known_holidays() -> None:
    import datetime as _dt
    from irc.data.akshare_client import fetch_trade_calendar
    cal = fetch_trade_calendar()
    assert len(cal) > 1000
    assert list(cal) == sorted(cal)
    cal_set = set(cal)
    # 2026-02-16 is inside the CN Spring-Festival closure → not a trading day.
    assert _dt.date(2026, 2, 16) not in cal_set
```

(`pytest` and `_os_live` are already imported at the top of this test file — see lines 4 and 9.)

- [ ] **Step 6: Verify the live test is collected-but-skipped under the default run**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_trade_calendar_live_is_sorted_and_contains_known_holidays -v`
Expected: SKIPPED (reason "double-gated: set IRC_RUN_LIVE_AKSHARE=1 to hit AkShare").

- [ ] **Step 7: Commit**

```bash
git add src/irc/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(monitor): fetch_trade_calendar — SSE trade-date history via AkShare"
```

---

## Task 2: `trading_calendar.load_trading_days` — caching edge

**Files:**
- Create: `src/irc/monitor/trading_calendar.py`
- Test: `tests/monitor/test_trading_calendar.py`

This thin edge owns the cache at `data/monitor/trade_calendar.json` (shape `{"fetched_on": "<ISO>", "dates": ["<ISO>", ...]}`). It refetches via `fetch_trade_calendar` only when the cache is **missing** OR its `fetched_on < today` — at most once per calendar day (spec §3.1: avoids the weekend over-fetch a "max-date < today" trigger would cause). It persists atomically via `atomic_write_text`. On ANY fetch/parse/write failure it logs a warning and returns `None` (degrade, never crash). Returns `frozenset[date]` for O(1) membership.

- [ ] **Step 1: Write the failing edge tests**

Create `tests/monitor/test_trading_calendar.py`:

```python
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import irc.monitor.trading_calendar as tc


def _write_cache(root: Path, fetched_on: str, dates: list[str]) -> Path:
    p = root / "data" / "monitor" / "trade_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"fetched_on": fetched_on, "dates": dates}), encoding="utf-8")
    return p


def test_cache_hit_today_does_not_fetch(monkeypatch, tmp_path: Path):
    _write_cache(tmp_path, "2026-06-17", ["2026-02-13", "2026-02-17"])
    calls = []
    monkeypatch.setattr(tc, "fetch_trade_calendar", lambda: calls.append(1) or ())
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert calls == []                       # no network on same-day cache
    assert out == frozenset({_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)})


def test_stale_cache_refetches_and_persists(monkeypatch, tmp_path: Path):
    _write_cache(tmp_path, "2026-06-10", ["2026-02-13"])   # fetched_on < today
    monkeypatch.setattr(
        tc, "fetch_trade_calendar",
        lambda: (_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)),
    )
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out == frozenset({_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)})
    on_disk = json.loads(
        (tmp_path / "data" / "monitor" / "trade_calendar.json").read_text(encoding="utf-8"))
    assert on_disk["fetched_on"] == "2026-06-17"
    assert on_disk["dates"] == ["2026-02-13", "2026-02-17"]   # sorted ISO


def test_missing_cache_fetches_and_persists(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tc, "fetch_trade_calendar", lambda: (_dt.date(2026, 2, 13),))
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out == frozenset({_dt.date(2026, 2, 13)})
    assert (tmp_path / "data" / "monitor" / "trade_calendar.json").exists()


def test_fetch_failure_returns_none(monkeypatch, tmp_path: Path):
    def _boom():
        raise RuntimeError("akshare down")
    monkeypatch.setattr(tc, "fetch_trade_calendar", _boom)
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out is None


def test_corrupt_cache_refetches(monkeypatch, tmp_path: Path):
    p = tmp_path / "data" / "monitor" / "trade_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(tc, "fetch_trade_calendar", lambda: (_dt.date(2026, 2, 13),))
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out == frozenset({_dt.date(2026, 2, 13)})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/monitor/test_trading_calendar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.trading_calendar'`.

- [ ] **Step 3: Implement `trading_calendar.py`**

Create `src/irc/monitor/trading_calendar.py`:

```python
"""EDGE: cached CN (SSE) trading-calendar loader for the monitor nav_quality
gap check (spec §3.1). The ONLY monitor module besides akshare_client that
touches network/filesystem for the calendar. Degrades to None on any failure
so the pure gate can fall back to the calendar-day heuristic.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.data.akshare_client import fetch_trade_calendar
from irc.io_utils import atomic_write_text

_log = logging.getLogger(__name__)

_CACHE_REL = ("data", "monitor", "trade_calendar.json")


def _cache_path(root: Path) -> Path:
    return root.joinpath(*_CACHE_REL)


def _read_cache(path: Path, today: date) -> frozenset[date] | None:
    """Return cached trading days iff the cache is present AND fetched_on >= today.
    Returns None (→ caller refetches) on missing / stale / unparseable cache."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if date.fromisoformat(obj["fetched_on"]) < today:
            return None
        return frozenset(date.fromisoformat(d) for d in obj["dates"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _fetch_and_persist(path: Path, today: date) -> frozenset[date] | None:
    dates = sorted(fetch_trade_calendar())
    atomic_write_text(path, json.dumps(
        {"fetched_on": today.isoformat(), "dates": [d.isoformat() for d in dates]}))
    return frozenset(dates)


def load_trading_days(today: date, *, root: Path = Path(".")) -> frozenset[date] | None:
    """CN SSE trading days as a frozenset, cached at data/monitor/trade_calendar.json.
    Refetch only when the cache is missing or its fetched_on < today (once per
    calendar day; the calendar only appends at the tail). Returns None on any
    fetch/parse/write failure — the pure gate then falls back to max_gap_days."""
    path = _cache_path(root)
    cached = _read_cache(path, today)
    if cached is not None:
        return cached
    try:
        return _fetch_and_persist(path, today)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("load_trading_days failed: %s", exc, exc_info=True)
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/monitor/test_trading_calendar.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint the new module**

Run: `uv run ruff check src/irc/monitor/trading_calendar.py tests/monitor/test_trading_calendar.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/trading_calendar.py tests/monitor/test_trading_calendar.py
git commit -m "feat(monitor): trading_calendar.load_trading_days — once-per-day cached SSE calendar"
```

---

## Task 3: `_missing_trading_days` pure metric (trace.py)

**Files:**
- Modify: `src/irc/monitor/eval/trace.py` (add function after `_max_gap_days`, ~line 54)
- Test: `tests/monitor/eval/test_trace.py`

Pure, no I/O, no mocks. Over the last `window` observations, for each consecutive pair `(d0, d1)` count trading dates **strictly between** `d0` and `d1` (`{d ∈ trading_days : d0 < d < d1}`); return the max. Holidays/weekends aren't in `trading_days` → contribute 0. Returns `None` when `trading_days is None`. `< 2` parsed observations → `0`.

- [ ] **Step 1: Write the failing unit tests**

Add to `tests/monitor/eval/test_trace.py`. First extend the existing import on line 4 to include `_missing_trading_days`:

```python
from irc.monitor.eval.trace import (
    build_eval_trace, dedup_by_citation_id, _max_gap_days, _missing_trading_days,
)
```

Then add these tests:

```python
def _cn_cal(*iso: str):
    return frozenset(_dt.date.fromisoformat(d) for d in iso)


def test_missing_trading_days_none_calendar_returns_none():
    series = (("2026-06-15", 1.0), ("2026-06-16", 1.0))
    assert _missing_trading_days(series, None) is None


def test_missing_trading_days_fewer_than_two_obs_is_zero():
    assert _missing_trading_days((("2026-06-16", 1.0),), _cn_cal("2026-06-16")) == 0
    assert _missing_trading_days((), _cn_cal("2026-06-16")) == 0


def test_missing_trading_days_holiday_gap_counts_zero():
    # Series jumps across a closure; NONE of the in-between days are trading days,
    # so the fund missed zero open sessions.
    series = (("2026-02-13", 1.0), ("2026-02-23", 1.0))   # Spring-Festival hole
    cal = _cn_cal("2026-02-13", "2026-02-23")             # closure days absent
    assert _missing_trading_days(series, cal) == 0


def test_missing_trading_days_real_interior_miss_counts():
    # The fund skipped 2026-02-17 and 2026-02-18, both of which the market was open.
    series = (("2026-02-16", 1.0), ("2026-02-19", 1.0))
    cal = _cn_cal("2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19")
    assert _missing_trading_days(series, cal) == 2


def test_missing_trading_days_respects_recent_window():
    # An ancient outage (3 missed trading days) sits outside the recent window of
    # 20 obs and must be ignored; only the daily-cadence tail is scored.
    cal_days = [_dt.date(2026, 5, 1) + _dt.timedelta(days=i) for i in range(40)]
    cal = frozenset(cal_days)
    # obs 0 then a 4-day jump (3 interior trading days missed), then 25 daily obs.
    old = (("2026-05-01", 1.0), ("2026-05-05", 1.0))
    recent = tuple((d.isoformat(), 1.0) for d in cal_days[4:29])   # 25 consecutive
    assert _missing_trading_days(old + recent) == 0
```

Note the last test calls `_missing_trading_days(old + recent)` with the **default** `trading_days` — that is a deliberate type error to fix; rewrite it to pass `cal` explicitly:

```python
    assert _missing_trading_days(old + recent, cal) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_trace.py -k missing_trading_days -v`
Expected: FAIL — `ImportError: cannot import name '_missing_trading_days'`.

- [ ] **Step 3: Implement `_missing_trading_days`**

Insert into `src/irc/monitor/eval/trace.py` immediately after `_max_gap_days` (after line 54):

```python
def _missing_trading_days(
    series: tuple[tuple[str, float], ...],
    trading_days: frozenset[date] | None,
    *, window: int = _RECENT_GAP_WINDOW,
) -> int | None:
    """Max number of SSE-open trading dates strictly inside any recent
    inter-observation gap (spec §3.2). Holidays/weekends aren't in trading_days
    so a holiday gap scores 0. None when the calendar is unavailable (→ gate
    falls back to max_gap_days). <2 parsed observations → 0."""
    if trading_days is None:
        return None
    recent = series[-window:] if window else series
    dates = [d for d, _ in recent if (d := _parse(d)) is not None]
    if len(dates) < 2:
        return 0
    return max(
        sum(1 for td in trading_days if d0 < td < d1)
        for d0, d1 in zip(dates, dates[1:])
    )
```

Note the walrus reuse of `d` in the list comprehension shadows the loop variable — write it explicitly instead to keep it readable and lint-clean:

```python
    dates = [p for d, _ in recent if (p := _parse(d)) is not None]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_trace.py -k missing_trading_days -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/trace.py tests/monitor/eval/test_trace.py
git commit -m "feat(monitor): _missing_trading_days — calendar-grounded gap metric"
```

---

## Task 4: Thread `trading_days` through `_nav` / `build_eval_trace` + bump `schema_version`

**Files:**
- Modify: `src/irc/monitor/eval/trace.py` (`_nav` lines 57–67; `_fund_entry` lines 104–121; `build_eval_trace` lines 124–134; `_SCHEMA_VERSION` line 12)
- Test: `tests/monitor/eval/test_trace.py`

`build_eval_trace` gains a `trading_days: frozenset[date] | None = None` keyword (default `None` keeps every existing call site valid — they fall back to `max_gap_days`). It threads through `_fund_entry` → `_nav`, which adds the `missing_trading_days` key. Bump `_SCHEMA_VERSION` "1" → "2".

- [ ] **Step 1: Write the failing tests**

Update the nav-key-set assertion in `test_per_fund_schema_keys` (currently `test_trace.py:88-89`) to include the new key:

```python
    assert set(f["nav"]) == {"as_of_date", "latest_unit_nav", "nav_acc", "acc_series",
                             "obs_count", "max_gap_days", "missing_trading_days"}
```

Add a new test:

```python
def test_nav_missing_trading_days_threaded_from_calendar():
    cal = frozenset(_dt.date.fromisoformat(d) for d in
                    ("2026-06-15", "2026-06-16"))
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16", trading_days=cal)
    nav = t["funds"]["008986"]["nav"]
    # _good_view's series is consecutive trading days → no missed open sessions.
    assert nav["missing_trading_days"] == 0


def test_nav_missing_trading_days_is_none_without_calendar():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert t["funds"]["008986"]["nav"]["missing_trading_days"] is None


def test_schema_version_is_2():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert t["schema_version"] == "2"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_trace.py::test_nav_missing_trading_days_threaded_from_calendar tests/monitor/eval/test_trace.py::test_nav_missing_trading_days_is_none_without_calendar tests/monitor/eval/test_trace.py::test_schema_version_is_2 tests/monitor/eval/test_trace.py::test_per_fund_schema_keys -v`
Expected: FAIL — `build_eval_trace` has no `trading_days` kwarg; `missing_trading_days` key absent; `schema_version` is `"1"`.

- [ ] **Step 3: Bump the schema version**

In `src/irc/monitor/eval/trace.py` line 12:

```python
_SCHEMA_VERSION = "2"
```

- [ ] **Step 4: Thread `trading_days` through `_nav`**

Replace `_nav` (lines 57–67) with:

```python
def _nav(view: FundView, trading_days: frozenset[date] | None) -> dict:
    series = view.nav_series
    nav_acc = series[-1][1] if series else None
    return {
        "as_of_date": view.as_of_date,
        "latest_unit_nav": view.latest_nav,
        "nav_acc": nav_acc,
        "acc_series": [list(pt) for pt in series],
        "obs_count": len(series),
        "max_gap_days": _max_gap_days(series),
        "missing_trading_days": _missing_trading_days(series, trading_days),
    }
```

- [ ] **Step 5: Thread `trading_days` through `_fund_entry`**

In `_fund_entry` (lines 104–121), change the signature and the `_nav` call:

```python
def _fund_entry(fund: MonitorFund, view: FundView, gate: GateDecision,
                bundle: FundTraceBundle, trading_days: frozenset[date] | None) -> dict:
    return {
        "resolved": {"analysis_profile": fund.analysis_profile, "weights": dict(fund.weights),
                     "bands": dict(fund.bands), "minimum_confidence": fund.minimum_confidence},
        "nav": _nav(view, trading_days),
```

(leave the rest of the dict unchanged.)

- [ ] **Step 6: Thread `trading_days` through `build_eval_trace`**

Replace `build_eval_trace` (lines 124–134) with:

```python
def build_eval_trace(
    items: tuple[tuple[MonitorFund, FundView, GateDecision, FundTraceBundle], ...],
    *, engine_version: str, run_date: str,
    trading_days: frozenset[date] | None = None,
) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "engine_version": engine_version,
        "run_date": run_date,
        "funds": {fund.id: _fund_entry(fund, view, gate, bundle, trading_days)
                  for fund, view, gate, bundle in items},
    }
```

- [ ] **Step 7: Run the full trace test file**

Run: `uv run pytest tests/monitor/eval/test_trace.py -v`
Expected: PASS (all tests, including the unchanged `test_top_level_keys`, `test_degraded_nav_*`, `test_good_nav_fields_computed`). The default-`None` path keeps every existing call valid.

- [ ] **Step 8: Commit**

```bash
git add src/irc/monitor/eval/trace.py tests/monitor/eval/test_trace.py
git commit -m "feat(monitor): thread trading_days into eval_trace; bump schema_version 1->2"
```

---

## Task 5: `nav_quality` gate branch (structural.py)

**Files:**
- Modify: `src/irc/monitor/eval/structural.py` (add `_MISSING_TRADING_WARN` near line 14; `nav_quality` lines 68–85)
- Test: `tests/monitor/eval/test_structural.py`

The gap sub-status becomes: `md = nav["missing_trading_days"]`; if `md is not None` → WARN when `md >= _MISSING_TRADING_WARN` (=2), else PASS; if `md is None` → fall back to WARN when `max_gap_days > _WARN_GAP_DAYS` (the unchanged #158 path). The `obs<min`, missing-NAV, and `as_of older than stale_days` FAILs are **unchanged**.

- [ ] **Step 1: Write the failing tests**

Add to `tests/monitor/eval/test_structural.py`. The existing `_good_fund()` nav dict (lines 14–16) currently has no `missing_trading_days` key; tests that exercise the calendar branch set it explicitly.

```python
def test_nav_quality_warn_when_two_missing_trading_days():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = 2
    t["nav"]["max_gap_days"] = 3   # fallback would PASS — calendar branch must dominate
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_pass_when_one_missing_trading_day():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = 1
    t["nav"]["max_gap_days"] = 99  # fallback would WARN — calendar branch must dominate
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_pass_when_zero_missing_trading_days_over_holiday():
    # A Spring-Festival closure: big max_gap_days but zero missed open sessions.
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = 0
    t["nav"]["max_gap_days"] = 11
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_falls_back_to_max_gap_when_calendar_absent_warn():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = None
    t["nav"]["max_gap_days"] = 9   # > _WARN_GAP_DAYS=8 → WARN
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_falls_back_to_max_gap_when_calendar_absent_pass():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = None
    t["nav"]["max_gap_days"] = 7   # <= 8 → PASS
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"
```

The two pre-existing fallback tests (`test_nav_quality_pass_on_minor_holiday_gap`, `test_nav_quality_warn_on_single_gap_over_eight_days`, lines 103–116) do NOT set `missing_trading_days`. Because `_good_fund()`'s nav dict omits the key, `nav.get("missing_trading_days")` returns `None`, so they correctly exercise the fallback path and stay green **without edits** — leave them as-is.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_structural.py -k "missing_trading or falls_back" -v`
Expected: FAIL — the new branch doesn't exist; e.g. `test_nav_quality_warn_when_two_missing_trading_days` returns PASS (current code only checks `max_gap_days`, which is 3 here).

- [ ] **Step 3: Add the constant**

In `src/irc/monitor/eval/structural.py`, after `_WARN_GAP_DAYS = 8` (line 14), add:

```python
# Calendar-grounded gap rule (spec §3.3): WARN only when the fund missed >=2
# consecutive SSE-open trading days (a single isolated miss is a transient
# publish/AkShare glitch, tolerated). _WARN_GAP_DAYS above survives only as the
# degraded fallback when the calendar is unavailable. See ADR 0018 D3.
_MISSING_TRADING_WARN = 2
```

- [ ] **Step 4: Implement the branch**

In `nav_quality` (lines 68–85), replace the final gap block (current lines 82–85):

```python
    gap = nav.get("max_gap_days")
    if gap is not None and gap > _WARN_GAP_DAYS:
        return StageHealth("nav_quality", "WARN", (f"gap {gap}d",))
    return StageHealth("nav_quality", "PASS", ())
```

with:

```python
    missing = nav.get("missing_trading_days")
    gap = nav.get("max_gap_days")
    if missing is not None:
        if missing >= _MISSING_TRADING_WARN:
            return StageHealth("nav_quality", "WARN", (f"missed {missing} trading days",))
        return StageHealth("nav_quality", "PASS", ())
    if gap is not None and gap > _WARN_GAP_DAYS:
        return StageHealth("nav_quality", "WARN", (f"gap {gap}d",))
    return StageHealth("nav_quality", "PASS", ())
```

- [ ] **Step 5: Run the full structural test file**

Run: `uv run pytest tests/monitor/eval/test_structural.py -v`
Expected: PASS (all tests — the new branch tests, the unchanged fallback tests, and the unchanged FAIL tests).

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/eval/structural.py tests/monitor/eval/test_structural.py
git commit -m "feat(monitor): nav_quality WARNs on >=2 missed trading days, max_gap fallback"
```

---

## Task 6: Thread the calendar through the edge (monitor_cmd.py)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`_compute_gates` 378–416; `_write_eval_artifacts` 419–449; `run_monitor` 601–638; imports near line 43)
- Test: `tests/monitor/test_acceptance_eval.py`

`run_monitor` calls `load_trading_days(date.today(), root=root)` **once per run** and passes the result into both `build_eval_trace` call sites. Both helpers gain a `trading_days` keyword.

- [ ] **Step 1: Write the failing edge test**

Add to `tests/monitor/test_acceptance_eval.py` (it already imports `monitor_cmd` and patches its edges via `_patch`). This test proves the calendar is threaded into the emitted trace:

```python
def test_trace_carries_missing_trading_days_from_calendar(monkeypatch, tmp_path: Path):
    import datetime as _dt
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    # _stale_view's series is ("2000-01-01"),("2000-01-02") — consecutive, both
    # in a calendar that lists them as trading days → missing_trading_days == 0.
    cal = frozenset({_dt.date(2000, 1, 1), _dt.date(2000, 1, 2)})
    monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda today, root: cal)
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    trace = json.loads(
        (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json")
        .read_text(encoding="utf-8"))
    assert trace["funds"]["008986"]["nav"]["missing_trading_days"] == 0
    assert trace["schema_version"] == "2"
```

(The existing `_stale_view` fund still gets `EVAL_GATED` from the `as_of older than stale_days` FAIL — that is orthogonal to the gap metric and the other tests in this file still cover it.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/monitor/test_acceptance_eval.py::test_trace_carries_missing_trading_days_from_calendar -v`
Expected: FAIL — `monitor_cmd` has no `load_trading_days` attribute to patch (AttributeError), or the trace lacks the threaded value.

- [ ] **Step 3: Import `load_trading_days` in monitor_cmd**

Add to the imports in `src/irc/commands/monitor_cmd.py` (near the other `irc.monitor.*` imports, e.g. after line 43 `from irc.monitor.eval.trace import build_eval_trace`):

```python
from irc.monitor.trading_calendar import load_trading_days
```

- [ ] **Step 4: Add `trading_days` to `_compute_gates`**

Change the `_compute_gates` signature (line 378–381) to accept `trading_days`, and pass it into its `build_eval_trace` call (line 393–396):

```python
def _compute_gates(
    funds: list[MonitorFund], views: list[FundView], bundles: list[FundTraceBundle],
    *, min_obs: int, suite_healths: tuple[StageHealth, ...],
    trading_days: frozenset[date] | None,
) -> tuple[tuple[GateDecision, ...], dict, dict]:
```

and the call inside the loop:

```python
        projection = build_eval_trace(
            ((fund, view, stub, bundle),), engine_version=_ENGINE_VERSION,
            run_date="", trading_days=trading_days,
        )["funds"][fund.id]
```

- [ ] **Step 5: Add `trading_days` to `_write_eval_artifacts`**

Change `_write_eval_artifacts` signature (line 419–422) and its `build_eval_trace` call (line 426–429):

```python
def _write_eval_artifacts(
    out: Path, root: Path, funds: list[MonitorFund], views: list[FundView],
    bundles: list[FundTraceBundle], gates: tuple[GateDecision, ...], *, run_date: str,
    trading_days: frozenset[date] | None,
) -> None:
```

and the call:

```python
        trace = build_eval_trace(
            tuple(zip(funds, views, gates, bundles)),
            engine_version=_ENGINE_VERSION, run_date=run_date, trading_days=trading_days,
        )
```

- [ ] **Step 6: Load the calendar once and pass it to both call sites in `run_monitor`**

In `run_monitor`, after the fund-processing loop and before `_compute_gates` (current lines 619–623), add the calendar load and thread it into both helpers:

```python
    now_dt = datetime.now(timezone(timedelta(hours=8)))
    trading_days = load_trading_days(date.today(), root=root)
    suite_healths, suite_rows = _suite_eval(root, _today, now_dt)
    gates, signal_healths, deterministic_healths = _compute_gates(
        list(funds), views, bundles,
        min_obs=cfg.history.minimum_observations, suite_healths=suite_healths,
        trading_days=trading_days)
```

and update the `_write_eval_artifacts` call (current line 629):

```python
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates,
                          run_date=_today, trading_days=trading_days)
```

(`date` is already imported at line 12; no new datetime import needed.)

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/monitor/test_acceptance_eval.py::test_trace_carries_missing_trading_days_from_calendar -v`
Expected: PASS.

- [ ] **Step 8: Run the whole acceptance_eval file to confirm no regression**

Run: `uv run pytest tests/monitor/test_acceptance_eval.py -v`
Expected: PASS (the new test plus the two pre-existing ones — `test_eval_trace_emitted_and_ledger_uses_coalesce_basis`, `test_stale_nav_fund_is_eval_gated_and_panel_names_it`). The pre-existing tests don't patch `load_trading_days`, so the real edge runs; in `tmp_path` there is no cache and `fetch_trade_calendar` will attempt a network call. **If those two tests now hit the network or fail**, add a default `monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda today, root: None)` inside the shared `_patch` helper (line 40–50) so every test in the file degrades to the fallback unless it overrides. Do this in the same commit.

- [ ] **Step 9: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/monitor/test_acceptance_eval.py
git commit -m "feat(monitor): load trading calendar once per run, thread into both trace call sites"
```

---

## Task 7: §6 Acceptance — Spring-Festival fixture, day-after run → validated

**Files:**
- Test: `tests/monitor/test_acceptance_eval.py` (add the §6 acceptance test)

This is the spec §6 acceptance: recompute the gate over a fixture NAV series spanning a Spring-Festival closure, including a run dated the **day after** the holiday (the residual the #158 heuristic couldn't close) → `missing_trading_days = 0` → `validated`. It exercises the pure stack end-to-end (`build_eval_trace` → `nav_quality`) with a realistic calendar, no mocks of the pure layer.

- [ ] **Step 1: Write the acceptance test**

Add to `tests/monitor/test_acceptance_eval.py` (top-of-file imports already cover `FundView`, `MonitorFund`, `SignalRecord`, `FactorContribution`, `NarrativeDoc`; add `from irc.monitor.eval.structural import nav_quality` and `from irc.monitor.eval.trace import build_eval_trace` and `from irc.monitor.eval.types import GateDecision`):

```python
def test_acceptance_spring_festival_run_day_after_holiday_validates():
    import datetime as _dt
    from irc.monitor.eval.structural import nav_quality
    from irc.monitor.eval.trace import build_eval_trace
    from irc.monitor.eval.types import GateDecision

    # CN Spring-Festival 2026: market closed 2026-02-16..2026-02-20 inclusive.
    # The fund publishes on every trading day around it; the run is dated
    # 2026-02-23 — the FIRST trading day AFTER the holiday (the #158 residual).
    closed = {_dt.date(2026, 2, d) for d in range(16, 21)}
    weekends = {_dt.date(2026, 2, 14), _dt.date(2026, 2, 15),
                _dt.date(2026, 2, 21), _dt.date(2026, 2, 22)}
    cal = frozenset(
        _dt.date(2026, 2, d) for d in range(2, 24)
    ) - closed - weekends
    # NAV series: trading days only, last point is the run date (day after holiday).
    series = tuple((d.isoformat(), 1.0) for d in sorted(cal))

    fund = _fund("008986")
    view = FundView(
        fund_id="008986", name_cn="测试", latest_nav=1.0, as_of_date="2026-02-23",
        nav_series=series, signal=_signal("008986"),
        narrative=NarrativeDoc("008986", (), (), (), "ok"), evidence_pool=(),
        return_table={}, factor_freshness={}, missing_factor_reasons=(), factor_scores=())
    stub = GateDecision("008986", False, (), "validated", "")
    projection = build_eval_trace(
        ((fund, view, stub, FundTraceBundle("008986", (), (), ())),),
        engine_version="1", run_date="2026-02-23", trading_days=cal,
    )["funds"]["008986"]

    assert projection["nav"]["missing_trading_days"] == 0
    # max_gap_days across the closure would be ~9 cal days → the #158 fallback
    # WOULD have WARNed; the calendar branch must validate instead.
    assert projection["nav"]["max_gap_days"] > 8
    health = nav_quality(projection, minimum_observations=2, stale_days=400,
                         today=_dt.date(2026, 2, 23))
    assert health.status == "PASS"
```

(`stale_days=400` and `today=2026-02-23` keep the as_of-staleness FAIL out of the picture so the test isolates the gap rule.)

- [ ] **Step 2: Run the acceptance test (expect it to PASS — Tasks 3–5 already built the behavior)**

Run: `uv run pytest tests/monitor/test_acceptance_eval.py::test_acceptance_spring_festival_run_day_after_holiday_validates -v`
Expected: PASS. (If it fails, the bug is in Task 3/5 — fix there, not here.)

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_acceptance_eval.py
git commit -m "test(monitor): §6 acceptance — day-after-Spring-Festival run validates"
```

---

## Task 8: Update ADR 0018 "D3"

**Files:**
- Modify: `docs/adr/0018-monitor-scoring-rationale-and-governance.md` (the last "Consequences" bullet, ~lines 167–180)

D3 currently documents the PR #158 recent-window + `_WARN_GAP_DAYS=8` heuristic as the resolution. Update it to record that the heuristic is **superseded** by the calendar-grounded check (this item), retained only as the degraded fallback.

- [ ] **Step 1: Append the supersession note to the D3 bullet**

In the bullet beginning `**`nav_quality` gap rule is a recent-activity probe, not a full-history scan (D3).**` (line ~167), after the existing paragraph (which ends `…only fresh structural/LLM **FAIL**s suppress a bias.`), append:

```markdown

  **Superseded 2026-06-17 (calendar-grounded successor).** The two magic numbers
  above (`_RECENT_GAP_WINDOW`, `_WARN_GAP_DAYS`) *proxied* the holiday calendar
  rather than knowing it, and left a residual: a run in the ~4 weeks **after**
  Spring Festival / National Day still saw the big closure inside the window and
  WARNed. That residual is now **closed**. `trace._missing_trading_days` consults a
  real CN (SSE) trading calendar (`fetch_trade_calendar` → cached
  `data/monitor/trade_calendar.json` via `monitor/trading_calendar.load_trading_days`)
  and counts only *trading days the market was actually open* inside each recent
  gap; `structural.nav_quality` WARNs when `missing_trading_days >= _MISSING_TRADING_WARN = 2`.
  `_RECENT_GAP_WINDOW` (now relevance-scoping, not holiday-dodging) and the
  `_WARN_GAP_DAYS = 8` heuristic survive **only** as the degraded fallback when the
  calendar is unavailable (`missing_trading_days is None`), so #158 is not wasted.
  The gate stays fail-open. `eval_trace.json` gains `missing_trading_days`;
  `schema_version` bumped `"1"` → `"2"`. See
  `docs/2026-06-17-monitor-nav-gap-calendar/items/001-spec.md`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0018-monitor-scoring-rationale-and-governance.md
git commit -m "docs(adr-0018): D3 superseded by calendar-grounded nav-gap check"
```

---

## Verification points

- **After Task 3 (pure metric):** `uv run pytest tests/monitor/eval/test_trace.py -v` — all green, no network.
- **After Task 4 (threading + schema bump):** `uv run pytest tests/monitor/eval/test_trace.py -v` — confirms default-`None` keeps legacy call sites valid.
- **After Task 5 (gate branch):** `uv run pytest tests/monitor/eval/test_structural.py -v` — all green.
- **After Task 6 (edge):** `uv run pytest tests/monitor/test_acceptance_eval.py tests/commands/test_monitor_cmd.py -v` — the edge wiring and the existing run_monitor E2E tests stay green (these run the real edge; if any now reaches the network, apply the `_patch`/fixture default from Task 6 Step 8).
- **Full unit suite (no network), run after Task 6 and again after Task 8:**

  Run: `uv run pytest tests/monitor tests/data/test_akshare_client.py tests/commands/test_monitor_cmd.py tests/evals -v`
  Expected: all PASS or SKIPPED (the `live_akshare`/`live_llm` tests SKIP under default env). What "passing" looks like: zero failures, zero errors, the new tests listed as PASSED, the live tests as SKIPPED.

- **Lint, after the last code task:**

  Run: `uv run ruff check src tests`
  Expected: `All checks passed!`

---

## `schema_version` impact note (read before Task 4)

The eval-trace `schema_version` is currently `"1"` (`src/irc/monitor/eval/trace.py:12`, emitted at `:129`). It bumps to `"2"` in Task 4.

**No existing test asserts the *output* `schema_version` value equals `"1"`.** The places that mention it:

- `tests/monitor/eval/test_trace.py:76` (`test_top_level_keys`) asserts the **key set** `{"schema_version", "engine_version", "run_date", "funds"}`, not the value — stays green.
- `tests/evals/test_monitor_signal_runner.py:37`, `tests/evals/test_monitor_signal_metrics.py:30`, `tests/scripts/test_backfill_nav_history.py:9` each **construct** a fixture dict with `"schema_version": "1"` as **input** to the signal runner / metrics / backfill — those consumers do not validate the version, so the hardcoded `"1"` is inert and needs **no change**.

The only deliberate value assertion is the new `test_schema_version_is_2` you add in Task 4. The `schema_version: 1` integer literals in `config/monitor.yaml` and the `tests/.../test_resolve.py` / `test_monitor_cmd.py` / `test_config_loader_monitor.py` fixtures are the **config** schema_version (`irc.schemas.monitor.MonitorConfig`), a completely separate field — do **not** touch them.

---

## Self-review notes

- **Spec coverage:** §3.1 → Tasks 1+2; §3.2 → Tasks 3+4; §3.3 → Task 5; §3.4 threading → Task 6; §5 degrade (None → fallback) → Tasks 2/3/5 (None paths) + Task 6 Step 8; §6 acceptance → Task 7 + the live-gated test in Task 1 Step 5; §8 consequences (schema bump, ADR update) → Tasks 4 + 8.
- **Type consistency:** `trading_days: frozenset[date] | None` is identical across `_missing_trading_days`, `_nav`, `_fund_entry`, `build_eval_trace`, `_compute_gates`, `_write_eval_artifacts`, `load_trading_days`, and `fetch_trade_calendar -> tuple[date, ...]`. `missing_trading_days` is the single key name used in the trace, the gate, and all tests.
- **Judgment calls (flagged for the executor):**
  - The spec does not name the AkShare frame's exact column; this plan assumes a single `trade_date` column (the documented `tool_trade_date_hist_sina` shape) and coerces both `date` and ISO-string cells (Task 1). If the live test (Task 1 Step 5, opt-in) reveals a different column name, narrow the live finding into `fetch_trade_calendar` only — the mocked tests pin the contract.
  - The spec's §6 acceptance is specified as a gate recomputation, not necessarily a full `run_monitor`; this plan implements it as a pure `build_eval_trace → nav_quality` recompute (Task 7) for determinism, and separately proves edge threading in Task 6. Both together discharge §6 + §3.4.
  - Task 6 Step 8 flags a possible network reach in the two pre-existing `run_monitor` tests once the real `load_trading_days` is wired; the remediation (default-`None` patch in `_patch`) is specified inline so the executor doesn't have to improvise.

---

## Execution handoff

Plan complete and saved to `docs/2026-06-17-monitor-nav-gap-calendar/items/001-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session via executing-plans, batch execution with checkpoints.
