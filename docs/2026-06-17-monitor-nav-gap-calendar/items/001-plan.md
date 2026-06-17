# Monitor `nav_quality` — Calendar-Grounded NAV-Gap Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the PR #158 calendar-day NAV-gap heuristic with ground truth — a fund is caveated only when it missed CN trading days the market was actually open — while keeping the #158 heuristic intact as a degraded-mode fallback.

**Architecture:** A new edge fetches the SSE trading calendar (AkShare `tool_trade_date_hist_sina`) once per run, caches it under `data/monitor/trade_calendar.json`, and threads a `frozenset[date] | None` into the pure trace/structural layers. The pure metric `_missing_trading_days` counts trading dates strictly inside each NAV gap; the gate WARNs at `>= 2` missed open days, falling back to the unchanged `max_gap_days > 8` heuristic when the calendar is unavailable (`None`). Pure functions never do I/O (ADR 0017 §3.3); the new `trading_days` param defaults to `None` so every existing pure-test call site stays valid.

**Tech Stack:** Python 3.12+, uv, pandas, AkShare (`tool_trade_date_hist_sina`), pytest, frozen dataclasses, atomic `.tmp.{pid} → os.replace` writes (`irc.io_utils.atomic_write_text`).

---

## Context the implementer needs (read before starting)

- **Spec:** `docs/2026-06-17-monitor-nav-gap-calendar/items/001-spec.md` — the full contract (§3 Design, §6 Testing, §8 Consequences).
- **ADR 0017 §3.3** (`docs/adr/0017-monitor-evidence-isolation.md`): the monitor pure-types boundary — `trace.py` / `structural.py` import NO I/O (no AkShare/LLM/settings). The calendar arrives as a parameter.
- **ADR 0018 "D3"** (`docs/adr/0018-monitor-scoring-rationale-and-governance.md:167-180`): the PR #158 heuristic this supersedes, and the **fail-open** rule (WARN → `caveated`, never `EVAL_GATED`). This plan updates D3 to point at the calendar-grounded successor.
- **AkShare shape (verified):** `tool_trade_date_hist_sina()` takes **no args** and returns a `pd.DataFrame` with a single column `trade_date` of `datetime.date` objects, sorted ascending.
- **Test layout (verified):** tests live at `tests/monitor/eval/` and `tests/data/` (NOT `tests/irc/...`). Mirror those.
- **Atomic writer (verified):** `irc.io_utils.atomic_write_text(path: Path, content: str)` — uses `tempfile.mkstemp` + `os.replace` + dir fsync. Reuse it; do NOT hand-roll a temp file.
- **AkShare boundary pattern (verified):** all AkShare calls go through `_ak_call(fn_name, **kwargs)` in `src/irc/data/akshare_client.py` (a local-import indirection for testability). Tests mock `irc.data.akshare_client._ak_call`.
- **Engine version constant:** `_ENGINE_VERSION = "1"` in `monitor_cmd.py:63`; `_NAV_STALE_DAYS = 7` at line 64.

## File Structure

| File | Responsibility | Create/Modify |
|---|---|---|
| `src/irc/data/akshare_client.py` | `fetch_trade_calendar()` — wrap `tool_trade_date_hist_sina`, return sorted `tuple[date, ...]` | Modify |
| `src/irc/monitor/trading_calendar.py` | `load_trading_days(today)` — cache-or-fetch edge → `frozenset[date] | None` | **Create** |
| `src/irc/monitor/eval/trace.py` | `_missing_trading_days` pure metric; `missing_trading_days` nav key; `trading_days` param on `build_eval_trace`/`_nav`; `_SCHEMA_VERSION` bump | Modify |
| `src/irc/monitor/eval/structural.py` | `nav_quality` calendar branch; `_MISSING_TRADING_WARN = 2` | Modify |
| `src/irc/commands/monitor_cmd.py` | once-per-run `load_trading_days(date.today())`; thread `trading_days` into both `build_eval_trace` call sites | Modify |
| `docs/adr/0018-monitor-scoring-rationale-and-governance.md` | Update D3 to point at the calendar-grounded successor | Modify |
| `tests/data/test_akshare_client.py` | `fetch_trade_calendar` shape/parse test (mocked `_ak_call`) | Modify |
| `tests/monitor/test_trading_calendar.py` | `load_trading_days` cache/fetch/degrade/atomic tests | **Create** |
| `tests/monitor/eval/test_trace.py` | `_missing_trading_days` pure tests; schema key + default-None tests | Modify |
| `tests/monitor/eval/test_structural.py` | `nav_quality` calendar-branch + fallback tests | Modify |

> **Note on `tests/monitor/test_trading_calendar.py`:** `trading_calendar.py` lives at `src/irc/monitor/` (not under `eval/`), so its test mirrors to `tests/monitor/` (not `tests/monitor/eval/`). Confirm `tests/monitor/__init__.py` exists before creating (it does — sibling test files import from there).

---

## Task 1: `fetch_trade_calendar` AkShare edge

