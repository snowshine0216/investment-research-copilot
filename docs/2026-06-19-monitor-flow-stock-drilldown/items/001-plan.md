# Monitor per-stock valuation + capital-flow drill-down — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bullish-on-inflow `flow` factor (main-money net inflow over a fund's top-5 holdings) plus a per-stock PB/PE drill-down board to `irc monitor`, so each fund's directional bias is grounded bottom-up in valuation + capital flow.

**Architecture:** A new EDGE fetch (`flow_fetch.py`, mirrors `heat_fetch.py`'s never-raises/byte-stable-cache contract) + a new pure core (`holding_metrics.py`: per-stock valuation reusing the opportunity primitives, flow windows, weight-renormalized aggregate with a 0.50 coverage gate). The aggregate drives a 6th `flow` factor through the unchanged `compute_signal`, renders a drill-down board (card + standalone `drilldown.html`), and is isolated in the forward eval by an engine-version bump (`1`→`2`) paired with a `target_engine` population filter.

**Tech Stack:** Python 3.12, frozen dataclasses, DuckDB (cached reads only), AkShare (`ak.stock_individual_fund_flow`, edge-only), pytest (TDD red→green), ruff (line-length 100).

---

## Invariants every task must honor (spec §6, ADR 0017/0015/0019)

- **ADR 0017 evidence isolation:** flow data is the monitor's OWN cache `data/monitor/fund_flow/`; never read opportunity output files; pure cores take already-loaded inputs, effects only in `flow_fetch.py` + `commands/`.
- **New N/A reasons are non-caveating:** `flow_no_data`, `flow_no_coverage` are added to `KNOWN_NA_REASONS` → they never trip a WARN/FAIL and never caveat a fund (consistent with valuation/heat N/A).
- **No silent caps:** surface the coverage-floor N/A; never silently treat an uncovered holding as score 0.
- **Size budget:** new modules < 200 lines, functions < 20 lines. Extract helpers rather than nest > 3 levels. Do NOT inline flow-input assembly into `monitor_cmd.py` (already 672 lines) — it lives in `holding_metrics.py`.
- **ADR 0015 lean line:** the board uses lean language (偏多/偏空 / 估值 / 资金流). It MUST NOT emit imperative 买入/卖出, target weights, current-vs-target weight deltas, or any per-instrument action. "Add-bias = buy signal" means a better-*reasoned* lean, never an executable order.
- **Flow units are percent-points (D3/D7).** `12.34` means 12.34%. NO `/100` anywhere. Every band/threshold/test is in percent-points. The ratio-unit canary (`0.01`/`0.03`) must land in the deadband.
- **Versioning:** accumulate this feature under CHANGELOG `[Unreleased]` at the static VERSION. Do NOT bump the package VERSION. (The `_ENGINE_VERSION "1"→"2"` bump in `monitor_cmd.py` is the eval engine tag — that IS bumped, in Slice 4.)
- **Test scope on signature changes (project rule + MEMORY):** any task that changes a shared signature (`FactorInputs`, `CANONICAL_FACTOR_ORDER`, `KNOWN_NA_REASONS`, `_SCHEMA_VERSION`, `score_forward`) MUST run `tests/monitor/`, `tests/monitor/eval/`, AND `tests/commands/` — not just the mirror dir. The right command is baked into each verification point.
- **No network / no LLM in pure-core + fetch-cache tests:** `flow_fetch` tests inject the `fetch` callable; `holding_metrics` tests pass already-loaded inputs. `irc monitor` end-to-end needs `MINIMAX_*` env but no unit test here requires it.

---

## File structure (created / modified across all slices)

**Slice 1 — data layer (no bias impact):**
- Create `src/irc/monitor/flow_fetch.py` — EDGE fetch + pure parse + byte-stable JSON cache (mirrors `heat_fetch.py`).
- Create `src/irc/monitor/holding_metrics.py` — PURE: `HoldingMetric`, `FlowAggregate`, `per_stock_metrics`, `aggregate_flow`, per-stock valuation, flow windows.
- Create `tests/monitor/test_flow_fetch.py`, `tests/monitor/test_holding_metrics.py`.

**Slice 2 — report (you see data before it moves any bias):**
- Create `src/irc/monitor/render_drilldown.py` — PURE: `holdings_board_html`, `flow_rollup_html`, `drilldown_page_html`.
- Modify `src/irc/monitor/render_types.py` — `FundView.holding_metrics`.
- Modify `src/irc/monitor/render_html.py` — embed board+rollup in `_card`, broad-outage header note, CSS, `_EXPLAINER`.
- Modify `src/irc/commands/monitor_cmd.py` — build metrics in `_process_fund`, write `drilldown.html`.
- Create `tests/monitor/test_render_drilldown.py`; extend `tests/commands/test_monitor_cmd*`.

**Slice 3 — flow factor → bias (LOCKED-TEST FLIPS HERE):**
- Modify `src/irc/monitor/factor_maps.py` — `flow_score` + `_FLOW_BANDS`.
- Modify `src/irc/monitor/factors.py` — `FactorInputs.flow`, `_flow`, two `_NA_FLOW_*`, `KNOWN_NA_REASONS`, `build_factor_scores`.
- Modify `src/irc/monitor/profiles.py` — `active_cn_equity` eligible + D8 weights.
- Modify `src/irc/monitor/signal.py` — `_FAMILY_OF["flow"]`, `valuation_flow_conflict`.
- Modify `src/irc/monitor/render_factors.py` — `CANONICAL_FACTOR_ORDER`, `_DIVERGENCE_CAVEATS`.
- **Locked-test flips:** `tests/monitor/test_known_na_reasons.py`, `tests/monitor/test_profiles.py`, `tests/monitor/test_render_factors.py`, `tests/monitor/_oracle.py`.
- Create `tests/monitor/test_factor_maps_flow.py`; extend `tests/monitor/test_factors.py`, `test_signal.py`.

**Slice 4 — eval + versioning (LOCKED-TEST FLIPS HERE):**
- Modify `src/irc/monitor/eval/trace.py` — `_SCHEMA_VERSION "2"→"3"`, `holding_metrics` block.
- Modify `src/irc/monitor/eval/structural.py` — flow coverage health.
- Modify `src/irc/monitor/eval/forward_score.py` — `score_forward(target_engine=…)` + `engine_mismatch`.
- Create `evals/monitor_forward/runner.py` change — `_target_engine`, pass to `score_forward`, `excluded_by_engine`.
- Modify `src/irc/commands/monitor_cmd.py` — `_ENGINE_VERSION "1"→"2"`.
- Add a reconciliation oracle to `src/irc/monitor/eval/structural.py`.
- **Locked-test flips:** `tests/monitor/test_acceptance_eval.py:79`, `tests/monitor/eval/test_trace.py::test_schema_version_is_2`.
- Extend `tests/monitor/eval/test_forward_score.py`, `tests/monitor/eval/test_structural.py`, `tests/monitor/eval/test_trace.py`.

---

# SLICE 1 — Data layer (`flow_fetch.py` + `holding_metrics.py`)

No bias impact. Pure core + edge fetch only. Nothing downstream consumes these yet.

### Task 1.1: `flow_fetch.parse_main_net_pct` — pure column-tolerant parse

**Files:**
- Create: `src/irc/monitor/flow_fetch.py`
- Test: `tests/monitor/test_flow_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_flow_fetch.py
from __future__ import annotations
import pandas as pd
from irc.monitor.flow_fetch import parse_main_net_pct


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_parse_extracts_date_and_net_pct_percent_points():
    # akshare parses 主力净流入-净占比 already as percent-points (12.34 means 12.34%).
    df = _df([
        {"日期": "2026-06-16", "主力净流入-净占比": 12.34},
        {"日期": "2026-06-17", "主力净流入-净占比": -3.5},
    ])
    assert parse_main_net_pct(df) == (("2026-06-16", 12.34), ("2026-06-17", -3.5))


def test_parse_sorts_ascending_by_date():
    df = _df([
        {"日期": "2026-06-17", "主力净流入-净占比": 1.0},
        {"日期": "2026-06-16", "主力净流入-净占比": 2.0},
    ])
    assert parse_main_net_pct(df) == (("2026-06-16", 2.0), ("2026-06-17", 1.0))


def test_parse_drops_nonnumeric_or_nan_net_pct():
    df = _df([
        {"日期": "2026-06-16", "主力净流入-净占比": "—"},
        {"日期": "2026-06-17", "主力净流入-净占比": float("nan")},
        {"日期": "2026-06-18", "主力净流入-净占比": 4.0},
    ])
    assert parse_main_net_pct(df) == (("2026-06-18", 4.0),)


def test_parse_unexpected_shape_is_empty_not_fabricated():
    df = _df([{"wrong": 1}])
    assert parse_main_net_pct(df) == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_flow_fetch.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_main_net_pct'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/flow_fetch.py
"""EDGE + pure parse: monitor capital-flow leg via AkShare (ADR 0019).

`ak.stock_individual_fund_flow(stock, market)` returns ONE per-symbol daily
table (主力净流入-净占比 percent-points). Unlike `fund_purchase_em` there is NO
batch variant — flow is ~15-25 SEQUENTIAL per-A-share-symbol calls/run, deduped
and cached per day. Each fetch NEVER raises: a failure → None → flow_no_data
(spec §5.A). Parsing is pure and column-name-tolerant: an unexpected shape →
empty → N/A, NEVER a fabricated value.

Flow units are PERCENT-POINTS (D3): akshare parses the EastMoney 净占比 column via
pd.to_numeric with NO /100, so 12.34 means 12.34%. NO /100 here. CN endpoint
stays DIRECT (no IRC_HTTPS_PROXY) per the project http-proxy rule (ADR 0017).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

_log = logging.getLogger(__name__)

# A FlowSeries is parsed rows, NEVER a DataFrame, so the on-disk form is
# byte-stable: (date_iso, main_net_pct) in percent-points, sorted ascending.
FlowSeries = tuple[tuple[str, float], ...]

_DATE_COL = "日期"
_NET_PCT_COL = "主力净流入-净占比"


def _coerce(value: object) -> float | None:
    """Pure: numeric value or None for non-numeric / NaN. NO /100 (percent-points)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


def parse_main_net_pct(df: pd.DataFrame | None) -> FlowSeries:
    """Pure: extract (date_iso, 主力净流入-净占比) rows, sorted ascending by date,
    percent-point units. Rows with a non-numeric/NaN 净占比 are dropped. Unexpected
    shape (missing columns / empty / None) → empty tuple (→ N/A, never fabricated)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    if _DATE_COL not in df.columns or _NET_PCT_COL not in df.columns:
        return ()
    rows: list[tuple[str, float]] = []
    for _, row in df.iterrows():
        pct = _coerce(row[_NET_PCT_COL])
        if pct is None:
            continue
        rows.append((str(row[_DATE_COL]).strip(), pct))
    return tuple(sorted(rows, key=lambda r: r[0]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_flow_fetch.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/flow_fetch.py tests/monitor/test_flow_fetch.py
git commit -m "feat(monitor): flow_fetch.parse_main_net_pct (percent-point, column-tolerant)"
```

---

### Task 1.2: `flow_fetch._market_of` — A-share market routing

**Files:**
- Modify: `src/irc/monitor/flow_fetch.py`
- Test: `tests/monitor/test_flow_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_flow_fetch.py
import pytest
from irc.monitor.flow_fetch import _market_of


@pytest.mark.parametrize("symbol,market", [
    ("600519", "sh"), ("601318", "sh"),
    ("000001", "sz"), ("300750", "sz"),
    ("830799", "bj"), ("430047", "bj"),
])
def test_market_of_routes_a_share_prefixes(symbol, market):
    assert _market_of(symbol) == market


@pytest.mark.parametrize("symbol", ["00700", "AAPL", "09988"])
def test_market_of_non_a_share_is_none(symbol):
    # HK/US lines (QDII look-through) are not A-shares → None → never fetched.
    assert _market_of(symbol) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_flow_fetch.py::test_market_of_routes_a_share_prefixes -v`
Expected: FAIL with `ImportError: cannot import name '_market_of'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/flow_fetch.py (after parse helpers)
def _market_of(symbol: str) -> str | None:
    """Pure: A-share market for ak.stock_individual_fund_flow. 6*→sh, 0*/3*→sz,
    8*/4*→bj. A non-6-digit symbol or any other prefix → None (HK/US QDII lines
    are not A-shares → never fetched → uncovered)."""
    s = str(symbol).strip()
    if len(s) != 6 or not s.isdigit():
        return None
    head = s[0]
    if head == "6":
        return "sh"
    if head in ("0", "3"):
        return "sz"
    if head in ("8", "4"):
        return "bj"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_flow_fetch.py -v`
Expected: PASS (6 tests added).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/flow_fetch.py tests/monitor/test_flow_fetch.py
git commit -m "feat(monitor): flow_fetch._market_of A-share routing (HK/US → None)"
```

---

### Task 1.3: `flow_fetch` cache schema — serialize / load round-trip (ok + miss, sorted, 4dp)

**Files:**
- Modify: `src/irc/monitor/flow_fetch.py`
- Test: `tests/monitor/test_flow_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_flow_fetch.py
from irc.monitor.flow_fetch import _cache_payload, _load_cache_payload


def test_cache_payload_is_byte_stable_sorted_and_rounded():
    by_symbol = {
        "600519": (("2026-06-16", 1.23456), ("2026-06-15", 2.0)),
        "000001": None,  # confirmed miss
    }
    payload = _cache_payload(by_symbol)
    # symbols sorted; rows sorted ascending by date; main_net_pct rounded 4dp.
    assert list(payload.keys()) == ["000001", "600519"]
    assert payload["000001"] == {"status": "miss", "rows": []}
    assert payload["600519"] == {
        "status": "ok",
        "rows": [{"date": "2026-06-15", "main_net_pct": 2.0},
                 {"date": "2026-06-16", "main_net_pct": 1.2346}],
    }


def test_cache_roundtrip_maps_ok_to_series_and_miss_to_none():
    payload = {
        "600519": {"status": "ok", "rows": [{"date": "2026-06-16", "main_net_pct": 1.5}]},
        "000001": {"status": "miss", "rows": []},
    }
    loaded = _load_cache_payload(payload)
    assert loaded["600519"] == (("2026-06-16", 1.5),)
    assert loaded["000001"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_flow_fetch.py::test_cache_payload_is_byte_stable_sorted_and_rounded -v`
Expected: FAIL with `ImportError: cannot import name '_cache_payload'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/flow_fetch.py
_ROUND_DP = 4


def _rows_for(series: FlowSeries) -> list[dict]:
    """Sorted ascending by date, main_net_pct rounded to 4dp (byte-stable)."""
    return [
        {"date": d, "main_net_pct": round(pct, _ROUND_DP)}
        for d, pct in sorted(series, key=lambda r: r[0])
    ]


def _cache_payload(by_symbol: dict[str, FlowSeries | None]) -> dict[str, dict]:
    """Pure: symbol→series map → deterministic cache dict. None → status:miss
    (records a confirmed fetch failure so re-runs don't re-hit a dead symbol).
    Symbols sorted; rows sorted+rounded."""
    out: dict[str, dict] = {}
    for symbol in sorted(by_symbol):
        series = by_symbol[symbol]
        if series is None:
            out[symbol] = {"status": "miss", "rows": []}
        else:
            out[symbol] = {"status": "ok", "rows": _rows_for(series)}
    return out


def _load_cache_payload(payload: dict[str, dict]) -> dict[str, FlowSeries | None]:
    """Pure: cache dict → symbol→(series|None) map. ok→FlowSeries, miss→None."""
    out: dict[str, FlowSeries | None] = {}
    for symbol, entry in payload.items():
        if entry.get("status") != "ok":
            out[symbol] = None
            continue
        out[symbol] = tuple(
            (str(r["date"]), float(r["main_net_pct"])) for r in entry.get("rows", [])
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_flow_fetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/flow_fetch.py tests/monitor/test_flow_fetch.py
git commit -m "feat(monitor): flow_fetch byte-stable cache payload (ok/miss, sorted, 4dp)"
```

---

### Task 1.4: `flow_fetch.fetch_flow_series` — edge orchestration (cache-first, never raises, deduped, paced)

**Files:**
- Modify: `src/irc/monitor/flow_fetch.py`
- Test: `tests/monitor/test_flow_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_flow_fetch.py
import json as _json
from irc.monitor.flow_fetch import fetch_flow_series


def _fake_df(pct: float) -> pd.DataFrame:
    return pd.DataFrame([{"日期": "2026-06-16", "主力净流入-净占比": pct}])


def test_fetch_dedups_symbols_and_writes_cache(tmp_path):
    calls: list[str] = []

    def fake_fetch(*, stock, market):
        calls.append(stock)
        return _fake_df(5.0)

    out = fetch_flow_series(
        ("600519", "600519", "000001"),  # duplicate 600519
        cache_dir=tmp_path, today="2026-06-16", fetch=fake_fetch,
    )
    assert calls == ["600519", "000001"]  # deduped, ordered
    assert out["600519"] == (("2026-06-16", 5.0),)
    cache = _json.loads((tmp_path / "2026-06-16.json").read_text())
    assert set(cache) == {"000001", "600519"}


def test_fetch_is_idempotent_within_a_day_no_refetch(tmp_path):
    calls: list[str] = []

    def fake_fetch(*, stock, market):
        calls.append(stock)
        return _fake_df(5.0)

    fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16", fetch=fake_fetch)
    fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16", fetch=fake_fetch)
    assert calls == ["600519"]  # second call served from cache


def test_fetch_failure_degrades_to_miss_never_raises(tmp_path):
    def boom(*, stock, market):
        raise RuntimeError("rate limited")

    out = fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16", fetch=boom)
    assert out["600519"] is None  # flow_no_data, never a crash
    cache = _json.loads((tmp_path / "2026-06-16.json").read_text())
    assert cache["600519"] == {"status": "miss", "rows": []}


def test_fetch_skips_non_a_share_symbols(tmp_path):
    calls: list[str] = []

    def fake_fetch(*, stock, market):
        calls.append(stock)
        return _fake_df(5.0)

    out = fetch_flow_series(("00700",), cache_dir=tmp_path, today="2026-06-16", fetch=fake_fetch)
    assert calls == []          # HK line never fetched
    assert out["00700"] is None  # uncovered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_flow_fetch.py -k fetch -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_flow_series'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/flow_fetch.py
_PACING_SECONDS = 0.3  # light pacing between live CN calls (ADR 0014 rate-limit posture)


def _cache_path(cache_dir: Path, today: str) -> Path:
    return cache_dir / f"{today}.json"


def _read_cache(cache_dir: Path, today: str) -> dict[str, FlowSeries | None]:
    path = _cache_path(cache_dir, today)
    if not path.is_file():
        return {}
    try:
        return _load_cache_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
        _log.warning("flow_fetch: unreadable cache %s; refetching", path, exc_info=True)
        return {}


def _write_cache(cache_dir: Path, today: str, by_symbol: dict[str, FlowSeries | None]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = _cache_payload(by_symbol)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = _cache_path(cache_dir, today).with_suffix(f".tmp.{__import__('os').getpid()}")
    tmp.write_text(text, encoding="utf-8")
    import os
    os.replace(tmp, _cache_path(cache_dir, today))


def _fetch_one(symbol: str, fetch, *, sleep) -> FlowSeries | None:
    """EDGE: one symbol → FlowSeries or None. NEVER raises. Non-A-share → None
    (skipped, never fetched). CN endpoint DIRECT."""
    market = _market_of(symbol)
    if market is None:
        return None
    try:
        df = fetch(stock=symbol, market=market)
    except Exception:  # noqa: BLE001 — degrade to None (flow_no_data), never crash
        _log.warning("flow_fetch: stock_individual_fund_flow failed for %s", symbol,
                     exc_info=True)
        return None
    sleep(_PACING_SECONDS)
    return parse_main_net_pct(df)


def fetch_flow_series(
    symbols: tuple[str, ...], *, cache_dir: Path, today: str, fetch=None, sleep=time.sleep,
) -> dict[str, FlowSeries | None]:
    """EDGE: dedup symbols → cache-first per-day fetch → byte-stable cache write.
    Idempotent within a day (--resume / drilldown re-render never re-fetch).
    `fetch` is injectable for tests; the default lazy-imports akshare (house
    pattern). ~15-25 sequential CN calls/run, free endpoint."""
    if fetch is None:
        import akshare as ak  # local import — house pattern, no module-top akshare
        fetch = ak.stock_individual_fund_flow
    cached = _read_cache(cache_dir, today)
    out: dict[str, FlowSeries | None] = {}
    dirty = False
    for symbol in dict.fromkeys(symbols):  # dedup, preserve order
        if symbol in cached:
            out[symbol] = cached[symbol]
            continue
        out[symbol] = _fetch_one(symbol, fetch, sleep=sleep)
        dirty = True
    if dirty:
        _write_cache(cache_dir, today, {**cached, **out})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_flow_fetch.py -v`
Expected: PASS (all flow_fetch tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/flow_fetch.py tests/monitor/test_flow_fetch.py
git commit -m "feat(monitor): flow_fetch.fetch_flow_series (cache-first, never-raises, deduped, paced)"
```

---

### Task 1.5: `holding_metrics` flow bands + window blend (percent-point + ratio canary)

**Files:**
- Create: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

Note: `flow_band` (D7 step function) lives here in Slice 1 because `per_stock_metrics` needs it. In Slice 3 the SAME band map is exposed as `factor_maps.flow_score` for the factor layer; `factor_maps.flow_score` will delegate to this function (single source of truth). Keep the band thresholds here.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_holding_metrics.py
from __future__ import annotations
import pytest
from irc.monitor.holding_metrics import flow_band, _blend_flow_pct


# D7 bands in PERCENT-POINTS: >=3.0→+1.0, 1.0..3.0→+0.5, -1.0..1.0→0.0,
# -3.0..-1.0→-0.5, <=-3.0→-1.0.
@pytest.mark.parametrize("pct,score", [
    (5.0, 1.0), (3.0, 1.0),
    (2.0, 0.5), (1.0, 0.5),
    (0.5, 0.0), (0.0, 0.0), (-0.5, 0.0),
    (-1.0, -0.5), (-2.0, -0.5),
    (-3.0, -1.0), (-5.0, -1.0),
])
def test_flow_band_percent_point_thresholds(pct, score):
    assert flow_band(pct) == score


@pytest.mark.parametrize("ratio_value", [0.01, 0.03])
def test_ratio_unit_canary_lands_in_deadband(ratio_value):
    # 100x inversion guard: a ratio-unit value (0.01 == 1% in ratio) is read as
    # 0.01 PERCENT-POINTS → deadband → 0.0. If someone /100's the flow leg, a real
    # 3.0pp inflow would collapse to 0.03 here and silently score 0.0.
    assert flow_band(ratio_value) == 0.0


def test_blend_favors_20d_with_named_weights():
    # blended = 0.4*5d + 0.6*20d
    assert _blend_flow_pct(5.0, 0.0) == pytest.approx(2.0)
    assert _blend_flow_pct(0.0, 5.0) == pytest.approx(3.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.holding_metrics'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/holding_metrics.py
"""PURE per-stock drill-down core for `irc monitor` (ADR 0019). No I/O.

Takes already-loaded inputs (top holdings, per-code PE/PB MetricSeries, per-code
FlowSeries) and produces per-stock HoldingMetrics (valuation + flow) plus the
holding-weight-renormalized FlowAggregate that drives the `flow` factor.

Flow units are PERCENT-POINTS throughout (D3/D7). NO /100. Per-stock valuation is
a NEW computation distinct from the fund aggregate: each stock's PE percentile vs
ITS OWN history, reusing the opportunity primitives (no new fetch).
"""
from __future__ import annotations

from dataclasses import dataclass

# Flow blend weights (D7 note): steadier 20d favored. Named constants.
_FLOW_W_5D = 0.4
_FLOW_W_20D = 0.6


def _blend_flow_pct(pct_5d: float, pct_20d: float) -> float:
    """Pure: 0.4*5d + 0.6*20d, percent-points."""
    return _FLOW_W_5D * pct_5d + _FLOW_W_20D * pct_20d


# D7 bands as a pure step function, PERCENT-POINTS.
def flow_band(flow_pct: float) -> float:
    """Pure step function (D7). flow_pct in PERCENT-POINTS. >=3→+1, 1..3→+0.5,
    -1..1→0, -3..-1→-0.5, <=-3→-1."""
    if flow_pct >= 3.0:
        return 1.0
    if flow_pct >= 1.0:
        return 0.5
    if flow_pct > -1.0:
        return 0.0
    if flow_pct > -3.0:
        return -0.5
    return -1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/holding_metrics.py tests/monitor/test_holding_metrics.py
git commit -m "feat(monitor): holding_metrics flow_band (percent-point D7) + 5d/20d blend"
```

---

### Task 1.6: `holding_metrics` window means (short-series tolerant)

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from irc.monitor.holding_metrics import _window_mean


def test_window_mean_uses_last_n_rows():
    series = tuple((f"2026-06-{d:02d}", float(d)) for d in range(1, 11))  # 1.0..10.0
    assert _window_mean(series, 5) == pytest.approx((6 + 7 + 8 + 9 + 10) / 5)


def test_window_mean_short_series_uses_what_it_has():
    series = (("2026-06-01", 2.0), ("2026-06-02", 4.0))  # <5 rows
    assert _window_mean(series, 5) == pytest.approx(3.0)


def test_window_mean_empty_series_is_none():
    assert _window_mean((), 5) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py::test_window_mean_empty_series_is_none -v`
Expected: FAIL with `ImportError: cannot import name '_window_mean'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/holding_metrics.py
def _window_mean(series, n: int) -> float | None:
    """Pure: mean of the last n values (percent-points). <n rows uses what it has;
    empty series → None."""
    if not series:
        return None
    tail = series[-n:]
    return sum(v for _, v in tail) / len(tail)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/holding_metrics.py tests/monitor/test_holding_metrics.py
git commit -m "feat(monitor): holding_metrics window mean (short-series tolerant)"
```

---

### Task 1.7: `holding_metrics.per_stock_valuation` — per-stock PE percentile (maturity gate, negative/zero-PE → state None)

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

Reuses the opportunity primitives: `MetricSeries` (`points: (date_iso, pe, pb)`), `_pe_series_is_mature` (120 points / 180 days), `self_history_percentile` (rank ECDF, None if <30 pts), and `percentile_to_valuation_state` (from `irc.monitor.valuation`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from datetime import date, timedelta
from irc.monitor.holding_metrics import per_stock_valuation
from irc.opportunity.lookthrough_valuation import MetricSeries


def _mature_series(code: str, pes: list[float | None], pbs: list[float | None]):
    # 200 daily points to clear the 120-point / 180-day maturity gate.
    base = date(2025, 1, 1)
    pts = tuple(
        ((base + timedelta(days=i)).isoformat(), pes[i], pbs[i]) for i in range(len(pes))
    )
    return MetricSeries(code=code, source="eastmoney", points=pts)


def test_per_stock_valuation_latest_pe_pb_and_percentile():
    n = 200
    pes = [10.0 + i * 0.01 for i in range(n)]   # strictly rising → latest is the max
    pbs = [1.0 + i * 0.001 for i in range(n)]
    series = _mature_series("600519", pes, pbs)
    metric = per_stock_valuation("600519", series)
    assert metric.pe == pytest.approx(pes[-1])
    assert metric.pb == pytest.approx(pbs[-1])
    assert metric.pe_percentile == pytest.approx(1.0)  # latest == historical max
    assert metric.valuation_state == "very_expensive"  # pct 1.0 → expensive band
    assert metric.valuation_reason is None


def test_per_stock_valuation_negative_pe_shows_raw_state_none():
    n = 200
    pes = [-5.0] * n   # no strictly-positive PE point
    pbs = [2.0] * n
    series = _mature_series("000001", pes, pbs)
    metric = per_stock_valuation("000001", series)
    assert metric.pe == pytest.approx(-5.0)          # raw negative shown
    assert metric.pe_percentile is None
    assert metric.valuation_state is None
    assert metric.valuation_reason == "pe_not_positive"


def test_per_stock_valuation_immature_history_is_none():
    pes = [10.0 + i * 0.01 for i in range(50)]  # <120 points → immature
    pbs = [1.0] * 50
    series = _mature_series("300750", pes, pbs)
    metric = per_stock_valuation("300750", series)
    assert metric.pe_percentile is None
    assert metric.valuation_state is None
    assert metric.valuation_reason == "pe_immature"


def test_per_stock_valuation_no_series_is_none():
    metric = per_stock_valuation("600519", None)
    assert metric.pe is None and metric.pb is None
    assert metric.valuation_state is None
    assert metric.valuation_reason == "no_series"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k per_stock_valuation -v`
Expected: FAIL with `ImportError: cannot import name 'per_stock_valuation'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/holding_metrics.py (top imports)
import pandas as pd

from irc.monitor.valuation import percentile_to_valuation_state
from irc.opportunity.lookthrough_valuation import MetricSeries, _pe_series_is_mature
from irc.opportunity.returns import self_history_percentile


@dataclass(frozen=True)
class StockValuation:
    """Per-stock valuation: raw latest PE/PB + self-history PE percentile + state."""
    pe: float | None
    pb: float | None
    pe_percentile: float | None
    valuation_state: str | None
    valuation_reason: str | None  # None | pe_not_positive | pe_immature | no_series


def _latest_value(series: MetricSeries, idx: int) -> float | None:
    """Most recent point with a non-null value at tuple index idx (1=pe, 2=pb)."""
    for date_iso, pe, pb in reversed(series.points):
        value = pe if idx == 1 else pb
        if value is not None:
            return value
    return None


def _positive_pe_pandas(series: MetricSeries) -> "pd.Series":
    """Strictly-positive PE sub-series indexed by date (for the maturity gate +
    percentile). Mirrors the opportunity gate's pd.Series shape."""
    pairs = [(d, pe) for d, pe, _pb in series.points if pe is not None and pe > 0.0]
    if not pairs:
        return pd.Series([], dtype=float)
    idx = pd.to_datetime([d for d, _ in pairs])
    return pd.Series([v for _, v in pairs], index=idx)


def per_stock_valuation(code: str, series: MetricSeries | None) -> StockValuation:
    """Pure: per-stock latest PE/PB + self-history percentile (gated). Each stock
    vs ITS OWN PE history — NOT the fund-aggregate percentile. Negative/zero PE →
    no positive metric → percentile None → state None (board shows raw PE)."""
    if series is None:
        return StockValuation(None, None, None, None, "no_series")
    pe = _latest_value(series, 1)
    pb = _latest_value(series, 2)
    pos = _positive_pe_pandas(series)
    if pos.empty:
        return StockValuation(pe, pb, None, None, "pe_not_positive")
    if not _pe_series_is_mature(pos):
        return StockValuation(pe, pb, None, None, "pe_immature")
    pct = self_history_percentile(pos)
    return StockValuation(pe, pb, pct, percentile_to_valuation_state(pct), None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/holding_metrics.py tests/monitor/test_holding_metrics.py
git commit -m "feat(monitor): per_stock_valuation (self-history pct, maturity gate, neg-PE → None)"
```

---

### Task 1.8: `holding_metrics.per_stock_metrics` + `HoldingMetric` — assemble per-stock rows

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

`HoldingMetric` fields (spec §5.B): `symbol, name, weight_pct, pe, pb, pe_percentile, valuation_state, valuation_reason, flow_pct_5d, flow_pct_20d, flow_score, flow_reason`. Input `top_holdings` is the snapshot's sorted top-5 `ConstituentAnalysis` (fields `symbol`, `name_cn`, `weight_pct`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from dataclasses import dataclass as _dc
from irc.monitor.holding_metrics import per_stock_metrics, HoldingMetric


@_dc(frozen=True)
class _Holding:  # stand-in for ConstituentAnalysis (symbol, name_cn, weight_pct)
    symbol: str
    name_cn: str
    weight_pct: float


def _flow(n_days: int, pct: float):
    base = date(2026, 1, 1)
    return tuple(((base + timedelta(days=i)).isoformat(), pct) for i in range(n_days))


def test_per_stock_metrics_builds_rows_with_flow_windows_and_score():
    holdings = (_Holding("600519", "贵州茅台", 12.0),)
    flow_by_code = {"600519": _flow(20, 4.0)}  # steady +4.0pp → score +1.0
    metrics = per_stock_metrics(holdings, series_by_code={}, flow_series_by_code=flow_by_code)
    m = metrics[0]
    assert isinstance(m, HoldingMetric)
    assert m.symbol == "600519" and m.name == "贵州茅台" and m.weight_pct == 12.0
    assert m.flow_pct_5d == pytest.approx(4.0)
    assert m.flow_pct_20d == pytest.approx(4.0)
    assert m.flow_score == 1.0
    assert m.flow_reason is None


def test_per_stock_metrics_no_flow_series_marks_flow_no_data():
    holdings = (_Holding("600519", "贵州茅台", 12.0),)
    metrics = per_stock_metrics(holdings, series_by_code={}, flow_series_by_code={"600519": None})
    m = metrics[0]
    assert m.flow_score is None
    assert m.flow_reason == "flow_no_data"
    assert m.flow_pct_5d is None and m.flow_pct_20d is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k per_stock_metrics -v`
Expected: FAIL with `ImportError: cannot import name 'per_stock_metrics'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/holding_metrics.py
@dataclass(frozen=True)
class HoldingMetric:
    symbol: str
    name: str
    weight_pct: float
    pe: float | None
    pb: float | None
    pe_percentile: float | None
    valuation_state: str | None
    valuation_reason: str | None
    flow_pct_5d: float | None
    flow_pct_20d: float | None
    flow_score: float | None
    flow_reason: str | None  # None | flow_no_data


def _flow_metric(series) -> tuple[float | None, float | None, float | None, str | None]:
    """(5d, 20d, score, reason). None series → flow_no_data."""
    if series is None:
        return None, None, None, "flow_no_data"
    p5 = _window_mean(series, 5)
    p20 = _window_mean(series, 20)
    if p5 is None or p20 is None:
        return p5, p20, None, "flow_no_data"
    return p5, p20, flow_band(_blend_flow_pct(p5, p20)), None


def per_stock_metrics(top_holdings, series_by_code, flow_series_by_code) -> tuple[HoldingMetric, ...]:
    """Pure: top holdings + per-code PE/PB series + per-code flow series →
    HoldingMetric rows (valuation + flow). No I/O; consumes already-loaded inputs."""
    out: list[HoldingMetric] = []
    for h in top_holdings:
        val = per_stock_valuation(h.symbol, series_by_code.get(h.symbol))
        p5, p20, score, reason = _flow_metric(flow_series_by_code.get(h.symbol))
        out.append(HoldingMetric(
            symbol=h.symbol, name=h.name_cn, weight_pct=h.weight_pct,
            pe=val.pe, pb=val.pb, pe_percentile=val.pe_percentile,
            valuation_state=val.valuation_state, valuation_reason=val.valuation_reason,
            flow_pct_5d=p5, flow_pct_20d=p20, flow_score=score, flow_reason=reason,
        ))
    return tuple(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/holding_metrics.py tests/monitor/test_holding_metrics.py
git commit -m "feat(monitor): per_stock_metrics + HoldingMetric (valuation + flow rows)"
```

---

### Task 1.9: `holding_metrics.aggregate_flow` + `FlowAggregate` — weighted renorm + coverage gate

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

`FlowAggregate` (spec §5.B): `value: float|None, reason: str|None, covered_weight_ratio: float`. Aggregation = `Σ(wᵢ·sᵢ)/Σ(wᵢ)` over covered holdings; `covered_weight_ratio = Σ covered wᵢ / Σ all top-holding wᵢ`. Zero covered → `flow_no_data`; covered but ratio < 0.50 → `flow_no_coverage`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from irc.monitor.holding_metrics import aggregate_flow, FlowAggregate, _COVERAGE_FLOOR


def _metric(symbol, weight, score, reason=None):
    return HoldingMetric(symbol, symbol, weight, None, None, None, None, None,
                         None, None, score, reason)


def test_aggregate_flow_weighted_renorm_over_covered():
    metrics = (
        _metric("a", 30.0, 1.0),
        _metric("b", 10.0, -0.5),
    )
    agg = aggregate_flow(metrics)
    # (30*1.0 + 10*-0.5) / (30+10) = 25/40 = 0.625
    assert agg.value == pytest.approx(0.625)
    assert agg.reason is None
    assert agg.covered_weight_ratio == pytest.approx(1.0)


def test_aggregate_flow_zero_covered_is_flow_no_data():
    metrics = (_metric("a", 30.0, None, "flow_no_data"),)
    agg = aggregate_flow(metrics)
    assert agg.value is None and agg.reason == "flow_no_data"
    assert agg.covered_weight_ratio == pytest.approx(0.0)


def test_aggregate_flow_below_coverage_floor_is_flow_no_coverage():
    # covered weight 10 of total 40 → ratio 0.25 < 0.50 floor.
    metrics = (
        _metric("a", 10.0, 1.0),
        _metric("b", 30.0, None, "flow_no_data"),
    )
    agg = aggregate_flow(metrics)
    assert agg.value is None and agg.reason == "flow_no_coverage"
    assert agg.covered_weight_ratio == pytest.approx(0.25)


def test_aggregate_flow_exactly_at_floor_is_covered():
    # covered weight 20 of total 40 → ratio 0.50 == floor → covered.
    metrics = (
        _metric("a", 20.0, 1.0),
        _metric("b", 20.0, None, "flow_no_data"),
    )
    agg = aggregate_flow(metrics)
    assert agg.value == pytest.approx(1.0)
    assert agg.reason is None
    assert _COVERAGE_FLOOR == 0.50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k aggregate_flow -v`
Expected: FAIL with `ImportError: cannot import name 'aggregate_flow'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/holding_metrics.py
_COVERAGE_FLOOR = 0.50  # mirrors the valuation factor's covered-NAV gate (D6)

_NA_FLOW_NO_DATA = "flow_no_data"
_NA_FLOW_NO_COVERAGE = "flow_no_coverage"


@dataclass(frozen=True)
class FlowAggregate:
    value: float | None
    reason: str | None
    covered_weight_ratio: float


def aggregate_flow(metrics: tuple[HoldingMetric, ...]) -> FlowAggregate:
    """Pure: Σ(wᵢ·sᵢ)/Σ(wᵢ) over holdings with a non-None flow_score, renormalized
    over covered top holdings (D5). covered_weight_ratio = Σ covered wᵢ / Σ all wᵢ.
    Zero covered → flow_no_data; covered but ratio < 0.50 → flow_no_coverage."""
    total_w = sum(m.weight_pct for m in metrics)
    covered = [m for m in metrics if m.flow_score is not None]
    covered_w = sum(m.weight_pct for m in covered)
    ratio = covered_w / total_w if total_w > 0.0 else 0.0
    if not covered or covered_w <= 0.0:
        return FlowAggregate(None, _NA_FLOW_NO_DATA, ratio)
    if ratio < _COVERAGE_FLOOR:
        return FlowAggregate(None, _NA_FLOW_NO_COVERAGE, ratio)
    value = sum(m.weight_pct * m.flow_score for m in covered) / covered_w
    return FlowAggregate(value, None, ratio)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit + Slice 1 verification**

```bash
git add src/irc/monitor/holding_metrics.py tests/monitor/test_holding_metrics.py
git commit -m "feat(monitor): aggregate_flow weighted renorm + coverage gate (D5/D6)"
```

**Slice 1 verification point:**

Run: `uv run pytest tests/monitor/test_flow_fetch.py tests/monitor/test_holding_metrics.py -v`
Expected: ALL PASS. No network, no LLM (fetch injected, inputs pre-loaded).

Run: `uv run ruff check src/irc/monitor/flow_fetch.py src/irc/monitor/holding_metrics.py tests/monitor/test_flow_fetch.py tests/monitor/test_holding_metrics.py`
Expected: no errors (line-length 100). If either new module exceeds 200 lines, split helpers out.

Passing looks like: two new modules, no consumer yet, no existing test touched → the rest of the monitor suite is unchanged. Confirm with `uv run pytest tests/monitor/ -q` (still green).

---

# SLICE 2 — Report (`render_drilldown.py` + `FundView.holding_metrics` + `monitor_cmd` wiring)

You see the data before it moves any bias. The factor is NOT wired yet — only the board + standalone page render the metrics.

### Task 2.1: `FundView.holding_metrics` field

**Files:**
- Modify: `src/irc/monitor/render_types.py`
- Test: `tests/monitor/test_render_types.py` (create if absent)

This changes a shared type (`FundView`) → run the broad test scope at the verification point.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_render_types.py (create or append)
from irc.monitor.render_types import FundView


def test_fundview_holding_metrics_defaults_empty():
    # trailing, defaulted → existing construction sites stay green.
    import inspect
    sig = inspect.signature(FundView)
    assert sig.parameters["holding_metrics"].default == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_types.py -v`
Expected: FAIL with `KeyError: 'holding_metrics'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_types.py — add the trailing defaulted field + import
from irc.monitor.holding_metrics import HoldingMetric  # add at top
# ...
@dataclass(frozen=True)
class FundView:
    # ... existing fields unchanged ...
    factor_scores: tuple[FactorScore, ...] = ()
    impacts_status: str = "ok"
    holding_metrics: tuple[HoldingMetric, ...] = ()   # ADD (trailing, defaulted)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_types.py tests/monitor/test_render_types.py
git commit -m "feat(monitor): FundView.holding_metrics (trailing defaulted)"
```

---

### Task 2.2: `render_drilldown.holdings_board_html` — per-stock board

**Files:**
- Create: `src/irc/monitor/render_drilldown.py`
- Test: `tests/monitor/test_render_drilldown.py`

Board columns (spec §5.D): `# · symbol · name · weight% · PB · PE · PE-pct · 估值 state · 5d净占比 · 20d净占比 · flow score`. N/A cells show `—` + reason. Rows sorted by weight desc. Use `html.escape` (mirror `render_factors.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_render_drilldown.py
from __future__ import annotations
from irc.monitor.holding_metrics import HoldingMetric
from irc.monitor.render_drilldown import holdings_board_html


def _m(symbol, weight, **kw):
    base = dict(pe=None, pb=None, pe_percentile=None, valuation_state=None,
                valuation_reason=None, flow_pct_5d=None, flow_pct_20d=None,
                flow_score=None, flow_reason=None)
    base.update(kw)
    return HoldingMetric(symbol=symbol, name=symbol, weight_pct=weight, **base)


def test_board_renders_present_row_values():
    m = _m("600519", 12.0, pe=30.0, pb=8.0, pe_percentile=0.82,
           valuation_state="expensive", flow_pct_5d=4.0, flow_pct_20d=3.5, flow_score=1.0)
    html = holdings_board_html((m,))
    assert "600519" in html
    assert "30.0" in html and "8.0" in html
    assert "expensive" in html


def test_board_na_cells_show_dash_and_reason():
    m = _m("000001", 5.0, pe=-5.0, valuation_reason="pe_not_positive", flow_reason="flow_no_data")
    html = holdings_board_html((m,))
    assert "—" in html
    assert "pe_not_positive" in html
    assert "flow_no_data" in html


def test_board_rows_sorted_by_weight_desc():
    rows = (_m("aaa", 5.0), _m("bbb", 20.0))
    html = holdings_board_html(rows)
    assert html.index("bbb") < html.index("aaa")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.monitor.render_drilldown'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_drilldown.py
"""PURE per-stock drill-down rendering for `irc monitor` (ADR 0019). No I/O.

Renders the top-5 holdings board (PB/PE + 5d/20d 净占比 + flow score) and the
flow roll-up reconciliation line. ADR 0015 lean line: 估值/资金流/偏多/偏空 only —
NO 买入/卖出, no target weights, no per-instrument action.
"""
from __future__ import annotations
from html import escape
from irc.monitor.holding_metrics import FlowAggregate, HoldingMetric
from irc.monitor.types import SignalRecord


def _cell_num(v: float | None, fmt: str = "{:.2f}") -> str:
    return "—" if v is None else escape(fmt.format(v))


def _cell_state(state: str | None, reason: str | None) -> str:
    if state is not None:
        return escape(state)
    return f"— <span class='na-reason'>{escape(reason)}</span>" if reason else "—"


def _flow_cell(score: float | None, reason: str | None) -> str:
    if score is not None:
        return f"{score:+.1f}"
    return f"— <span class='na-reason'>{escape(reason)}</span>" if reason else "—"


def _row(i: int, m: HoldingMetric) -> str:
    return (
        f"<tr><td>{i}</td><td>{escape(m.symbol)}</td><td>{escape(m.name)}</td>"
        f"<td>{m.weight_pct:.2f}</td>"
        f"<td>{_cell_num(m.pb)}</td><td>{_cell_num(m.pe)}</td>"
        f"<td>{_cell_num(m.pe_percentile, '{:.0%}')}</td>"
        f"<td>{_cell_state(m.valuation_state, m.valuation_reason)}</td>"
        f"<td>{_cell_num(m.flow_pct_5d)}</td><td>{_cell_num(m.flow_pct_20d)}</td>"
        f"<td>{_flow_cell(m.flow_score, m.flow_reason)}</td></tr>"
    )


def holdings_board_html(metrics: tuple[HoldingMetric, ...]) -> str:
    """PURE: top-holdings board, rows sorted by weight desc, N/A cells dashed."""
    head = (
        "<tr><th>#</th><th>代码</th><th>名称</th><th>权重%</th><th>PB</th><th>PE</th>"
        "<th>PE分位</th><th>估值</th><th>5d净占比</th><th>20d净占比</th><th>资金流分</th></tr>"
    )
    ordered = sorted(metrics, key=lambda m: m.weight_pct, reverse=True)
    rows = "".join(_row(i, m) for i, m in enumerate(ordered, start=1))
    return f"<table class='holdings-board'>{head}{rows}</table>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_drilldown.py tests/monitor/test_render_drilldown.py
git commit -m "feat(monitor): render_drilldown.holdings_board_html (top-5 board, lean language)"
```

---

### Task 2.3: `render_drilldown.flow_rollup_html` — reconciliation + representativeness line

**Files:**
- Modify: `src/irc/monitor/render_drilldown.py`
- Test: `tests/monitor/test_render_drilldown.py`

The roll-up line (spec §5.D): `flow factor = Σ(wᵢ·sᵢ)/Σ(wᵢ) = <value> (covered <ratio>% of top-5; top-5 = <Σ weight_pct>% of fund AUM)`. The "top-5 = X% of fund AUM" context is ALWAYS shown (transparency, not a coverage veto). NO imperative language.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_render_drilldown.py
from irc.monitor.holding_metrics import FlowAggregate
from irc.monitor.render_drilldown import flow_rollup_html
from irc.monitor.types import SignalRecord, FactorContribution


def _sig(composite=0.3):
    return SignalRecord(fund_id="x", status="ok", bias="ADD_BIAS", composite=composite,
                        signal_confidence=1.0, available_weight=0.9,
                        present_families=("capital-flow",),
                        contributions=(FactorContribution("flow", 0.15, 0.625, 0.094, 1.0, True, ""),),
                        divergence_codes=())


def test_rollup_shows_value_coverage_and_aum_representativeness():
    metrics = (_m("a", 30.0, flow_score=1.0), _m("b", 10.0, flow_score=-0.5))
    agg = FlowAggregate(value=0.625, reason=None, covered_weight_ratio=1.0)
    html = flow_rollup_html(metrics, agg, _sig())
    assert "0.625" in html or "0.6250" in html
    assert "100%" in html        # covered ratio
    assert "40" in html          # top-5 = 40% of fund AUM (sum of weight_pct)


def test_rollup_na_aggregate_states_reason():
    metrics = (_m("a", 10.0, flow_reason="flow_no_data"),)
    agg = FlowAggregate(value=None, reason="flow_no_coverage", covered_weight_ratio=0.0)
    html = flow_rollup_html(metrics, agg, _sig())
    assert "flow_no_coverage" in html


def test_rollup_has_no_imperative_trade_language():
    metrics = (_m("a", 30.0, flow_score=1.0),)
    agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    html = flow_rollup_html(metrics, agg, _sig())
    assert "买入" not in html and "卖出" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -k rollup -v`
Expected: FAIL with `ImportError: cannot import name 'flow_rollup_html'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/render_drilldown.py
def _aum_share(metrics: tuple[HoldingMetric, ...]) -> float:
    return sum(m.weight_pct for m in metrics)


def flow_rollup_html(
    metrics: tuple[HoldingMetric, ...], agg: FlowAggregate, signal: SignalRecord,
) -> str:
    """PURE: the reconciliation line — flow factor = Σ(wᵢ·sᵢ)/Σ(wᵢ), covered ratio,
    and top-5 representativeness (% of fund AUM, ALWAYS shown). Lean language only."""
    aum = _aum_share(metrics)
    if agg.value is None:
        body = (
            f"资金流因子 = N/A（{escape(agg.reason or 'flow_no_data')}）· "
            f"前五大 = {aum:.0f}% of 基金资产"
        )
    else:
        body = (
            f"资金流因子 = Σ(wᵢ·sᵢ)/Σ(wᵢ) = {agg.value:+.4f} "
            f"（覆盖 {agg.covered_weight_ratio:.0%} of 前五大；"
            f"前五大 = {aum:.0f}% of 基金资产）· "
            f"综合 C = {signal.composite:+.4f} → {escape(signal.bias or 'NEUTRAL')}"
        )
    return f"<div class='flow-rollup'>{body}</div>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_drilldown.py tests/monitor/test_render_drilldown.py
git commit -m "feat(monitor): flow_rollup_html (reconciliation + AUM representativeness)"
```

---

### Task 2.4: `render_drilldown.drilldown_page_html` — standalone page wrapper

**Files:**
- Modify: `src/irc/monitor/render_drilldown.py`
- Test: `tests/monitor/test_render_drilldown.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_render_drilldown.py
from irc.monitor.render_drilldown import drilldown_page_html


def test_drilldown_page_is_self_contained_html_per_fund():
    metrics = (_m("600519", 12.0, pe=30.0, flow_score=1.0),)
    agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    views = (("519069", "易方达蓝筹", metrics, agg, _sig()),)
    html = drilldown_page_html(views)
    assert html.startswith("<!doctype html>")
    assert "519069" in html and "易方达蓝筹" in html
    assert "600519" in html        # board embedded
    assert "<style>" in html       # shared CSS inline (no remote refs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -k drilldown_page -v`
Expected: FAIL with `ImportError: cannot import name 'drilldown_page_html'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/render_drilldown.py
_DRILLDOWN_CSS = (
    "<style>"
    "body{font-family:sans-serif}"
    ".holdings-board{border-collapse:collapse;font-size:13px;margin:8px 0;width:100%}"
    ".holdings-board th,.holdings-board td{border:1px solid #d0d7de;padding:3px 6px;text-align:right}"
    ".holdings-board th:nth-child(-n+3),.holdings-board td:nth-child(-n+3){text-align:left}"
    ".na-reason{color:#8c959f;font-size:11px}"
    ".flow-rollup{margin:8px 0;padding:6px 8px;background:#f6f8fa;border-left:3px solid #0969da;font-size:13px}"
    "</style>"
)


def drilldown_section_html(name_cn: str, fund_id: str, metrics, agg, signal) -> str:
    """PURE: one fund's board + roll-up section (reused by card + standalone page)."""
    return (
        f"<section class='drilldown' id='dd-{escape(fund_id)}'>"
        f"<h2>{escape(name_cn)} ({escape(fund_id)})</h2>"
        f"{holdings_board_html(metrics)}{flow_rollup_html(metrics, agg, signal)}"
        "</section>"
    )


def drilldown_page_html(views) -> str:
    """PURE: full standalone drilldown.html. views = iterable of
    (fund_id, name_cn, metrics, agg, signal). Self-contained: inline CSS, no JS."""
    sections = "".join(
        drilldown_section_html(name_cn, fund_id, metrics, agg, signal)
        for fund_id, name_cn, metrics, agg, signal in views
    )
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor — 个股钻取</title>" + _DRILLDOWN_CSS + "</head><body>"
        + sections + "</body></html>"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_drilldown.py tests/monitor/test_render_drilldown.py
git commit -m "feat(monitor): drilldown_page_html (self-contained standalone artifact)"
```

---

### Task 2.5: Embed board + roll-up in the card; broad-outage header note; CSS + `_EXPLAINER`

**Files:**
- Modify: `src/irc/monitor/render_html.py`
- Test: `tests/monitor/test_render_html.py` (append)

Spec §5.D: `_card` embeds the board + roll-up after the factor table for funds that have metrics. `render_report` emits ONE run-level header note `⚠ 资金流数据今日不可用——倾向回退至五因子 (flow unavailable today; lean fell back to 5-factor)` ONLY when set-wide flow coverage collapses (0 of the flow-eligible funds got a usable flow leg). It is computed PURELY from the views' factor N/A reasons. Extend `_EXPLAINER` to name the flow leg (估值 + 资金流 → 倾向; 非买卖指令).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_render_html.py (mirror existing fixtures there)
from irc.monitor.render_html import _flow_outage_note, render_report
from irc.monitor.holding_metrics import HoldingMetric, FlowAggregate


def _hm(score, reason=None):
    return HoldingMetric("600519", "贵州茅台", 12.0, 30.0, 8.0, 0.8, "expensive",
                         None, 4.0, 3.5, score, reason)


def test_card_embeds_board_when_metrics_present():
    # build a minimal view with holding_metrics (reuse this file's view factory).
    view = _view_with_metrics(holding_metrics=(_hm(1.0),))  # helper added in this test module
    html = _card(view, None)
    assert "holdings-board" in html
    assert "600519" in html


def test_flow_outage_note_only_when_set_wide_collapse():
    # both eligible funds lost flow → note present.
    collapsed = (
        _view_with_factor_na("flow", "flow_no_data"),
        _view_with_factor_na("flow", "flow_no_coverage"),
    )
    assert "资金流数据今日不可用" in _flow_outage_note(collapsed)
    # at least one fund has a present flow factor → no note.
    mixed = (_view_with_factor_present("flow"), _view_with_factor_na("flow", "flow_no_data"))
    assert _flow_outage_note(mixed) == ""
    # no flow-eligible fund at all (all profile_ineligible) → no note (not an outage).
    none_eligible = (_view_with_factor_na("flow", "profile_ineligible"),)
    assert _flow_outage_note(none_eligible) == ""
```

(Add small `_view_with_*` helpers in the test module that build a `FundView` with the given `factor_scores`/`holding_metrics`, mirroring existing fixtures.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_html.py -k "flow_outage or board_embeds" -v`
Expected: FAIL with `ImportError: cannot import name '_flow_outage_note'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_html.py
from irc.monitor.render_drilldown import holdings_board_html, flow_rollup_html  # add import
from irc.monitor.holding_metrics import aggregate_flow  # add import

# In _card, after factor_table_html(...), insert the drilldown block when metrics exist:
def _drilldown_block(view: FundView) -> str:
    if not view.holding_metrics:
        return ""
    agg = aggregate_flow(view.holding_metrics)
    return (holdings_board_html(view.holding_metrics)
            + flow_rollup_html(view.holding_metrics, agg, view.signal))

# _card: add f"{_drilldown_block(view)}" right after the factor table line.


def _flow_eligible(view: FundView) -> bool:
    """A fund is flow-eligible iff its flow factor is present OR N/A for a
    data/coverage reason (NOT profile_ineligible)."""
    for s in view.factor_scores:
        if s.name == "flow":
            return s.reason != "profile_ineligible"
    return False


def _flow_present(view: FundView) -> bool:
    return any(s.name == "flow" and s.eligible for s in view.factor_scores)


def _flow_outage_note(views: tuple[FundView, ...]) -> str:
    """PURE: ONE run-level header line iff set-wide flow coverage collapses — every
    flow-eligible fund lost its flow leg (0 usable). No flow-eligible fund → "" (not
    an outage). Driven by factor N/A reasons, not a side effect. Per-fund N/A stays
    non-caveating (KNOWN_NA_REASONS)."""
    eligible = [v for v in views if _flow_eligible(v)]
    if not eligible:
        return ""
    if any(_flow_present(v) for v in eligible):
        return ""
    return ('<div class="flow-outage">⚠ 资金流数据今日不可用——倾向回退至五因子 '
            "(flow unavailable today; lean fell back to 5-factor)</div>")
```

Add CSS to `_CSS`: `.holdings-board`, `.na-reason`, `.flow-rollup`, `.flow-outage{margin:8px 0;padding:6px 8px;background:#fff8c5;border:1px solid #d4a72c;border-radius:6px}`. Extend `_EXPLAINER` legend: append `估值 + 资金流 → 倾向（偏多/偏空），仍为研究参考、非买卖指令`. Insert `_flow_outage_note(views)` into `render_report`'s body right after `header` (before `_EXPLAINER`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_html.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_html.py tests/monitor/test_render_html.py
git commit -m "feat(monitor): embed drilldown board in card + set-wide flow-outage header note"
```

---

### Task 2.6: `monitor_cmd` — build holding_metrics in `_process_fund`; write `drilldown.html`

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Modify: `src/irc/monitor/holding_metrics.py` (add the edge-input assembly helper here, NOT inline)
- Test: `tests/commands/test_monitor_cmd_drilldown.py` (create)

Per spec §6, flow-input assembly lives in `holding_metrics.py` (a pure builder taking the top holdings + already-loaded series), NOT inline in the 672-line command. `monitor_cmd` only does the I/O: dedup symbols → `fetch_flow_series` (edge) → `_stock_series_by_code` (cached read, already imported pattern) → call the pure builder → attach to the view; then write `drilldown.html`.

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_monitor_cmd_drilldown.py
from __future__ import annotations
from pathlib import Path
from irc.monitor.holding_metrics import build_holding_metrics, HoldingMetric


def test_build_holding_metrics_assembles_from_loaded_inputs():
    # Pure assembly helper — NO I/O. Top holdings + pre-loaded series in → metrics out.
    class _H:
        def __init__(self, s, n, w):
            self.symbol, self.name_cn, self.weight_pct = s, n, w
    holdings = (_H("600519", "贵州茅台", 12.0),)
    flow_by_code = {"600519": (("2026-06-16", 4.0),) * 20}
    metrics = build_holding_metrics(holdings, series_by_code={}, flow_series_by_code=flow_by_code)
    assert isinstance(metrics[0], HoldingMetric)
    assert metrics[0].flow_score == 1.0
```

(A separate edge test exercises the `drilldown.html` write via the existing `monitor_cmd` test harness in `tests/commands/test_monitor_cmd*.py` — assert `outputs/<date>/monitor/drilldown.html` exists after `run_monitor` with patched fetches. Add it next to the existing acceptance fixtures so the LLM/akshare edges are already monkeypatched.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_drilldown.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_holding_metrics'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/holding_metrics.py — pure assembly entry (keeps monitor_cmd thin)
def build_holding_metrics(top_holdings, series_by_code, flow_series_by_code):
    """Pure assembly entry called from the edge (monitor_cmd). Identical to
    per_stock_metrics — named so the command imports one stable name. Effects
    (fetch_flow_series, _stock_series_by_code) stay in monitor_cmd."""
    return per_stock_metrics(top_holdings, series_by_code, flow_series_by_code)
```

```python
# src/irc/commands/monitor_cmd.py — wire the edge in _process_fund (active_fund branch)
# after top_holdings is computed (line ~571), and con is available:
from irc.monitor.flow_fetch import fetch_flow_series
from irc.monitor.holding_metrics import build_holding_metrics
from irc.opportunity.inputs_loader import _stock_series_by_code

holding_metrics: tuple = ()
if profile_spec and profile_spec.lookthrough == "active_fund" and top_holdings:
    symbols = tuple(h.symbol for h in top_holdings)
    flow_series = fetch_flow_series(
        symbols, cache_dir=root / "data" / "monitor" / "fund_flow",
        today=_today_for(root),  # pass run date through; see note below
    )
    series_by_code = _stock_series_by_code(con, symbols) if con is not None else {}
    holding_metrics = build_holding_metrics(top_holdings, series_by_code, flow_series)
# pass holding_metrics into _make_view (add param) → FundView.holding_metrics
```

Note: `_process_fund` does not currently receive `today`; thread the run date in (add a `today` kw to `_process_fund` and pass `_today` from `run_monitor`). Then in `run_monitor`, after `_write_outputs`, write the standalone page:

```python
# src/irc/commands/monitor_cmd.py — in run_monitor, after _write_outputs(...)
from irc.monitor.holding_metrics import aggregate_flow
from irc.monitor.render_drilldown import drilldown_page_html

dd_views = tuple(
    (v.fund_id, v.name_cn, v.holding_metrics, aggregate_flow(v.holding_metrics), v.signal)
    for v in views if v.holding_metrics
)
if dd_views:
    atomic_write_text(out / "drilldown.html", drilldown_page_html(dd_views))
```

Update `_make_view` to accept and set `holding_metrics=...` (trailing kw, default `()`), and update the `_process_fund` call site in `run_monitor` to pass `today=_today`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_drilldown.py -v`
Expected: PASS.

- [ ] **Step 5: Commit + Slice 2 verification**

```bash
git add src/irc/monitor/holding_metrics.py src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_drilldown.py
git commit -m "feat(monitor): wire holding_metrics in _process_fund + write drilldown.html"
```

**Slice 2 verification point:**

Run: `uv run pytest tests/monitor/ tests/monitor/eval/ tests/commands/ -q`
Expected: ALL PASS. (`FundView.holding_metrics` is a shared-type change → broad scope required by the project test-scope rule. The existing `monitor_cmd` acceptance tests must still pass; `holding_metrics` defaults to `()` so no view-construction site breaks.)

Run: `uv run ruff check src tests`
Expected: no errors. Confirm `render_drilldown.py`, `render_html.py`, `holding_metrics.py` all < 200 lines.

Passing looks like: the report renders a board + roll-up; a standalone `drilldown.html` is produced; the BIAS is unchanged (no factor wired yet) — verify by confirming the factor table still shows the 5 factors and `signal.json` biases match the pre-slice baseline.

---

# SLICE 3 — Flow factor → bias (LOCKED TESTS FLIP HERE)

Now the factor enters the composite. The 4 slice-3 locked tests flip in this slice as deliberate red→green updates.

### Task 3.1: `factor_maps.flow_score` — D7 band map (delegates to `holding_metrics.flow_band`)

**Files:**
- Modify: `src/irc/monitor/factor_maps.py`
- Test: `tests/monitor/test_factor_maps_flow.py` (create)

`factor_maps.flow_score` is the factor-layer entry; it delegates to `holding_metrics.flow_band` (single source of truth for the D7 thresholds). It takes the aggregate value (already on [−1,+1]) and is the identity-passthrough band — but per spec §5.C `flow_score(flow_pct)` is the percent-point band function. To avoid two band definitions, define `factor_maps.flow_score = flow_band` (re-export) and add the `_FLOW_BANDS` doc constant.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_factor_maps_flow.py
import pytest
from irc.monitor.factor_maps import flow_score


@pytest.mark.parametrize("pct,score", [
    (3.0, 1.0), (1.0, 0.5), (0.0, 0.0), (-1.0, -0.5), (-3.0, -1.0),
])
def test_flow_score_percent_point_bands(pct, score):
    assert flow_score(pct) == score


@pytest.mark.parametrize("ratio_value", [0.01, 0.03])
def test_flow_score_ratio_canary_lands_in_deadband(ratio_value):
    assert flow_score(ratio_value) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_factor_maps_flow.py -v`
Expected: FAIL with `ImportError: cannot import name 'flow_score'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/factor_maps.py — add at end
from irc.monitor.holding_metrics import flow_band as flow_score  # noqa: E402,F401

# D7 band thresholds (percent-points), documented here for the factor layer.
# Single source of truth is holding_metrics.flow_band; flow_score re-exports it.
_FLOW_BANDS = ((3.0, 1.0), (1.0, 0.5), (-1.0, 0.0), (-3.0, -0.5), (-1e18, -1.0))
```

(If a circular import arises — `holding_metrics` imports `valuation` which imports nothing from `factor_maps` at module top, so importing `holding_metrics` from `factor_maps` is safe. Verify with the test run.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_factor_maps_flow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/factor_maps.py tests/monitor/test_factor_maps_flow.py
git commit -m "feat(monitor): factor_maps.flow_score re-exports D7 band (single source)"
```

---

### Task 3.2: `FactorInputs.flow` + `factors._flow` + N/A reasons + `KNOWN_NA_REASONS` [LOCKED TEST FLIP]

**Files:**
- Modify: `src/irc/monitor/factors.py`
- Modify: `tests/monitor/test_known_na_reasons.py` **[LOCKED FLIP]**
- Test: `tests/monitor/test_factors.py` (append)

`FactorInputs.flow: FlowAggregate | None = None` — **trailing AND defaulted** so the 5 existing construction sites stay green (`eval/backtest.py:33`, `tests/monitor/test_factors.py`, `test_heat_fetch.py`, `test_factors_property.py`, `test_valuation_wiring.py`). `_flow` maps the aggregate's reason to its N/A: `profile_ineligible` (not eligible) / `flow_no_data` (None or reason flow_no_data) / `flow_no_coverage` (value None) / else `FactorScore("flow", value, True, "", 1.0)`. Add `_NA_FLOW_NO_DATA`, `_NA_FLOW_NO_COVERAGE` to constants + `KNOWN_NA_REASONS`. `build_factor_scores` appends `_flow(...)` → 6 factors.

**LOCKED FLIP** — `tests/monitor/test_known_na_reasons.py`: `_EXPECTED` (currently 8 codes) gains `flow_no_data` + `flow_no_coverage` → 10; `test_known_na_reasons_is_exactly_the_eight_codes` becomes the ten-codes test.

- [ ] **Step 1: Write the failing test (incl. the locked flip)**

```python
# tests/monitor/test_known_na_reasons.py — UPDATE _EXPECTED (was 8 → now 10) [LOCKED FLIP]
_EXPECTED = {
    "profile_ineligible",
    "trend_insufficient_history",
    "valuation_no_anchor",
    "valuation_unknown_state",
    "heat_no_data",
    "macro_insufficient_families",
    "macro_empty_pool",
    "constituent_no_coverage",
    "flow_no_data",          # ADD
    "flow_no_coverage",      # ADD
}
# rename the test for clarity:
def test_known_na_reasons_is_exactly_the_ten_codes():
    assert KNOWN_NA_REASONS == frozenset(_EXPECTED)
```

```python
# tests/monitor/test_factors.py — append _flow behavior tests
from irc.monitor.factors import FactorInputs, build_factor_scores, _flow
from irc.monitor.holding_metrics import FlowAggregate


def _inp(flow=None):
    return FactorInputs(
        acc_nav=(), minimum_observations=1, valuation_state=None, valuation_cached=False,
        restricted=None, aum_delta_pct=None, macro_rows=(), constituent_rows=(), flow=flow,
    )


def test_flow_profile_ineligible_on_gold():
    s = _flow("gold", _inp(FlowAggregate(0.5, None, 1.0)))
    assert not s.eligible and s.reason == "profile_ineligible"


def test_flow_none_input_is_flow_no_data():
    s = _flow("active_cn_equity", _inp(None))
    assert not s.eligible and s.reason == "flow_no_data"


def test_flow_no_coverage_when_value_none():
    s = _flow("active_cn_equity", _inp(FlowAggregate(None, "flow_no_coverage", 0.25)))
    assert not s.eligible and s.reason == "flow_no_coverage"


def test_flow_present_value_passes_through():
    s = _flow("active_cn_equity", _inp(FlowAggregate(0.625, None, 1.0)))
    assert s.eligible and s.value == 0.625


def test_build_factor_scores_now_has_six_factors():
    scores = build_factor_scores("active_cn_equity", _inp(FlowAggregate(0.5, None, 1.0)))
    assert [s.name for s in scores] == ["trend", "valuation", "heat", "macro_tilt",
                                        "constituent", "flow"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_known_na_reasons.py tests/monitor/test_factors.py -k "flow or ten_codes or six_factors" -v`
Expected: FAIL — `_flow` not importable; `KNOWN_NA_REASONS` still 8.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/factors.py
from irc.monitor.factor_maps import valuation_state_score, heat_score  # existing
from irc.monitor.holding_metrics import FlowAggregate  # add

# add constants near the other _NA_*:
_NA_FLOW_NO_DATA = "flow_no_data"
_NA_FLOW_NO_COVERAGE = "flow_no_coverage"

# add both to KNOWN_NA_REASONS frozenset:
#     _NA_FLOW_NO_DATA, _NA_FLOW_NO_COVERAGE

# FactorInputs: add trailing defaulted field
#     flow: FlowAggregate | None = None

def _flow(profile: str, inp: FactorInputs) -> FactorScore:
    if "flow" not in eligible_factors(profile):
        return _na("flow", _NA_PROFILE_INELIGIBLE)
    if inp.flow is None or inp.flow.reason == _NA_FLOW_NO_DATA:
        return _na("flow", _NA_FLOW_NO_DATA)
    if inp.flow.value is None:
        return _na("flow", _NA_FLOW_NO_COVERAGE)
    return FactorScore("flow", inp.flow.value, True, "", 1.0)

# build_factor_scores: append _flow(profile, inp) → 6-tuple
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_known_na_reasons.py tests/monitor/test_factors.py -v`
Expected: PASS (incl. the two-way exhaustiveness tests in test_known_na_reasons — both new constants are referenced in `factors.py`).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/factors.py tests/monitor/test_known_na_reasons.py tests/monitor/test_factors.py
git commit -m "feat(monitor): _flow factor + FactorInputs.flow (defaulted) + 2 N/A reasons [locked: 10 codes]"
```

---

### Task 3.3: `profiles.py` — `active_cn_equity` eligible + D8 weights [LOCKED TEST FLIP]

**Files:**
- Modify: `src/irc/monitor/profiles.py`
- Modify: `tests/monitor/test_profiles.py::test_active_cn_equity_full_vector` **[LOCKED FLIP]**

D8 weights: trend `.25`, valuation `.20`, flow `.15`, heat `.10`, macro_tilt `.15`, constituent `.15` (sum 1.0). Add `"flow"` to `active_cn_equity.eligible`. Other profiles unchanged (flow weight exists ONLY on active_cn_equity — invariant: a profile never weights a factor it can't fill).

**LOCKED FLIP** — `test_active_cn_equity_full_vector`: the eligible set was the 5; now add `flow` → 6.

- [ ] **Step 1: Write the failing test (incl. locked flip)**

```python
# tests/monitor/test_profiles.py — UPDATE [LOCKED FLIP]
def test_active_cn_equity_full_vector():
    assert set(eligible_factors("active_cn_equity")) == {
        "trend", "valuation", "flow", "heat", "macro_tilt", "constituent"
    }


def test_active_cn_equity_flow_weight_is_d8():
    w = default_weights("active_cn_equity")
    assert w == {"trend": 0.25, "valuation": 0.20, "flow": 0.15,
                 "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15}


def test_only_active_cn_equity_has_flow():
    for profile in ("gold", "qdii_global", "qdii_china_us_internet"):
        assert "flow" not in eligible_factors(profile)
```

(`test_default_weights_sum_to_one` and `test_weights_only_cover_eligible_factors` already cover sum==1.0 and the eligible⊇weights invariant — they must stay green after the edit.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_profiles.py -v`
Expected: FAIL — `test_active_cn_equity_full_vector` expects flow not yet present; `test_active_cn_equity_flow_weight_is_d8` fails.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/profiles.py — active_cn_equity ProfileSpec
"active_cn_equity": ProfileSpec(
    lookthrough="active_fund",
    eligible=("trend", "valuation", "flow", "heat", "macro_tilt", "constituent"),
    weights={"trend": 0.25, "valuation": 0.20, "flow": 0.15,
             "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15},
),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_profiles.py -v`
Expected: PASS (incl. sum-to-one and eligible-covers-weights).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/profiles.py tests/monitor/test_profiles.py
git commit -m "feat(monitor): active_cn_equity gains flow (.15) — D8 reweight [locked: 6-factor vector]"
```

---

### Task 3.4: `signal.py` — `_FAMILY_OF["flow"]` + `valuation_flow_conflict` divergence [LOCKED ORACLE FLIP]

**Files:**
- Modify: `src/irc/monitor/signal.py`
- Modify: `tests/monitor/_oracle.py::_FAMILY_OF` **[LOCKED FLIP — test oracle]**
- Test: `tests/monitor/test_signal.py` (append)

Add `_FAMILY_OF["flow"] = "capital-flow"` (new family → richer `present_families`). Add divergence code `valuation_flow_conflict`: cheap valuation (`v ≥ _DIVERGE`) with outflow (`f ≤ −_DIVERGE`), or expensive (`v ≤ −_DIVERGE`) with inflow (`f ≥ _DIVERGE`).

**LOCKED FLIP** — `tests/monitor/_oracle.py:13` `_FAMILY_OF` (a second copy consumed by oracle tests via a bare `_FAMILY_OF[name]` lookup → `KeyError` on a present flow factor if not updated). Add `"flow": "capital-flow"`.

- [ ] **Step 1: Write the failing test (incl. locked oracle flip)**

```python
# tests/monitor/_oracle.py — UPDATE _FAMILY_OF [LOCKED FLIP]
_FAMILY_OF = {
    "trend": "price-momentum", "valuation": "valuation",
    "heat": "crowding", "macro_tilt": "news", "constituent": "news",
    "flow": "capital-flow",   # ADD
}
```

```python
# tests/monitor/test_signal.py — append
from irc.monitor.signal import _divergence, _FAMILY_OF, present_families
from irc.monitor.types import FactorScore


def test_flow_family_is_capital_flow():
    assert _FAMILY_OF["flow"] == "capital-flow"


def _s(name, value):
    return FactorScore(name, value, True, "", 1.0)


def test_valuation_flow_conflict_cheap_but_outflow():
    present = (_s("valuation", 1.0), _s("flow", -0.5))
    assert "valuation_flow_conflict" in _divergence(present)


def test_valuation_flow_conflict_expensive_but_inflow():
    present = (_s("valuation", -1.0), _s("flow", 0.5))
    assert "valuation_flow_conflict" in _divergence(present)


def test_no_conflict_when_aligned():
    present = (_s("valuation", 1.0), _s("flow", 0.5))  # cheap + inflow → aligned
    assert "valuation_flow_conflict" not in _divergence(present)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_signal.py -k "flow or conflict" -v`
Expected: FAIL — `_FAMILY_OF` has no `flow`; `valuation_flow_conflict` not emitted.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/signal.py
_FAMILY_OF = {
    "trend": "price-momentum", "valuation": "valuation",
    "heat": "crowding", "macro_tilt": "news", "constituent": "news",
    "flow": "capital-flow",   # ADD
}

# in _divergence(present), after the trend/macro check, before the pstdev check:
    f = by.get("flow")
    if v is not None and f is not None and (
        (v >= _DIVERGE and f <= -_DIVERGE) or (v <= -_DIVERGE and f >= _DIVERGE)
    ):
        codes.append("valuation_flow_conflict")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_signal.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/signal.py tests/monitor/_oracle.py tests/monitor/test_signal.py
git commit -m "feat(monitor): flow family + valuation_flow_conflict divergence [locked: oracle _FAMILY_OF]"
```

---

### Task 3.5: `render_factors` — `CANONICAL_FACTOR_ORDER` + `valuation_flow_conflict` caveat [LOCKED TEST FLIP]

**Files:**
- Modify: `src/irc/monitor/render_factors.py`
- Modify: `tests/monitor/test_render_factors.py::test_canonical_order_is_locked` **[LOCKED FLIP]**

`CANONICAL_FACTOR_ORDER` → `("trend", "valuation", "flow", "heat", "macro_tilt", "constituent")` (insert flow after valuation). Add `_DIVERGENCE_CAVEATS["valuation_flow_conflict"] = "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入"` (without it `divergence_caveat` falls through to `escape(code)` and shows the raw English code).

**LOCKED FLIP** — `test_canonical_order_is_locked`: the 5-tuple becomes the 6-tuple with flow after valuation.

- [ ] **Step 1: Write the failing test (incl. locked flip)**

```python
# tests/monitor/test_render_factors.py — UPDATE [LOCKED FLIP]
def test_canonical_order_is_locked():
    assert CANONICAL_FACTOR_ORDER == (
        "trend", "valuation", "flow", "heat", "macro_tilt", "constituent"
    )


def test_valuation_flow_conflict_caveat_is_exact():
    assert divergence_caveat("valuation_flow_conflict") == (
        "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: FAIL — order is still the 5-tuple; caveat falls through to escaped raw code.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_factors.py
CANONICAL_FACTOR_ORDER = ("trend", "valuation", "flow", "heat", "macro_tilt", "constituent")

_DIVERGENCE_CAVEATS = {
    "trend_valuation_conflict": "趋势与估值背离：价格动能与估值方向相反",
    "trend_macro_conflict": "趋势与宏观背离：价格动能与宏观信号方向相反",
    "low_factor_agreement": "因子分歧较大：各因子方向/强度不一致",
    "valuation_flow_conflict": "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入",  # ADD
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit + Slice 3 verification**

```bash
git add src/irc/monitor/render_factors.py tests/monitor/test_render_factors.py
git commit -m "feat(monitor): CANONICAL_FACTOR_ORDER + valuation_flow_conflict caveat [locked: 6-tuple]"
```

**Slice 3 verification point:**

Run: `uv run pytest tests/monitor/ tests/monitor/eval/ tests/commands/ -q`
Expected: ALL PASS — including the 4 locked flips (test_known_na_reasons 10 codes, test_profiles 6-factor vector, test_render_factors 6-tuple, _oracle `_FAMILY_OF` flow) AND the regression-check sites (`eval/backtest.py:33` and the 4 test FactorInputs sites stay green because `flow` defaults to `None`). The property/oracle suite (`test_factors_property.py`, hybrid oracle) must pass — the `aggregate_flow` mean math is properties-only; only its coverage gate gets the decision-table oracle.

Run: `uv run ruff check src tests`
Expected: no errors.

Passing looks like: `active_cn_equity` funds now show 6 factor rows; bias reflects flow; `compute_signal` is UNCHANGED (the new factor flows through renorm automatically). Sanity: a cheap+inflow fund leans more `ADD_BIAS` than before; a cheap-but-outflow fund shows the `valuation_flow_conflict` caveat (informational only — bias not held back, per §9).

---

# SLICE 4 — Eval + versioning (LOCKED TESTS FLIP HERE)

Schema bump, holding_metrics trace block, reconciliation oracle, flow coverage health, engine-version bump + forward-eval population isolation.

### Task 4.1: `_ENGINE_VERSION "1"→"2"` + trace `_SCHEMA_VERSION "2"→"3"` [LOCKED TEST FLIPS]

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`_ENGINE_VERSION`)
- Modify: `src/irc/monitor/eval/trace.py` (`_SCHEMA_VERSION`)
- Modify: `tests/monitor/eval/test_trace.py::test_schema_version_is_2` **[LOCKED FLIP — rename + value]**
- Modify: `tests/monitor/test_acceptance_eval.py:79` **[LOCKED FLIP — value]**

`_ENGINE_VERSION` is the eval engine tag (IS bumped — distinct from the package VERSION, which is NOT). The bump tags new ledger rows so the §5.E `target_engine` filter (Task 4.4) can isolate them.

- [ ] **Step 1: Write the failing test (locked flips)**

```python
# tests/monitor/eval/test_trace.py — UPDATE [LOCKED FLIP] (rename + value)
def test_schema_version_is_3():
    t = build_eval_trace((), engine_version="2", run_date="2026-06-19")
    assert t["schema_version"] == "3"
```

```python
# tests/monitor/test_acceptance_eval.py:~79 — UPDATE [LOCKED FLIP]
    assert trace["schema_version"] == "3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_trace.py::test_schema_version_is_3 tests/monitor/test_acceptance_eval.py -v`
Expected: FAIL — `_SCHEMA_VERSION` still "2".

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/trace.py
_SCHEMA_VERSION = "3"
```

```python
# src/irc/commands/monitor_cmd.py
_ENGINE_VERSION = "2"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_trace.py tests/monitor/test_acceptance_eval.py -v`
Expected: PASS. (Other acceptance assertions about the `missing_trading_days` calendar are unaffected.)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/trace.py src/irc/commands/monitor_cmd.py tests/monitor/eval/test_trace.py tests/monitor/test_acceptance_eval.py
git commit -m "feat(monitor): _ENGINE_VERSION 1→2 + schema 2→3 [locked flips]"
```

---

### Task 4.2: `trace.py` — `holding_metrics` block per fund

**Files:**
- Modify: `src/irc/monitor/eval/trace.py`
- Test: `tests/monitor/eval/test_trace.py` (append)

Add a `holding_metrics` block per fund (the board rows + the `FlowAggregate`). The `flow` factor already appears in `factor_scores`/`signal.contributions` automatically. Serialize from `view.holding_metrics` (and `aggregate_flow` over them).

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_trace.py — append
from irc.monitor.holding_metrics import HoldingMetric


def test_trace_emits_holding_metrics_block():
    hm = HoldingMetric("600519", "贵州茅台", 12.0, 30.0, 8.0, 0.8, "expensive",
                       None, 4.0, 3.5, 1.0, None)
    view = _good_view()  # this module's fixture
    view = _replace_view(view, holding_metrics=(hm,))  # helper: dataclasses.replace
    fund = _fund("519069", profile="active_cn_equity")
    bundle = FundTraceBundle("519069", (), (), ())
    gate = apply_eval_gate(view.signal, health=(), gating_stages=GATING_STAGES_M0)
    t = build_eval_trace(((fund, view, gate, bundle),), engine_version="2",
                         run_date="2026-06-19")
    block = t["funds"]["519069"]["holding_metrics"]
    assert block["rows"][0]["symbol"] == "600519"
    assert block["rows"][0]["flow_score"] == 1.0
    assert block["aggregate"]["value"] == 1.0
    assert block["aggregate"]["covered_weight_ratio"] == 1.0
```

(Add `_replace_view = dataclasses.replace` import in the test module.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_trace.py::test_trace_emits_holding_metrics_block -v`
Expected: FAIL with `KeyError: 'holding_metrics'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/trace.py
from irc.monitor.holding_metrics import aggregate_flow  # add import


def _holding_metrics(view: FundView) -> dict:
    metrics = view.holding_metrics
    agg = aggregate_flow(metrics)
    return {
        "rows": [{"symbol": m.symbol, "name": m.name, "weight_pct": m.weight_pct,
                  "pe": m.pe, "pb": m.pb, "pe_percentile": m.pe_percentile,
                  "valuation_state": m.valuation_state, "valuation_reason": m.valuation_reason,
                  "flow_pct_5d": m.flow_pct_5d, "flow_pct_20d": m.flow_pct_20d,
                  "flow_score": m.flow_score, "flow_reason": m.flow_reason}
                 for m in metrics],
        "aggregate": {"value": agg.value, "reason": agg.reason,
                      "covered_weight_ratio": agg.covered_weight_ratio},
    }

# in _fund_entry(...), add to the returned dict:
#     "holding_metrics": _holding_metrics(view),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_trace.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/trace.py tests/monitor/eval/test_trace.py
git commit -m "feat(monitor): trace holding_metrics block (board rows + FlowAggregate)"
```

---

### Task 4.3: `structural.py` — reconciliation oracle + flow-coverage health

**Files:**
- Modify: `src/irc/monitor/eval/structural.py`
- Test: `tests/monitor/eval/test_structural.py` (append)

Reconciliation oracle (spec §5.E): assert the board's per-stock `Σ(wᵢ·sᵢ)/Σ(wᵢ)` over covered rows equals the `flow` factor value (to 4dp) — proves the methodology, not just the display. Flow coverage health: per-fund flow coverage % + `flow_no_data`/`flow_no_coverage` tallies (panel-only, NOT gating — like determinism). Determinism already imports `KNOWN_NA_REASONS`, so the new reasons are recognized automatically.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_structural.py — append
from irc.monitor.eval.structural import flow_reconciliation


def _trace_fund(rows, agg_value, flow_factor_value):
    return {
        "holding_metrics": {"rows": rows, "aggregate": {"value": agg_value,
                                                        "reason": None,
                                                        "covered_weight_ratio": 1.0}},
        "signal": {"contributions": [{"name": "flow", "value": flow_factor_value}]},
    }


def test_flow_reconciliation_passes_when_board_matches_factor():
    rows = [{"weight_pct": 30.0, "flow_score": 1.0},
            {"weight_pct": 10.0, "flow_score": -0.5}]
    t = _trace_fund(rows, 0.625, 0.625)   # (30*1 + 10*-0.5)/40
    assert flow_reconciliation(t).status == "PASS"


def test_flow_reconciliation_fails_on_mismatch():
    rows = [{"weight_pct": 30.0, "flow_score": 1.0}]
    t = _trace_fund(rows, 1.0, 0.5)   # factor value disagrees with board
    assert flow_reconciliation(t).status == "FAIL"


def test_flow_reconciliation_na_factor_is_pass():
    # no flow contribution (factor N/A) → nothing to reconcile → PASS.
    t = {"holding_metrics": {"rows": [], "aggregate": {"value": None}},
         "signal": {"contributions": []}}
    assert flow_reconciliation(t).status == "PASS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_structural.py -k flow_reconciliation -v`
Expected: FAIL with `ImportError: cannot import name 'flow_reconciliation'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/structural.py — append
def _board_flow_value(rows: list[dict]) -> float | None:
    covered = [r for r in rows if r.get("flow_score") is not None]
    cw = sum(r["weight_pct"] for r in covered)
    if cw <= 0.0:
        return None
    return sum(r["weight_pct"] * r["flow_score"] for r in covered) / cw


def _flow_factor_value(t: dict) -> float | None:
    for c in t.get("signal", {}).get("contributions", []):
        if c.get("name") == "flow":
            return c.get("value")
    return None


def flow_reconciliation(t: dict) -> StageHealth:
    """PURE: the board's Σ(wᵢ·sᵢ)/Σ(wᵢ) over covered rows must equal the flow factor
    value (4dp). No flow contribution → nothing to reconcile → PASS (§5.E)."""
    factor_value = _flow_factor_value(t)
    if factor_value is None:
        return StageHealth("flow_reconciliation", "PASS", ())
    board_value = _board_flow_value(t.get("holding_metrics", {}).get("rows", []))
    if board_value is None or abs(round(board_value, 4) - round(factor_value, 4)) >= _EPS:
        return StageHealth("flow_reconciliation", "FAIL",
                           (f"board {board_value} != factor {factor_value}",))
    return StageHealth("flow_reconciliation", "PASS", ())
```

(Add `flow_reconciliation(t)` to the `monitor_signal_health` parts tuple ONLY if §5.E intends it to gate; spec §5.E groups it under the free in-run `eval monitor_signal` reconciliation oracle and the project keeps determinism panel-only. Keep `flow_reconciliation` a standalone PASS/FAIL exposed to the panel, NOT added to the gating parts — mirror `deterministic_health`'s panel-only posture. If the impl agent wires it into a panel row, do so in `build_panel_rows`-adjacent code, never into `GATING_STAGES_*`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_structural.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/structural.py tests/monitor/eval/test_structural.py
git commit -m "feat(monitor): flow_reconciliation oracle (board == factor value, 4dp)"
```

> **§5.E gap CLOSED (2026-06-19):** `flow_coverage_health(t) → StageHealth` added to `structural.py`
> (PASS-always, surfaces `flow_cover`, `pe_cover`, `flow_no_data`, `flow_no_coverage` reasons;
> empty trace → PASS no-raise). Both `flow_reconciliation` and `flow_coverage` wired into
> `build_panel_rows` as new defaulted keyword params (back-compat) and emitted AFTER
> `deterministic_scoring`. `_compute_gates` now returns 5-tuple; production caller updated.
> `test_gate_flip_m1.py` (3 callers) updated for the 5-tuple. Neither stage added to any
> `GATING_STAGES_*` (panel-only invariant tested). 639→651 passed, ruff clean.

---

### Task 4.4: `forward_score.score_forward(target_engine=…)` + `engine_mismatch`

**Files:**
- Modify: `src/irc/monitor/eval/forward_score.py`
- Test: `tests/monitor/eval/test_forward_score.py` (append)

`score_forward(..., target_engine: str | None = None)`: when set, a row whose `manifest_versions.engine != target_engine` is excluded BEFORE the maturity join and counted under `engine_mismatch`. Rows missing the field count as legacy `"0"` → also excluded when a target is set. `target_engine=None` preserves today's no-filter behavior (back-compat).

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_forward_score.py — append
def _ledger_row(engine, fund="a", run="2026-01-10", as_of="2026-01-09"):
    return {"run_date": run, "fund_id": fund, "nav_acc": 1.0, "as_of_date": as_of,
            "raw_status": "ok", "raw_composite": 0.2, "raw_bias": "ADD_BIAS",
            "manifest_versions": {"engine": engine}}


def test_target_engine_excludes_other_engines():
    rows = [_ledger_row("1"), _ledger_row("2")]
    nav = {"a": _nav(40)}
    fwd, excl = score_forward(rows, nav, h=20, today="2026-12-31", target_engine="2")
    assert all(r.run_date == "2026-01-10" for r in fwd)  # only engine-2 rows survive maturity
    assert excl.get("engine_mismatch") == 1               # the engine-1 row excluded


def test_missing_engine_field_counts_as_legacy_and_excluded():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "2026-01-09", "raw_status": "ok", "raw_composite": 0.2,
             "raw_bias": "ADD_BIAS"}]  # no manifest_versions
    fwd, excl = score_forward(rows, {"a": _nav(40)}, h=20, today="2026-12-31",
                              target_engine="2")
    assert excl.get("engine_mismatch") == 1


def test_target_engine_none_is_back_compat_no_filter():
    rows = [_ledger_row("1"), _ledger_row("2")]
    fwd_none, excl_none = score_forward(rows, {"a": _nav(40)}, h=20, today="2026-12-31")
    assert "engine_mismatch" not in excl_none  # no filtering when target is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -k engine -v`
Expected: FAIL with `TypeError: score_forward() got an unexpected keyword argument 'target_engine'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/forward_score.py
_LEGACY_ENGINE = "0"


def _row_engine(r: dict) -> str:
    mv = r.get("manifest_versions") or {}
    return str(mv.get("engine", _LEGACY_ENGINE))


def _filter_engine(rows: list[dict], target_engine: str | None) -> tuple[list[dict], dict[str, int]]:
    """When target_engine is set, drop rows whose engine != target (missing → legacy
    '0'); count drops under engine_mismatch. None → no-op (back-compat)."""
    if target_engine is None:
        return rows, {}
    kept, n = [], 0
    for r in rows:
        if _row_engine(r) == target_engine:
            kept.append(r)
        else:
            n += 1
    return kept, ({"engine_mismatch": n} if n else {})


# update score_forward signature + body:
def score_forward(
    ledger_rows: list[dict], nav_by_fund: dict[str, list[dict]],
    *, h: int, today: str, target_engine: str | None = None,
) -> tuple[list[ForwardRow], dict[str, int]]:
    eng_kept, eng_excl = _filter_engine(ledger_rows, target_engine)
    kept, excl = prefilter_ledger(eng_kept)
    excl = {**eng_excl, **excl}
    # ... existing maturity-join loop unchanged ...
    return out, excl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v`
Expected: PASS (incl. the existing forward-score tests — `target_engine` defaults to None).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/forward_score.py tests/monitor/eval/test_forward_score.py
git commit -m "feat(monitor): score_forward(target_engine) population filter + engine_mismatch"
```

---

### Task 4.5: `runner._target_engine` (numeric max) + wire filter + `details.json.excluded_by_engine`

**Files:**
- Modify: `evals/monitor_forward/runner.py`
- Test: `tests/monitor/eval/test_forward_score.py` (add `_target_engine` unit test) OR `evals/monitor_forward/` test if present

`_target_engine(ledger)` = the MAX engine version present, compared **numerically** (`max(versions, key=int)`), NOT lexicographically (so a future `"10"` beats `"9"`). Deterministic, self-configuring, no external config. Pass it to `score_forward`; write per-engine excluded counts into `details.json` under a new `excluded_by_engine` key (alongside `forward_excluded`). Headline metrics are then computed on the target-engine population only.

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/eval/test_forward_score.py — append (or a runner-level test)
from evals.monitor_forward.runner import _target_engine


def test_target_engine_is_numeric_max_not_lexicographic():
    ledger = [{"manifest_versions": {"engine": "9"}},
              {"manifest_versions": {"engine": "10"}}]
    assert _target_engine(ledger) == "10"  # numeric: 10 > 9 (lexicographic would pick "9")


def test_target_engine_missing_field_is_legacy_zero():
    assert _target_engine([{}, {"manifest_versions": {"engine": "2"}}]) == "2"


def test_target_engine_empty_ledger_is_none():
    assert _target_engine([]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -k target_engine -v`
Expected: FAIL with `ImportError: cannot import name '_target_engine'`.

- [ ] **Step 3: Write minimal implementation**

```python
# evals/monitor_forward/runner.py
from irc.monitor.eval.forward_score import score_forward, _row_engine  # extend import


def _target_engine(ledger: list[dict]) -> str | None:
    """Max engine version present, compared NUMERICALLY (not lexicographically).
    Missing field → legacy '0'. Empty ledger → None (no filter; back-compat)."""
    versions = {_row_engine(r) for r in ledger}
    if not versions:
        return None
    return max(versions, key=int)


# in run(...), replace the score_forward call:
    target_engine = _target_engine(ledger)
    forward_rows, _excl = score_forward(ledger, nav_by_fund, h=FORWARD_H, today=today,
                                        target_engine=target_engine)
# ... and after details["forward_excluded"] = _excl:
    details["excluded_by_engine"] = {"target_engine": target_engine,
                                     "engine_mismatch": _excl.get("engine_mismatch", 0)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v`
Expected: PASS.

- [ ] **Step 5: Commit + Slice 4 verification**

```bash
git add evals/monitor_forward/runner.py tests/monitor/eval/test_forward_score.py
git commit -m "feat(monitor): runner._target_engine (numeric max) + details.excluded_by_engine"
```

**Slice 4 verification point:**

Run: `uv run pytest tests/monitor/ tests/monitor/eval/ tests/commands/ -q`
Expected: ALL PASS — including the locked flips (`test_schema_version_is_3`, acceptance `schema_version == "3"`), the holding_metrics trace block, the reconciliation oracle, and the mixed-engine isolation + single-engine back-compat tests.

Run: `uv run ruff check src tests`
Expected: no errors. Confirm `trace.py`, `forward_score.py`, `structural.py` still < 200 lines after the additions; if `structural.py` crosses, extract the reconciliation helpers.

Passing looks like: `eval_trace.json` is `schema_version "3"` with a `holding_metrics` block; a ledger mixing engine "1"/"2" scores only "2" rows with `engine_mismatch` counted; `details.json` reports `excluded_by_engine`; the reconciliation oracle proves board == factor value.

---

# Final: CHANGELOG + full-suite gate

### Task 5.1: CHANGELOG `[Unreleased]` entry (no VERSION bump)

**Files:**
- Modify: `CHANGELOG.md`

Per project memory: accumulate the feature under `[Unreleased]` at the static VERSION. Do NOT bump the package VERSION.

- [ ] **Step 1: Add the entry**

```markdown
## [Unreleased]

### Added
- **Monitor capital-flow factor + per-stock drill-down (ADR 0019).** New `flow`
  factor on `active_cn_equity` (主力净流入净占比, 5d/20d blended, percent-points,
  bullish-on-inflow, holding-weight-renormalized over the top-5 with a 0.50
  coverage floor); per-stock PB/PE board + flow roll-up embedded in `report.html`
  and written as standalone `drilldown.html`. Eval: trace schema 2→3 with a
  `holding_metrics` block, a board↔factor reconciliation oracle, and forward-eval
  population isolation (`_ENGINE_VERSION` 1→2 + `score_forward(target_engine)` +
  `runner._target_engine` numeric-max + `details.json.excluded_by_engine`). New
  non-caveating N/A reasons `flow_no_data` / `flow_no_coverage`.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): monitor flow factor + per-stock drill-down under [Unreleased]"
```

---

### Task 5.2: Final full-suite + lint gate

- [ ] **Step 1: Run the full monitor + commands + eval suites**

Run: `uv run pytest tests/monitor/ tests/monitor/eval/ tests/commands/ -q`
Expected: ALL PASS. All 6 locked tests flipped (10 N/A codes; 6-factor active_cn_equity vector; 6-tuple CANONICAL order; oracle `_FAMILY_OF["flow"]`; acceptance schema "3"; trace `test_schema_version_is_3`). All 5 regression FactorInputs sites green (flow defaults None).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests`
Expected: no errors (line-length 100, py312).

- [ ] **Step 3: Confirm size budget**

Run: `wc -l src/irc/monitor/flow_fetch.py src/irc/monitor/holding_metrics.py src/irc/monitor/render_drilldown.py`
Expected: each < 200 lines. If any is over, extract helpers into a sibling module and re-run the suite.

Note: `irc monitor` end-to-end needs `MINIMAX_*` env; that is NOT exercised by any test here (effects at edges — fetches injected, inputs pre-loaded). The free in-run `eval monitor_signal` covers determinism + reconciliation without network/LLM.

---

## Self-review notes (spec coverage)

- §5.A `flow_fetch` → Tasks 1.1–1.4 (parse, market routing, byte-stable cache, edge orchestration, never-raises, paced, deduped).
- §5.B `holding_metrics` → Tasks 1.5–1.9 (flow bands percent-point + ratio canary, window blend, per-stock valuation maturity-gate + neg-PE→None, HoldingMetric assembly, aggregate + coverage gate).
- §5.C flow factor + scoring → Tasks 3.1–3.4 (flow_score, _flow + FactorInputs.flow defaulted, profiles D8, signal family + valuation_flow_conflict).
- §5.D report → Tasks 2.2–2.6 (board, roll-up + AUM representativeness, standalone page, card embed + broad-outage note + CANONICAL order in 3.5, EXPLAINER, drilldown.html write).
- §5.E eval → Tasks 4.2–4.5 (schema 3 + holding_metrics block, reconciliation oracle, flow coverage health via KNOWN_NA recognition, score_forward target_engine + engine_mismatch, runner numeric-max + excluded_by_engine).
- §5.F versioning → Task 4.1 (`_ENGINE_VERSION` 1→2).
- §7.1 all 6 locked flips → Tasks 3.2 (10 codes), 3.3 (6-factor vector), 3.5 (6-tuple), 3.4 (oracle _FAMILY_OF), 4.1 (acceptance + trace schema "3").

**Judgment calls (cited):**
- §5.C ambiguity — `flow_score(flow_pct)` (factor layer) vs the per-stock D7 band: resolved to ONE band function (`holding_metrics.flow_band`) re-exported as `factor_maps.flow_score`, avoiding two divergent band definitions. CONTEXT.md flags `aggregate_flow` mean as properties-only with a coverage-gate decision-table oracle — honored.
- §5.E reconciliation oracle gating posture — spec groups it under the free `eval monitor_signal` but does not say it gates; mirrored `deterministic_health`'s PANEL-ONLY posture (never added to `GATING_STAGES_*`) to avoid a new gate the spec didn't sanction.
- §5.D card-embed mechanics — the spec names `_card`; the plan extracts `_drilldown_block(view)` to keep `_card` under the function-size budget and computes `aggregate_flow` at render time (pure) since `FundView` carries only the metrics, not the aggregate.