**Files:**
- Modify: `src/irc/data/akshare_client.py` (add new function near the other `fetch_*` functions, e.g. after `fetch_fund_nav_history` ~line 148)
- Test: `tests/data/test_akshare_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/data/test_akshare_client.py`. First extend the import block at the top (lines 11-23) to include `fetch_trade_calendar`, and add `import datetime as _dt` near the other imports:

```python
import datetime as _dt
```

```python
def test_fetch_trade_calendar_returns_sorted_date_tuple() -> None:
    fake = pd.DataFrame({
        "trade_date": [_dt.date(2026, 2, 13), _dt.date(2026, 2, 12),
                       _dt.date(2026, 2, 17)],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_trade_calendar()

    assert mocked.call_args[0][0] == "tool_trade_date_hist_sina"
    assert out == (_dt.date(2026, 2, 12), _dt.date(2026, 2, 13), _dt.date(2026, 2, 17))
    assert all(isinstance(d, _dt.date) for d in out)


def test_fetch_trade_calendar_coerces_string_dates() -> None:
    # tool_trade_date_hist_sina normally yields datetime.date, but guard against a
    # frame whose column came back as ISO strings.
    fake = pd.DataFrame({"trade_date": ["2026-02-12", "2026-02-13"]})
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_trade_calendar()
    assert out == (_dt.date(2026, 2, 12), _dt.date(2026, 2, 13))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_trade_calendar_returns_sorted_date_tuple tests/data/test_akshare_client.py::test_fetch_trade_calendar_coerces_string_dates -q`
Expected: FAIL — `ImportError: cannot import name 'fetch_trade_calendar'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/irc/data/akshare_client.py`, after `fetch_fund_nav_history` (around line 148). Add `from datetime import date` to the imports if not present — note `datetime` is NOT currently imported in this module, so add the import line near the top (after `import time`, line 10):

```python
from datetime import date
```

Then the function:

```python
def fetch_trade_calendar() -> tuple[date, ...]:
    """SSE A-share trading-date history via AkShare ``tool_trade_date_hist_sina``.

    Returns trade dates sorted ascending as a ``tuple[date, ...]``. A single CN
    calendar is correct for the whole monitor set (incl. QDII) — see spec §2: CN
    QDII funds publish unit NAV on every CN trading day, not on foreign calendars.
    Pure-ish wrapper at the AkShare boundary; no other module imports AkShare for
    the calendar.
    """
    df = _ak_call("tool_trade_date_hist_sina")
    dates = pd.to_datetime(df["trade_date"]).dt.date
    return tuple(sorted(dates))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_trade_calendar_returns_sorted_date_tuple tests/data/test_akshare_client.py::test_fetch_trade_calendar_coerces_string_dates -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(monitor): fetch_trade_calendar AkShare edge for SSE trade dates"
```

---

## Task 2: `load_trading_days` cache-or-fetch edge

**Files:**
- Create: `src/irc/monitor/trading_calendar.py`
- Test: `tests/monitor/test_trading_calendar.py`

The cache file `data/monitor/trade_calendar.json` stores `{"fetched_on": "<ISO date>", "dates": ["<ISO date>", ...]}`. Refetch only when the cache is **missing** OR its `fetched_on < today` (at most once per calendar day). Any fetch/parse failure → log a warning → return `None`. The cache path is resolved relative to a `repo_root` so tests use `tmp_path`.

- [ ] **Step 1: Write the failing test — cache hit (no fetch)**

Create `tests/monitor/test_trading_calendar.py`:

```python
from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path
from unittest.mock import patch

from irc.monitor.trading_calendar import load_trading_days


_TODAY = _dt.date(2026, 6, 17)


def _write_cache(root: Path, fetched_on: str, dates: list[str]) -> Path:
    p = root / "data" / "monitor" / "trade_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"fetched_on": fetched_on, "dates": dates}))
    return p


def test_cache_hit_today_does_not_fetch(tmp_path: Path) -> None:
    _write_cache(tmp_path, _TODAY.isoformat(), ["2026-06-15", "2026-06-16"])
    with patch("irc.monitor.trading_calendar.fetch_trade_calendar") as mocked:
        out = load_trading_days(_TODAY, repo_root=tmp_path)
    mocked.assert_not_called()
    assert out == frozenset({_dt.date(2026, 6, 15), _dt.date(2026, 6, 16)})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_trading_calendar.py::test_cache_hit_today_does_not_fetch -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.trading_calendar'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/trading_calendar.py`:

```python
"""EDGE: load the CN SSE trading calendar for the monitor nav-gap check.

Caches under data/monitor/trade_calendar.json; refetches at most once per calendar
day. Degrades to None on any fetch/parse failure so the pure gate can fall back to
the PR #158 calendar-day heuristic (spec §5). ADR 0017 §3.3: this is the ONLY
monitor module besides akshare_client that touches network/filesystem for the
calendar; the pure layers receive its frozenset result as a parameter.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.data.akshare_client import fetch_trade_calendar
from irc.io_utils import atomic_write_text

_log = logging.getLogger(__name__)

_CACHE_REL = Path("data") / "monitor" / "trade_calendar.json"


def _cache_path(repo_root: Path) -> Path:
    return repo_root / _CACHE_REL


def _read_cache(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_fresh(cache: dict, today: date) -> bool:
    try:
        return date.fromisoformat(str(cache["fetched_on"])) >= today
    except (KeyError, ValueError, TypeError):
        return False


def _parse_dates(cache: dict) -> frozenset[date]:
    return frozenset(date.fromisoformat(d) for d in cache["dates"])


def _refetch(path: Path, today: date) -> frozenset[date]:
    dates = fetch_trade_calendar()
    payload = {"fetched_on": today.isoformat(), "dates": [d.isoformat() for d in dates]}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False))
    return frozenset(dates)


def load_trading_days(today: date, *, repo_root: Path) -> frozenset[date] | None:
    """Return CN trading dates as a frozenset, or None if unavailable (degrade).

    Cache hit (fetched_on >= today) → parse and return. Otherwise refetch via
    AkShare, persist atomically, and return. On any failure → log + return None.
    """
    path = _cache_path(repo_root)
    cache = _read_cache(path)
    try:
        if cache is not None and _is_fresh(cache, today):
            return _parse_dates(cache)
        return _refetch(path, today)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("load_trading_days failed: %r", exc, exc_info=True)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_trading_calendar.py::test_cache_hit_today_does_not_fetch -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Write the remaining edge tests**

Append to `tests/monitor/test_trading_calendar.py`:

```python
def test_stale_cache_refetches_and_persists(tmp_path: Path) -> None:
    _write_cache(tmp_path, "2026-06-16", ["2026-06-10"])  # fetched_on < today
    fresh = (_dt.date(2026, 6, 16), _dt.date(2026, 6, 17))
    with patch("irc.monitor.trading_calendar.fetch_trade_calendar", return_value=fresh) as m:
        out = load_trading_days(_TODAY, repo_root=tmp_path)
    m.assert_called_once()
    assert out == frozenset(fresh)
    persisted = json.loads((tmp_path / "data" / "monitor" / "trade_calendar.json").read_text())
    assert persisted == {"fetched_on": "2026-06-17",
                         "dates": ["2026-06-16", "2026-06-17"]}


def test_missing_cache_fetches_and_persists(tmp_path: Path) -> None:
    fresh = (_dt.date(2026, 6, 17),)
    with patch("irc.monitor.trading_calendar.fetch_trade_calendar", return_value=fresh) as m:
        out = load_trading_days(_TODAY, repo_root=tmp_path)
    m.assert_called_once()
    assert out == frozenset(fresh)
    assert (tmp_path / "data" / "monitor" / "trade_calendar.json").exists()


def test_fetch_failure_returns_none_and_warns(tmp_path: Path, caplog) -> None:
    with patch("irc.monitor.trading_calendar.fetch_trade_calendar",
               side_effect=RuntimeError("boom")):
        out = load_trading_days(_TODAY, repo_root=tmp_path)
    assert out is None
    assert any("load_trading_days failed" in r.message for r in caplog.records)


def test_corrupt_cache_refetches(tmp_path: Path) -> None:
    p = tmp_path / "data" / "monitor" / "trade_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    fresh = (_dt.date(2026, 6, 17),)
    with patch("irc.monitor.trading_calendar.fetch_trade_calendar", return_value=fresh) as m:
        out = load_trading_days(_TODAY, repo_root=tmp_path)
    m.assert_called_once()
    assert out == frozenset(fresh)
```

- [ ] **Step 6: Run all trading_calendar tests**

Run: `uv run pytest tests/monitor/test_trading_calendar.py -q`
Expected: PASS (5 passed). The `side_effect=RuntimeError` case proves degrade-to-None; the corrupt-cache case proves `_read_cache` returning `None` triggers a refetch (not a crash).

- [ ] **Step 7: Commit**

```bash
git add src/irc/monitor/trading_calendar.py tests/monitor/test_trading_calendar.py
git commit -m "feat(monitor): load_trading_days cached SSE-calendar edge (degrade to None)"
```

---

## Task 3: `_missing_trading_days` pure metric + `missing_trading_days` nav key + schema bump

**Files:**
- Modify: `src/irc/monitor/eval/trace.py` (`_missing_trading_days` near `_max_gap_days` ~line 43; `_nav` ~line 57; `build_eval_trace` ~line 124; `_SCHEMA_VERSION` line 12)
- Test: `tests/monitor/eval/test_trace.py`

`_missing_trading_days(series, trading_days, *, window=_RECENT_GAP_WINDOW)`: over the last `window` observations, for each consecutive pair `(d0, d1)` count `{d in trading_days : d0 < d < d1}`; return the max. Returns `None` when `trading_days is None`; returns `0` for `< 2` observations.

- [ ] **Step 1: Write the failing pure-metric tests**

Add to `tests/monitor/eval/test_trace.py`. First extend the import on line 4 to add `_missing_trading_days`:

```python
from irc.monitor.eval.trace import (
    build_eval_trace, dedup_by_citation_id, _max_gap_days, _missing_trading_days,
)
```

Then the tests:

```python
def _trading_set(start: _dt.date, n: int):
    # n consecutive CALENDAR days, weekdays only counted as trading days.
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += _dt.timedelta(days=1)
    return frozenset(out)


def test_missing_trading_days_none_when_calendar_unavailable():
    series = (("2026-06-15", 1.0), ("2026-06-16", 1.0))
    assert _missing_trading_days(series, None) is None


def test_missing_trading_days_zero_for_under_two_obs():
    assert _missing_trading_days((("2026-06-16", 1.0),), frozenset()) == 0
    assert _missing_trading_days((), frozenset()) == 0


def test_missing_trading_days_holiday_gap_counts_zero():
    # NAV present 2026-02-13 (Fri) then 2026-02-17 (next trading Mon after a holiday
    # block); the in-between dates are NOT in the trading calendar → 0 missed.
    series = (("2026-02-13", 1.0), ("2026-02-17", 1.0))
    trading = frozenset({_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)})
    assert _missing_trading_days(series, trading) == 0


def test_missing_trading_days_counts_real_interior_miss():
    # Market open Mon-Fri; fund skipped Wed+Thu (2 trading days the market ran).
    series = (("2026-06-15", 1.0), ("2026-06-18", 1.0))  # Mon → Thu
    trading = _trading_set(_dt.date(2026, 6, 15), 6)  # Mon..next-Mon weekdays
    assert _missing_trading_days(series, trading) == 2  # Tue(16)+Wed(17) strictly between


def test_missing_trading_days_respects_recent_window():
    # An ancient interior miss falls outside the last `window` observations and is
    # ignored; only the recent cadence is measured.
    old = (("2021-03-01", 1.0), ("2021-03-31", 1.0))  # huge ancient gap
    base = _dt.date(2026, 5, 4)  # a Monday
    recent = tuple(
        (d.isoformat(), 1.0) for d in sorted(_trading_set(base, 25))
    )
    trading = _trading_set(_dt.date(2021, 3, 1), 0) | _trading_set(base, 25) | frozenset(
        {_dt.date(2021, 3, 1), _dt.date(2021, 3, 31)})
    assert _missing_trading_days(old + recent, trading, window=20) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_trace.py -k missing_trading_days -q`
Expected: FAIL — `ImportError: cannot import name '_missing_trading_days'`.

- [ ] **Step 3: Write `_missing_trading_days`**

Add to `src/irc/monitor/eval/trace.py` immediately after `_max_gap_days` (after line 54):

```python
def _missing_trading_days(
    series: tuple[tuple[str, float], ...],
    trading_days: frozenset[date] | None,
    *, window: int = _RECENT_GAP_WINDOW,
) -> int | None:
    """Max count of OPEN trading days a fund went dark over consecutive NAV pairs,
    scoped to the most recent `window` observations.

    Holidays/weekends are not in `trading_days` → contribute 0, so the big CN
    closures never WARN. Returns None when the calendar is unavailable (gate falls
    back to max_gap_days); 0 for <2 observations. Spec §3.2.
    """
    if trading_days is None:
        return None
    recent = series[-window:] if window else series
    if len(recent) < 2:
        return 0
    missed: list[int] = []
    for (d0, _), (d1, _) in zip(recent, recent[1:]):
        a, b = _parse(d0), _parse(d1)
        if a is not None and b is not None:
            missed.append(sum(1 for d in trading_days if a < d < b))
    return max(missed) if missed else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_trace.py -k missing_trading_days -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Write the failing nav-key + schema tests**

Add to `tests/monitor/eval/test_trace.py`:

```python
def test_nav_dict_has_missing_trading_days_key():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    nav = t["funds"]["008986"]["nav"]
    assert "missing_trading_days" in nav


def test_build_eval_trace_default_trading_days_none_yields_none_metric():
    # Default (no trading_days passed) → missing_trading_days is None → gate falls back.
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert t["funds"]["008986"]["nav"]["missing_trading_days"] is None


def test_build_eval_trace_threads_trading_days_into_metric():
    # Two adjacent trading days, no interior miss → 0 (not None).
    trading = frozenset({_dt.date(2026, 6, 15), _dt.date(2026, 6, 16)})
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16", trading_days=trading)
    assert t["funds"]["008986"]["nav"]["missing_trading_days"] == 0


def test_schema_version_is_two():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert t["schema_version"] == "2"
```

Also UPDATE the existing `test_per_fund_schema_keys` assertion (line 88-89) to include the new key:

```python
    assert set(f["nav"]) == {"as_of_date", "latest_unit_nav", "nav_acc", "acc_series",
                             "obs_count", "max_gap_days", "missing_trading_days"}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_trace.py::test_nav_dict_has_missing_trading_days_key tests/monitor/eval/test_trace.py::test_build_eval_trace_default_trading_days_none_yields_none_metric tests/monitor/eval/test_trace.py::test_build_eval_trace_threads_trading_days_into_metric tests/monitor/eval/test_trace.py::test_schema_version_is_two tests/monitor/eval/test_trace.py::test_per_fund_schema_keys -q`
Expected: FAIL — `missing_trading_days` not in nav dict; `schema_version` is `"1"`; `build_eval_trace` has no `trading_days` kwarg (`TypeError`).

- [ ] **Step 7: Thread `trading_days` through `_nav` and `build_eval_trace`; bump schema**

In `src/irc/monitor/eval/trace.py`:

(a) Bump the schema version (line 12):

```python
_SCHEMA_VERSION = "2"
```

(b) Change `_nav` (lines 57-67) to accept and use `trading_days`:

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

(c) Change `_fund_entry` (lines 104-121) to accept and forward `trading_days`. Update the signature and the `_nav` call:

```python
def _fund_entry(fund: MonitorFund, view: FundView, gate: GateDecision,
                bundle: FundTraceBundle, trading_days: frozenset[date] | None) -> dict:
    return {
        "resolved": {"analysis_profile": fund.analysis_profile, "weights": dict(fund.weights),
                     "bands": dict(fund.bands), "minimum_confidence": fund.minimum_confidence},
        "nav": _nav(view, trading_days),
        "evidence_pool": dedup_by_citation_id(view.evidence_pool + bundle.constituent_pool),
        "factor_scores": [{"name": s.name, "value": s.value, "eligible": s.eligible,
                           "reason": s.reason, "confidence": s.confidence}
                          for s in view.factor_scores],
        "signal": _signal(view.signal),
        "impacts": _impacts(bundle),
        "narrative": _narrative(view.narrative),
        "gate": {"suppressed": gate.suppressed, "failed_stages": list(gate.failed_stages),
                 "reason": gate.reason},
        "published_state": published_state(view.signal, gate),
        "validation_badge": gate.badge,
    }
```

(d) Change `build_eval_trace` (lines 124-134) to add the `trading_days` param (default `None`) and forward it:

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

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_trace.py -q`
Expected: PASS (all trace tests, including the updated `test_per_fund_schema_keys` and the 4 new ones). The `default trading_days=None` test confirms every existing pure-test call site (which omits the kwarg) still gets a valid `None` metric.

- [ ] **Step 9: Commit**

```bash
git add src/irc/monitor/eval/trace.py tests/monitor/eval/test_trace.py
git commit -m "feat(monitor): _missing_trading_days metric + trading_days thread + schema v2"
```

---

## Task 4: `nav_quality` calendar branch + `_MISSING_TRADING_WARN`

**Files:**
- Modify: `src/irc/monitor/eval/structural.py` (`nav_quality` lines 68-85; add `_MISSING_TRADING_WARN` near `_WARN_GAP_DAYS` line 14)
- Test: `tests/monitor/eval/test_structural.py`

Gate logic (spec §3.3): read `md = nav["missing_trading_days"]`. If `md is not None` → WARN when `md >= _MISSING_TRADING_WARN` (`= 2`), else PASS. If `md is None` → fall back to the unchanged `max_gap_days > _WARN_GAP_DAYS` heuristic. FAILs (`obs<min`, missing NAV, stale) unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/monitor/eval/test_structural.py`. The `_good_fund()` helper's nav dict (line 14-16) does NOT yet carry `missing_trading_days`; `nav.get("missing_trading_days")` returns `None` for the existing tests, which is exactly the fallback path — so the existing `max_gap_days` tests (lines 103-116) keep passing unchanged. New tests set the key explicitly:

```python
def test_nav_quality_warn_when_two_trading_days_missed():
    # Calendar available, fund went dark for 2 OPEN trading days → WARN (caveated).
    t = _good_fund()
    t["nav"]["missing_trading_days"] = 2
    t["nav"]["max_gap_days"] = 3            # below the fallback threshold, ignored
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_pass_when_one_trading_day_missed():
    # A single isolated missed open day is tolerated (transient publish glitch).
    t = _good_fund()
    t["nav"]["missing_trading_days"] = 1
    t["nav"]["max_gap_days"] = 30           # would WARN under fallback, but ignored
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_pass_when_zero_trading_days_missed_over_holiday():
    # The residual the heuristic could not close: a run the day after Spring Festival.
    # The 11-day calendar-day gap would WARN under fallback; calendar says 0 missed.
    t = _good_fund()
    t["nav"]["missing_trading_days"] = 0
    t["nav"]["max_gap_days"] = 11
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_falls_back_to_gap_heuristic_when_calendar_none():
    # Calendar unavailable (md is None) → PR #158 heuristic: gap>8 WARNs.
    t = _good_fund()
    t["nav"]["missing_trading_days"] = None
    t["nav"]["max_gap_days"] = 9
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_fallback_passes_minor_gap_when_calendar_none():
    t = _good_fund()
    t["nav"]["missing_trading_days"] = None
    t["nav"]["max_gap_days"] = 7            # ≤ _WARN_GAP_DAYS
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_calendar_warn_does_not_override_fail():
    # FAILs (stale/obs/missing) still win over the calendar WARN.
    t = _good_fund()
    t["nav"]["missing_trading_days"] = 5
    t["nav"]["as_of_date"] = "2000-01-01"   # stale → FAIL
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "FAIL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_structural.py -k "two_trading_days or one_trading_day or zero_trading_days or falls_back or fallback_passes or calendar_warn" -q`
Expected: FAIL — the calendar branch does not exist yet, so e.g. `missing_trading_days = 2` still routes through `max_gap_days` (`3 > 8` is False → PASS, not WARN).

- [ ] **Step 3: Add the constant and the calendar branch**

In `src/irc/monitor/eval/structural.py`, add after `_WARN_GAP_DAYS` (line 14):

```python
# Calendar-grounded successor to the _WARN_GAP_DAYS heuristic (ADR 0018 D3, spec §3.3):
# WARN only when the fund missed >= this many OPEN trading days. Tolerates a single
# isolated missed day (transient publish/AkShare glitch); the only remaining threshold.
_MISSING_TRADING_WARN = 2
```

Then replace the gap block in `nav_quality` (current lines 82-85):

```python
    gap = nav.get("max_gap_days")
    if gap is not None and gap > _WARN_GAP_DAYS:
        return StageHealth("nav_quality", "WARN", (f"gap {gap}d",))
    return StageHealth("nav_quality", "PASS", ())
```

with:

```python
    missing = nav.get("missing_trading_days")
    if missing is not None:
        if missing >= _MISSING_TRADING_WARN:
            return StageHealth("nav_quality", "WARN", (f"missed {missing} trading days",))
        return StageHealth("nav_quality", "PASS", ())
    gap = nav.get("max_gap_days")
    if gap is not None and gap > _WARN_GAP_DAYS:
        return StageHealth("nav_quality", "WARN", (f"gap {gap}d",))
    return StageHealth("nav_quality", "PASS", ())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_structural.py -q`
Expected: PASS (all structural tests — the 6 new ones plus the unchanged `max_gap_days` fallback tests, which still pass because `_good_fund()` has no `missing_trading_days` key → `.get()` returns `None` → fallback path).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/structural.py tests/monitor/eval/test_structural.py
git commit -m "feat(monitor): nav_quality calendar branch (_MISSING_TRADING_WARN=2) + #158 fallback"
```

---

## Task 5: Thread `load_trading_days` through `monitor_cmd.py`

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (import ~line 43; `_compute_gates` 378-416; `_write_eval_artifacts` 419-450; `run_monitor` 601-638)

`run_monitor` already computes `_today` as an ISO string (line 604) and calls `_compute_gates` (621) then `_write_eval_artifacts` (629). Both call `build_eval_trace`. We compute the calendar **once** in `run_monitor` and pass it into both functions, which forward it to `build_eval_trace`.

This task has no new pure logic — it's edge wiring. Verify by an integration-style test that mocks `load_trading_days` and asserts `eval_trace.json` carries `missing_trading_days`. Check whether an existing `monitor_cmd` test harness exists first.

- [ ] **Step 1: Check for an existing monitor_cmd test to mirror**

Run: `ls tests/commands/test_monitor_cmd.py 2>/dev/null; grep -rln "run_monitor\|_compute_gates\|_write_eval_artifacts" tests/ | head`
Expected: note the path(s). If a `tests/commands/test_monitor_cmd.py` exists, add the wiring test there; otherwise the wiring is covered by the live acceptance run (Task 7) and you skip the unit test for this edge (it is pure plumbing; the pure metric and gate are already tested).

- [ ] **Step 2: Add the import**

In `src/irc/commands/monitor_cmd.py`, after the `from irc.monitor.eval.trace import build_eval_trace` line (line 43):

```python
from irc.monitor.trading_calendar import load_trading_days
```

- [ ] **Step 3: Thread `trading_days` into `_compute_gates`**

Change the `_compute_gates` signature (lines 378-381) to accept `trading_days`:

```python
def _compute_gates(
    funds: list[MonitorFund], views: list[FundView], bundles: list[FundTraceBundle],
    *, min_obs: int, suite_healths: tuple[StageHealth, ...],
    trading_days: frozenset[date] | None,
) -> tuple[tuple[GateDecision, ...], dict, dict]:
```

And forward it in the `build_eval_trace` call inside the loop (lines 393-396):

```python
        projection = build_eval_trace(
            ((fund, view, stub, bundle),), engine_version=_ENGINE_VERSION,
            run_date="", trading_days=trading_days,
        )["funds"][fund.id]
```

> Note: `date` is already imported at `monitor_cmd.py:12` (`from datetime import date, ...`), so the annotation needs no new import.

- [ ] **Step 4: Thread `trading_days` into `_write_eval_artifacts`**

Change the `_write_eval_artifacts` signature (lines 419-421) to accept `trading_days`:

```python
def _write_eval_artifacts(
    out: Path, root: Path, funds: list[MonitorFund], views: list[FundView],
    bundles: list[FundTraceBundle], gates: tuple[GateDecision, ...], *, run_date: str,
    trading_days: frozenset[date] | None,
) -> None:
```

And forward it in the `build_eval_trace` call (lines 426-429):

```python
        trace = build_eval_trace(
            tuple(zip(funds, views, gates, bundles)),
            engine_version=_ENGINE_VERSION, run_date=run_date, trading_days=trading_days,
        )
```

- [ ] **Step 5: Compute the calendar once in `run_monitor` and pass it to both**

In `run_monitor`, after `out.mkdir(...)` (line 628) and before `_compute_gates`/`_write_eval_artifacts`, load the calendar once. Insert right after the `cfg = load_monitor_config(root)` block region — specifically add the load just before the `_compute_gates` call (after line 620, `suite_healths, suite_rows = _suite_eval(...)`):

```python
    trading_days = load_trading_days(date.today(), repo_root=root)
```

Then update the two call sites:

`_compute_gates` (lines 621-623):

```python
    gates, signal_healths, deterministic_healths = _compute_gates(
        list(funds), views, bundles,
        min_obs=cfg.history.minimum_observations, suite_healths=suite_healths,
        trading_days=trading_days)
```

`_write_eval_artifacts` (line 629):

```python
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates,
                          run_date=_today, trading_days=trading_days)
```

- [ ] **Step 6: Add a wiring test (only if a monitor_cmd harness exists from Step 1)**

If `tests/commands/test_monitor_cmd.py` exists and has a runnable `run_monitor` fixture, add a test patching `irc.commands.monitor_cmd.load_trading_days` to return a known frozenset and asserting the written `eval_trace.json` funds carry an integer `missing_trading_days`. Mirror the existing harness exactly. If no such harness exists, skip — the metric/gate are unit-tested (Tasks 3-4) and the wiring is exercised by the live acceptance run (Task 7).

- [ ] **Step 7: Run the monitor command-layer tests (regression check)**

Run: `uv run pytest tests/commands/ tests/monitor/ -q`
Expected: PASS — no regression from the signature changes. Pay attention to any existing test that calls `_compute_gates` / `_write_eval_artifacts` directly; if one does, update its call to pass `trading_days=None` (the degrade default) and confirm it still passes.

- [ ] **Step 8: Commit**

```bash
git add src/irc/commands/monitor_cmd.py
# include tests/commands/test_monitor_cmd.py only if you edited it in Step 6
git commit -m "feat(monitor): thread once-per-run trading calendar into eval trace"
```

---

## Task 6: Update ADR 0018 "D3" to point at the calendar-grounded successor

**Files:**
- Modify: `docs/adr/0018-monitor-scoring-rationale-and-governance.md` (the D3 bullet, lines 167-180)

The D3 entry currently documents the PR #158 heuristic as the resolution. Append a paragraph recording that the heuristic is now the **fallback** and the calendar check is the primary path. Do NOT delete the existing #158 text — it documents the surviving fallback.

- [ ] **Step 1: Append the successor note to D3**

After the existing D3 bullet (currently ends at line 180 with "...suppress a bias."), add:

```markdown
  - **Superseded 2026-06-17 by a calendar-grounded check (spec
    `docs/2026-06-17-monitor-nav-gap-calendar/items/001-spec.md`).** The two magic
    numbers above (`_RECENT_GAP_WINDOW`, `_WARN_GAP_DAYS`) *proxied* for the holiday
    calendar; they could not close the residual where a run within ~4 weeks **after**
    Spring Festival / National Day still saw the big-holiday gap inside the window and
    WARNed. The primary path is now ground truth: `trace._missing_trading_days` counts
    the **open** CN trading days inside each NAV gap (a single SSE calendar via
    `akshare_client.fetch_trade_calendar`, cached at `data/monitor/trade_calendar.json`,
    correct for the whole set incl. QDII — they publish on CN trading days, spec §2),
    and `structural.nav_quality` WARNs at `_MISSING_TRADING_WARN = 2` missed open days.
    The `_RECENT_GAP_WINDOW`/`_WARN_GAP_DAYS` heuristic is **retained as the degraded
    fallback**: when the calendar is unavailable (`load_trading_days → None →
    missing_trading_days → None`), `nav_quality` reverts to `max_gap_days > _WARN_GAP_DAYS`
    exactly as before, so the brief never regresses. The gate stays **fail-open** (WARN →
    `caveated`, never `EVAL_GATED`). `eval_trace.json` `schema_version` bumped `1 → 2`
    (adds the `nav.missing_trading_days` key).
```

- [ ] **Step 2: Verify the doc renders and the spec path is correct**

Run: `grep -n "001-spec.md\|_MISSING_TRADING_WARN\|schema_version" docs/adr/0018-monitor-scoring-rationale-and-governance.md`
Expected: the new lines appear; the spec path matches `docs/2026-06-17-monitor-nav-gap-calendar/items/001-spec.md` (it exists).

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0018-monitor-scoring-rationale-and-governance.md
git commit -m "docs(adr-0018): D3 points at calendar-grounded nav-gap successor"
```

---

## Task 7: Full-suite regression + acceptance

**Files:** none (verification only)

- [ ] **Step 1: Lint**

Run: `uv run ruff check src tests`
Expected: no new findings in the touched files (line-length 100, py312). If a line exceeds 100 chars, wrap it; do not disable the rule.

- [ ] **Step 2: Run the full monitor + data + eval test surface**

Run: `uv run pytest tests/monitor/ tests/data/test_akshare_client.py tests/commands/ -q`
Expected: PASS. This covers `_missing_trading_days`, `nav_quality` (calendar + fallback), `load_trading_days`, `fetch_trade_calendar`, schema-v2, and the threaded call sites.

- [ ] **Step 3: Acceptance — Spring-Festival fixture passes (the residual the heuristic could not close)**

This is already asserted as a unit test (`test_nav_quality_pass_when_zero_trading_days_missed_over_holiday` in Task 4: an 11-day `max_gap_days` with `missing_trading_days = 0` → PASS). Confirm it green:

Run: `uv run pytest tests/monitor/eval/test_structural.py::test_nav_quality_pass_when_zero_trading_days_missed_over_holiday -q`
Expected: PASS.

- [ ] **Step 4: (Optional, opt-in live) regenerate today's brief**

Per spec §6 "Live (gated, opt-in)". Only if `MINIMAX_*` keys are configured and the operator opts in:

Run: `uv run irc monitor`
Expected: `outputs/<date>/monitor/eval_trace.json` exists with `"schema_version": "2"` and every fund's `nav.missing_trading_days` is an integer (0 for the holiday-spanning funds); `data/monitor/trade_calendar.json` written; `monitor_signal` panel PASS with all 10 funds `validated`. This step is NOT required for the plan to be considered complete — the unit + acceptance fixtures cover the contract offline.

- [ ] **Step 5: Final commit (only if any lint wrap was needed)**

```bash
git add -A
git commit -m "chore(monitor): lint wrap for nav-gap calendar change"
```

---

## Self-Review Checklist (completed by plan author)

**Spec coverage:**
- §3.1 `fetch_trade_calendar` → Task 1. `load_trading_days` (cache once/day, atomic persist, degrade→None) → Task 2.
- §3.2 `_missing_trading_days` (strictly-between count, window scoping, None on no-calendar, 0 on <2 obs), `missing_trading_days` nav key, `_RECENT_GAP_WINDOW` retained, `schema_version` bump → Task 3.
- §3.3 gate branch (`md>=_MISSING_TRADING_WARN` else fallback `max_gap_days>_WARN_GAP_DAYS`), `_MISSING_TRADING_WARN=2`, FAILs unchanged → Task 4.
- §3.4 `trading_days` param on `build_eval_trace` (default None), threaded through both `monitor_cmd` call sites, one `load_trading_days(today)` edge call → Tasks 3 (param) + 5 (wiring).
- §5 degrade contracts (calendar fail → None → fallback; pure functions never I/O) → Tasks 2 (degrade), 3+4 (params, not I/O).
- §6 testing (pure no-mock for metric/gate; mocked-I/O for `load_trading_days`/`fetch_trade_calendar`; Spring-Festival acceptance) → Tasks 1-4, 7.
- §8 consequences (schema bump, ADR 0018 D3 update) → Tasks 3, 6.

**Placeholder scan:** no TBD/TODO; every code/test step shows full bodies; commands have expected output.

**Type consistency:** `fetch_trade_calendar() -> tuple[date, ...]`; `load_trading_days(today, *, root) -> frozenset[date] | None` [AMENDED 2026-06-17: was `repo_root`; impl uses `root`]; `_missing_trading_days(series, trading_days, *, window) -> int | None`; `build_eval_trace(..., trading_days=None)`; nav key spelled `missing_trading_days` and constant `_MISSING_TRADING_WARN` consistently across Tasks 3-5. `_compute_gates` / `_write_eval_artifacts` both gain `trading_days: frozenset[date] | None` keyword-only.

**Judgment calls (flagged for reviewer):**
1. **`load_trading_days` takes an explicit root kwarg** (spec §3.1 shows `load_trading_days(today: date)`). The cache lives under `data/monitor/` which is repo-root-relative; `monitor_cmd` already threads `root: Path` everywhere and never relies on cwd, so passing the root explicitly keeps the edge pure of cwd assumptions and makes the cache test `tmp_path`-isolatable. The impl chose `root` (not `repo_root`) as the kwarg name — consistent with the existing `monitor_cmd` convention where the variable is always `root`. The edge call is `load_trading_days(date.today(), root=root)`. [AMENDED 2026-06-17: plan said `repo_root`; impl uses `root` — intent identical, name matches monitor_cmd convention.]
2. **`<2` observations returns `0`, not `None`** (spec §3.2 says "`< 2` observations → `0`"). Confirmed: `None` is reserved exclusively for "calendar unavailable" so the gate's fallback branch is unambiguous.
