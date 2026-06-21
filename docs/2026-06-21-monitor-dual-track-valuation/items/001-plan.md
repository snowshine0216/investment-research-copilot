# Monitor dual-track per-stock valuation + False-Cheap clamp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-base the `irc monitor` look-through valuation factor from a single fund-aggregate state into a bottom-up, per-stock dual-track score (self-history percentile **and** industry-relative richness) with a False-Cheap clamp that neutralizes value traps, flowing through the existing linear composite.

**Architecture:** A new EDGE module `industry_valuation.py` (mirrors `flow_fetch.py`: never raises, per-day JSON cache, direct CN endpoint) feeds industry-average PE + per-symbol industry classification into the PURE core `holding_metrics.py`. The pure core computes per-stock `self_score` (from the existing valuation-state ladder), `industry_score` (additive raw-`r` bands), a `0.60·self + 0.40·industry` blend, a hard-0 clamp in the value-trap quadrant, and aggregates over the full disclosed basket with a NAV-denominator coverage floor of `0.40`. `factors._valuation` consumes the numeric aggregate on the look-through path (index funds keep the state path), gated by a new `ValuationResolution.path` discriminator. The old portfolio-harmonic look-through path is deleted. Eval gains schema-`4` trace fields, determinism recognition, coverage health, and a reconciliation oracle. Engine bumps `"2"→"3"`.

**Tech Stack:** Python 3.12, uv, DuckDB, pandas, AkShare (EastMoney endpoints), pytest, frozen dataclasses (functional/immutable), ruff (line-length 100).

---

## Read before starting

These ground every decision below. Do not re-derive; trust the spec.

- `docs/2026-06-21-monitor-dual-track-valuation/items/001-spec.md` — the grilled spec (D1–D10, §5 components, §7 slice plan, §7.1 locked tests). Binding.
- `docs/2026-06-21-monitor-dual-track-valuation/MASTER-PLAN.md` — build-critical constraints.
- `CONTEXT.md` "Monitor set" + valuation terms; `CLAUDE.md` conventions.

## Binding constants (from the grill — use these EXACT values)

| Constant | Value | Where |
|---|---|---|
| Blend weights | `_SELF_W = 0.60`, `_INDUSTRY_W = 0.40` | `holding_metrics.py` |
| False-Cheap richness threshold | `_FALSE_CHEAP_RICHNESS = 1.2` | `holding_metrics.py` |
| Industry richness bands (on raw `r`) | `r≤0.70→+1.0`, `0.70<r≤0.90→+0.5`, `0.90<r≤1.10→0.0`, `1.10<r<1.20→−0.5`, `r≥1.20→−1.0` | `holding_metrics.py` |
| Monitor coverage floor (NAV denominator) | `_MONITOR_COVERAGE_FLOOR = 0.40` | `holding_metrics.py` (distinct from `lookthrough._COVERAGE_FLOOR=0.50`) |
| Engine version | `"2" → "3"` | `commands/monitor_cmd.py:_ENGINE_VERSION` |
| Trace schema version | `"3" → "4"` | `eval/trace.py:_SCHEMA_VERSION` |
| KNOWN_NA_REASONS count | `10 → 12` (add factor codes `valuation_no_data`, `valuation_no_coverage`) | `factors.py` |

## Invariants (do NOT violate)

- **TDD strict**: red → green → refactor. Never write impl before a failing test.
- **Functional/immutable**: pure cores, frozen dataclasses, `dataclasses.replace`, no argument mutation. Effects (network/file) ONLY in `industry_valuation.py` and `commands/monitor_cmd.py`.
- **Size budget**: files < 200 lines, functions < 20 lines ideal; extract helpers over nesting > 3 levels.
- `industry_no_data` + `false_cheap_clamp` are **per-stock `HoldingMetric` reasons, NEVER added to `KNOWN_NA_REASONS`** (they are not factor reasons).
- **Valuation weight stays `.20`** — NO `profiles.py` weight-vector change.
- The valuation aggregate is computed over the **FULL disclosed basket**; flow stays **top-5** and byte-identical.
- Clamp is **hard-0** when `self_score > 0 AND r ≥ 1.2` (NOT `min(blend, 0)`); clamped stocks count as covered (contribute 0).

---

## File Structure (decomposition)

**Create:**
- `src/irc/monitor/industry_valuation.py` — EDGE fetch + pure parse for industry-avg PE + per-symbol classification (Slice 1).
- `tests/monitor/test_industry_valuation.py` — Slice 1 tests.
- `docs/adr/0020-monitor-dual-track-valuation.md` — ADR (Slice 4).

**Modify:**
- `src/irc/monitor/holding_metrics.py` — dual-track scoring + clamp + `aggregate_valuation` + extended `StockValuation`/`HoldingMetric` + `ValuationAggregate` (Slice 2). Also extend `build_holding_metrics`/`per_stock_metrics` to thread industry inputs (Slice 2/3).
- `src/irc/monitor/valuation.py` — add `ValuationResolution.path`, short-circuit look-through, delete `_resolve_lookthrough` (Slice 3).
- `src/irc/monitor/factors.py` — `_valuation` numeric path, `FactorInputs.valuation_aggregate`, 2 new `_NA_*` constants in `KNOWN_NA_REASONS` (Slice 3).
- `src/irc/commands/monitor_cmd.py` — `_process_fund` wiring (full-basket metrics, industry fetch, gate on `path=="lookthrough"` AND holding_metrics), `_ENGINE_VERSION "2"→"3"` (Slice 3).
- `src/irc/monitor/render_drilldown.py` — board columns + value-trap badge + industry-coverage rollup + sub-0.50 note (Slice 3).
- `src/irc/monitor/eval/trace.py` — `_SCHEMA_VERSION "3"→"4"` + holding_metrics fields + aggregate block (Slice 4).
- `src/irc/monitor/eval/structural.py` — `valuation_reconciliation` oracle + `valuation_coverage_health` (Slice 4).
- `src/irc/monitor/eval/determinism.py` — (verify only; per-stock recognition optional, NOT via KNOWN_NA_REASONS).

**Delete:**
- `src/irc/monitor/lookthrough.py` + `tests/monitor/test_lookthrough.py` (Slice 3).

**Locked-test edits:**
- `tests/monitor/test_known_na_reasons.py` — ten→twelve (Slice 3).
- `tests/monitor/test_render_drilldown.py` — new board columns (Slice 3).
- `tests/monitor/eval/test_trace.py::test_schema_version_is_3` → `_4` (Slice 4).
- `tests/monitor/test_acceptance_eval.py:79` + the second occurrence — `"3"→"4"` (Slice 4).

---

# SLICE 1 — `industry_valuation.py` (EDGE fetch + per-day JSON cache)

**Spec:** §5.A, §7.1. Mirrors `flow_fetch.py` exactly: never raises, parsed rows (no DataFrame on disk), per-day JSON cache with `ok`/`miss` status, **direct** CN endpoint (no proxy), light pacing.

**Two fetchers:**
1. `fetch_industry_pe` — market-wide `stock_board_industry_name_em` (1 call/day, cached). Returns `dict[industry_name -> avg_pe]`.
2. `fetch_stock_industry_map` — per-symbol `stock_individual_info_em` (the flow_fetch volume + contract). Returns `dict[symbol -> industry_name]`.

Reference contract to copy: `src/irc/monitor/flow_fetch.py` (read it first). Use the same `_coerce`, `_cache_path`, `_read_cache`/`_write_cache` atomic pattern, `_PACING_SECONDS`, lazy `import akshare`.

### Task 1.1: Pure parse — industry-PE table

**Files:**
- Create: `src/irc/monitor/industry_valuation.py`
- Test: `tests/monitor/test_industry_valuation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/monitor/test_industry_valuation.py
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from irc.monitor.industry_valuation import (
    parse_industry_pe,
    parse_stock_industry,
    fetch_industry_pe,
    fetch_stock_industry_map,
)


def test_parse_industry_pe_extracts_name_to_pe():
    df = pd.DataFrame({"板块名称": ["银行", "白酒"], "市盈率": ["6.5", "30.2"]})
    out = parse_industry_pe(df)
    assert out == {"银行": 6.5, "白酒": 30.2}


def test_parse_industry_pe_drops_nonpositive_and_nan():
    df = pd.DataFrame({"板块名称": ["亏损业", "正常业", "空值业"],
                       "市盈率": ["-12.0", "10.0", "nan"]})
    out = parse_industry_pe(df)
    assert out == {"正常业": 10.0}  # non-positive + NaN dropped


def test_parse_industry_pe_unexpected_shape_is_empty():
    assert parse_industry_pe(None) == {}
    assert parse_industry_pe(pd.DataFrame()) == {}
    assert parse_industry_pe(pd.DataFrame({"x": [1]})) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_industry_valuation.py::test_parse_industry_pe_extracts_name_to_pe -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.industry_valuation'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/industry_valuation.py
"""EDGE + pure parse: monitor industry valuation leg via AkShare (ADR 0020).

Two cached/day reads, mirroring flow_fetch.py's contract (never raises, parsed
rows, per-day JSON cache, DIRECT CN endpoint, light pacing):

- `stock_board_industry_name_em` — ONE market-wide call → 东财 industry → avg PE.
- `stock_individual_info_em(symbol)` — per-symbol → the symbol's 东财 industry
  (~15-25 deduped cached calls/run, same volume + contract as flow_fetch).

Industry-average PE is from a single 市盈率 column (cap-weighting unverified at
the source; see ADR 0020 denominator-robustness risk). NON-positive / NaN PE →
dropped (→ industry_no_data per-stock). No DataFrame on disk; the cache stores
parsed primitives so the on-disk form is byte-stable. CN endpoints stay DIRECT
(no IRC_HTTPS_PROXY) per ADR 0017.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

_log = logging.getLogger(__name__)

_PE_NAME_COL = "板块名称"
_PE_VALUE_COL = "市盈率"
_INFO_ITEM_COL = "item"
_INFO_VALUE_COL = "value"
_INDUSTRY_ITEM = "行业"


def _coerce_positive(value: object) -> float | None:
    """Pure: finite strictly-positive float, else None. A non-positive or NaN PE
    is meaningless as a denominator → None (→ industry_no_data upstream)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f) or f <= 0.0:
        return None
    return f


def parse_industry_pe(df: pd.DataFrame | None) -> dict[str, float]:
    """Pure: market-wide board table → {industry_name: avg_pe}. Rows with a
    non-positive / NaN / non-numeric 市盈率 are dropped. Unexpected shape → {}."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    if _PE_NAME_COL not in df.columns or _PE_VALUE_COL not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        pe = _coerce_positive(row[_PE_VALUE_COL])
        if pe is None:
            continue
        out[str(row[_PE_NAME_COL]).strip()] = pe
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k parse_industry_pe -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/industry_valuation.py tests/monitor/test_industry_valuation.py
git commit -m "feat(monitor): industry-PE pure parse (slice 1)"
```

### Task 1.2: Pure parse — per-symbol industry classification

**Files:**
- Modify: `src/irc/monitor/industry_valuation.py`
- Test: `tests/monitor/test_industry_valuation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_industry_valuation.py
def test_parse_stock_industry_reads_industry_row():
    # stock_individual_info_em returns a long (item, value) table.
    df = pd.DataFrame({"item": ["总市值", "行业", "上市时间"],
                       "value": ["1.2e12", "酿酒行业", "20010827"]})
    assert parse_stock_industry(df) == "酿酒行业"


def test_parse_stock_industry_missing_industry_is_none():
    df = pd.DataFrame({"item": ["总市值"], "value": ["1.2e12"]})
    assert parse_stock_industry(df) is None
    assert parse_stock_industry(None) is None
    assert parse_stock_industry(pd.DataFrame()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k parse_stock_industry -v`
Expected: FAIL — `ImportError: cannot import name 'parse_stock_industry'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/industry_valuation.py (after parse_industry_pe)
def parse_stock_industry(df: pd.DataFrame | None) -> str | None:
    """Pure: stock_individual_info_em (item,value) long table → the 行业 value,
    or None. Unexpected shape / missing 行业 row → None (→ no industry leg)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if _INFO_ITEM_COL not in df.columns or _INFO_VALUE_COL not in df.columns:
        return None
    for _, row in df.iterrows():
        if str(row[_INFO_ITEM_COL]).strip() == _INDUSTRY_ITEM:
            text = str(row[_INFO_VALUE_COL]).strip()
            return text or None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k parse_stock_industry -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): per-symbol industry classification parse (slice 1)"
```

### Task 1.3: Per-day cache round-trip (industry-PE single table)

**Files:**
- Modify: `src/irc/monitor/industry_valuation.py`
- Test: `tests/monitor/test_industry_valuation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_industry_valuation.py
def test_fetch_industry_pe_caches_and_round_trips(tmp_path: Path):
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return pd.DataFrame({"板块名称": ["银行"], "市盈率": ["6.5"]})

    cache_dir = tmp_path / "industry_pe"
    out1 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                             fetch=fake_fetch, sleep=lambda _s: None)
    out2 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                             fetch=fake_fetch, sleep=lambda _s: None)
    assert out1 == out2 == {"银行": 6.5}
    assert calls["n"] == 1  # second call served from cache
    # on-disk form is sorted-key JSON of primitives (byte-stable)
    payload = json.loads((cache_dir / "2026-06-21.json").read_text(encoding="utf-8"))
    assert payload == {"银行": 6.5}


def test_fetch_industry_pe_never_raises_returns_empty(tmp_path: Path):
    def boom():
        raise RuntimeError("network down")

    out = fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-06-21",
                            fetch=boom, sleep=lambda _s: None)
    assert out == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k fetch_industry_pe -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_industry_pe'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/industry_valuation.py
_PACING_SECONDS = 0.3  # light pacing between live CN calls (ADR 0014 posture)


def _cache_path(cache_dir: Path, today: str) -> Path:
    return cache_dir / f"{today}.json"


def _write_json(cache_dir: Path, today: str, payload: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = _cache_path(cache_dir, today).with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, _cache_path(cache_dir, today))


def _read_json(cache_dir: Path, today: str) -> dict | None:
    path = _cache_path(cache_dir, today)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("industry_valuation: unreadable cache %s; refetching", path,
                     exc_info=True)
        return None


def fetch_industry_pe(
    *, cache_dir: Path, today: str, fetch=None, sleep=time.sleep,
) -> dict[str, float]:
    """EDGE: ONE market-wide stock_board_industry_name_em call/day, cached.
    NEVER raises — any failure → {} (→ industry leg N/A). fetch injectable for
    tests; default lazy-imports akshare (house pattern). CN endpoint DIRECT."""
    cached = _read_json(cache_dir, today)
    if cached is not None:
        return {str(k): float(v) for k, v in cached.items()}
    if fetch is None:
        import akshare as ak  # local import — house pattern
        fetch = ak.stock_board_industry_name_em
    try:
        df = fetch()
    except Exception:  # noqa: BLE001 — degrade to {}, never crash the brief
        _log.warning("industry_valuation: stock_board_industry_name_em failed",
                     exc_info=True)
        return {}
    sleep(_PACING_SECONDS)
    parsed = parse_industry_pe(df)
    _write_json(cache_dir, today, parsed)
    return parsed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k fetch_industry_pe -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): industry-PE per-day cache (slice 1)"
```

### Task 1.4: Per-symbol industry map cache (ok/miss, sorted, deduped)

**Files:**
- Modify: `src/irc/monitor/industry_valuation.py`
- Test: `tests/monitor/test_industry_valuation.py`

This mirrors `flow_fetch.fetch_flow_series` exactly (per-symbol `ok`/`miss` cache, dedup-preserving-order, idempotent within a day).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_industry_valuation.py
def _info_df(industry: str) -> pd.DataFrame:
    return pd.DataFrame({"item": ["行业"], "value": [industry]})


def test_fetch_stock_industry_map_per_symbol_cache_ok_and_miss(tmp_path: Path):
    seen: list[str] = []

    def fake_fetch(symbol):
        seen.append(symbol)
        if symbol == "600519":
            return _info_df("酿酒行业")
        raise RuntimeError("dead symbol")  # 000001 → miss

    cache_dir = tmp_path / "stock_industry"
    out = fetch_stock_industry_map(("600519", "000001", "600519"),
                                   cache_dir=cache_dir, today="2026-06-21",
                                   fetch=fake_fetch, sleep=lambda _s: None)
    assert out == {"600519": "酿酒行业", "000001": None}
    assert seen == ["600519", "000001"]  # deduped, miss not re-fetched in-run
    # cache persists ok+miss; re-run hits NEITHER endpoint
    seen.clear()
    out2 = fetch_stock_industry_map(("600519", "000001"),
                                    cache_dir=cache_dir, today="2026-06-21",
                                    fetch=fake_fetch, sleep=lambda _s: None)
    assert out2 == {"600519": "酿酒行业", "000001": None}
    assert seen == []
    payload = json.loads((cache_dir / "2026-06-21.json").read_text(encoding="utf-8"))
    assert payload["000001"] == {"status": "miss", "industry": None}
    assert payload["600519"] == {"status": "ok", "industry": "酿酒行业"}


def test_fetch_stock_industry_map_per_call_never_raises(tmp_path: Path):
    def boom(symbol):
        raise RuntimeError("x")

    out = fetch_stock_industry_map(("600519",), cache_dir=tmp_path / "si",
                                   today="2026-06-21", fetch=boom, sleep=lambda _s: None)
    assert out == {"600519": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k stock_industry_map -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_stock_industry_map'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/irc/monitor/industry_valuation.py
def _industry_cache_payload(by_symbol: dict[str, str | None]) -> dict[str, dict]:
    """Pure: symbol→industry map → deterministic cache dict (sorted symbols).
    None → status:miss (records a confirmed failure so re-runs skip dead symbols)."""
    return {
        symbol: ({"status": "ok", "industry": by_symbol[symbol]}
                 if by_symbol[symbol] is not None
                 else {"status": "miss", "industry": None})
        for symbol in sorted(by_symbol)
    }


def _load_industry_cache(payload: dict[str, dict]) -> dict[str, str | None]:
    """Pure: cache dict → symbol→(industry|None) map."""
    out: dict[str, str | None] = {}
    for symbol, entry in payload.items():
        out[symbol] = entry.get("industry") if entry.get("status") == "ok" else None
    return out


def _read_industry_cache(cache_dir: Path, today: str) -> dict[str, str | None]:
    payload = _read_json(cache_dir, today)
    return _load_industry_cache(payload) if payload else {}


def _fetch_one_industry(symbol: str, fetch, *, sleep) -> str | None:
    """EDGE: one symbol → industry or None. NEVER raises. CN endpoint DIRECT."""
    try:
        df = fetch(symbol=symbol)
    except Exception:  # noqa: BLE001 — degrade to None (industry_no_data)
        _log.warning("industry_valuation: stock_individual_info_em failed for %s",
                     symbol, exc_info=True)
        return None
    sleep(_PACING_SECONDS)
    return parse_stock_industry(df)


def fetch_stock_industry_map(
    symbols: tuple[str, ...], *, cache_dir: Path, today: str,
    fetch=None, sleep=time.sleep,
) -> dict[str, str | None]:
    """EDGE: dedup symbols → cache-first per-day per-symbol fetch → byte-stable
    cache write (ok/miss). Idempotent within a day. Same contract + volume as
    flow_fetch.fetch_flow_series. fetch injectable; default lazy-imports akshare."""
    if fetch is None:
        import akshare as ak  # local import — house pattern
        fetch = ak.stock_individual_info_em
    cached = _read_industry_cache(cache_dir, today)
    out: dict[str, str | None] = {}
    dirty = False
    for symbol in dict.fromkeys(symbols):  # dedup, preserve order
        if symbol in cached:
            out[symbol] = cached[symbol]
            continue
        out[symbol] = _fetch_one_industry(symbol, fetch, sleep=sleep)
        dirty = True
    if dirty:
        _write_json(cache_dir, today, _industry_cache_payload({**cached, **out}))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -v`
Expected: PASS (all 9 tests).

- [ ] **Step 5: Verify size + lint, then commit**

Run: `uv run ruff check src/irc/monitor/industry_valuation.py tests/monitor/test_industry_valuation.py`
Expected: no errors. Confirm `industry_valuation.py` is < 200 lines (`wc -l`).

```bash
git add -A && git commit -m "feat(monitor): per-symbol industry-map cache + slice 1 complete"
```

---

# SLICE 2 — Dual-track scoring + clamp + `aggregate_valuation` in `holding_metrics.py` (PURE)

**Spec:** §5.B, §7 step 2. All pure. No bias wiring yet (Slice 3). Read `src/irc/monitor/holding_metrics.py` and `src/irc/monitor/factor_maps.py` (`valuation_state_score`) first.

**Key design:**
- `self_score = valuation_state_score(stock.valuation_state)` — reuses the existing `_VALUATION_MAP` ladder (`cheap→1.0 … very_expensive→−1.0`). `valuation_state is None` → `valuation_state_score(None)` → KeyError? NO: read `factor_maps.valuation_state_score` — it is `_VALUATION_MAP.get(state)`; but `state` is typed `str`. Passing `None` returns `None` via `.get`. Confirm with a unit test (Task 2.1). `self_score is None` → no `val_score` → excluded from aggregate.
- `industry_score` from `r = stock_pe / industry_avg_pe` via the additive bands.
- `val_score = 0.60·self + 0.40·industry`; industry-N/A → `val_score = self_score`.
- Clamp: `self_score > 0 AND r ≥ 1.2` → `val_score = 0.0`, `false_cheap=True`.
- `aggregate_valuation`: full basket, `Σwᵢvᵢ/Σwᵢ` over non-None `val_score`, NAV-denominator coverage `Σ covered weight_pct / 100.0`, floor `0.40`.

### Task 2.1: `valuation_state_score(None)` returns None (guard the self leg)

**Files:**
- Test: `tests/monitor/test_factor_maps.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_factor_maps.py
def test_valuation_state_score_none_state_is_none():
    from irc.monitor.factor_maps import valuation_state_score
    assert valuation_state_score(None) is None  # self-leg N/A path
```

- [ ] **Step 2: Run test to verify it fails OR passes**

Run: `uv run pytest tests/monitor/test_factor_maps.py::test_valuation_state_score_none_state_is_none -v`
Expected: PASS already (`.get(None)` → `None`). If it FAILS (a typing-narrowed `if state not in …` raises), widen the signature to `state: str | None` in `factor_maps.valuation_state_score` and return `None` for falsy input. Do NOT change the map.

- [ ] **Step 3: (only if needed) widen signature**

```python
# src/irc/monitor/factor_maps.py — only if step 2 failed
def valuation_state_score(state: str | None) -> float | None:
    """Fixed map; None for an unrecognised/None state (→ N/A upstream)."""
    if state is None:
        return None
    return _VALUATION_MAP.get(state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_factor_maps.py::test_valuation_state_score_none_state_is_none -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test(monitor): lock valuation_state_score(None)->None (slice 2)"
```

### Task 2.2: `industry_score` banding (additive raw-`r`, asymmetric)

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
import pytest as _pt
from irc.monitor.holding_metrics import (
    industry_band, _FALSE_CHEAP_RICHNESS, _SELF_W, _INDUSTRY_W,
    _MONITOR_COVERAGE_FLOOR,
)


@_pt.mark.parametrize("r,score", [
    (0.50, 1.0), (0.70, 1.0),         # r<=0.70 → +1.0
    (0.80, 0.5), (0.90, 0.5),         # 0.70<r<=0.90 → +0.5
    (1.00, 0.0), (1.10, 0.0),         # 0.90<r<=1.10 → 0.0
    (1.15, -0.5), (1.19, -0.5),       # 1.10<r<1.20 → -0.5
    (1.20, -1.0), (2.00, -1.0),       # r>=1.20 → -1.0 (pinned to _FALSE_CHEAP_RICHNESS)
])
def test_industry_band_asymmetric_raw_r(r, score):
    assert industry_band(r) == score


def test_named_constants_locked():
    assert _SELF_W == 0.60 and _INDUSTRY_W == 0.40
    assert _FALSE_CHEAP_RICHNESS == 1.2
    assert _MONITOR_COVERAGE_FLOOR == 0.40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k "industry_band or named_constants" -v`
Expected: FAIL — `ImportError: cannot import name 'industry_band'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/holding_metrics.py — add near the top (after _NA_FLOW_* constants)

# Dual-track valuation constants (ADR 0020 D3/D5/D9/D10 — priors, never auto-tuned).
_SELF_W = 0.60
_INDUSTRY_W = 0.40
_FALSE_CHEAP_RICHNESS = 1.2  # r >= this → max rich-vs-peers AND clamp trigger
# Monitor coverage floor (D10/Q8): NAV-denominator, distinct from
# lookthrough._COVERAGE_FLOOR=0.50 — the monitor valuation is a 0.20-weight
# research lean, not a publishability gate.
_MONITOR_COVERAGE_FLOOR = 0.40

_NA_VALUATION_NO_DATA = "valuation_no_data"
_NA_VALUATION_NO_COVERAGE = "valuation_no_coverage"
# Per-stock HoldingMetric reasons (NOT factor reasons, NEVER in KNOWN_NA_REASONS).
_REASON_INDUSTRY_NO_DATA = "industry_no_data"
_REASON_FALSE_CHEAP_CLAMP = "false_cheap_clamp"


def industry_band(r: float) -> float:
    """Pure: industry richness r = stock_pe/industry_avg_pe → score in [-1,+1].
    Cheaper-than-peers → positive. ASYMMETRIC bands (slow to call cheap, quick to
    withhold cheap). The -1.0 edge is pinned to _FALSE_CHEAP_RICHNESS so ONE
    threshold governs both 'max rich-vs-peers' and the clamp trigger."""
    if r <= 0.70:
        return 1.0
    if r <= 0.90:
        return 0.5
    if r <= 1.10:
        return 0.0
    if r < _FALSE_CHEAP_RICHNESS:
        return -0.5
    return -1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k "industry_band or named_constants" -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): industry richness banding (slice 2)"
```

### Task 2.3: Per-stock dual-track score + clamp — `dual_track_score`

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

This computes the per-stock `(industry_score, val_score, false_cheap, industry_reason)` given a `self_score`, a `stock_pe`, and an `industry_avg_pe`. Pure, no dataclass yet.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from irc.monitor.holding_metrics import dual_track_score, DualTrack


def test_dual_track_blend_self_and_industry():
    # self=+1.0 (cheap vs own), r=0.5 (cheap vs peers, industry=+1.0)
    # blend = 0.6*1.0 + 0.4*1.0 = 1.0
    dt = dual_track_score(self_score=1.0, stock_pe=10.0, industry_avg_pe=20.0)
    assert dt == DualTrack(industry_score=1.0, val_score=1.0,
                           false_cheap=False, industry_reason=None,
                           industry_richness=0.5)


def test_dual_track_industry_na_falls_to_self_only():
    # No industry PE → industry leg N/A → val_score == self_score, reason set.
    dt = dual_track_score(self_score=0.5, stock_pe=10.0, industry_avg_pe=None)
    assert dt.val_score == 0.5
    assert dt.industry_score is None
    assert dt.industry_reason == "industry_no_data"
    assert dt.industry_richness is None
    assert dt.false_cheap is False


def test_dual_track_industry_na_when_pe_nonpositive_or_missing():
    assert dual_track_score(self_score=0.5, stock_pe=None,
                            industry_avg_pe=20.0).industry_reason == "industry_no_data"
    assert dual_track_score(self_score=0.5, stock_pe=10.0,
                            industry_avg_pe=0.0).industry_reason == "industry_no_data"


def test_dual_track_self_na_yields_no_score():
    # self_score None (immature/non-positive PE) → val_score None → excluded.
    dt = dual_track_score(self_score=None, stock_pe=10.0, industry_avg_pe=20.0)
    assert dt.val_score is None
    assert dt.false_cheap is False


def test_false_cheap_clamp_hard_zero():
    # self=+0.5 (cheap vs own) AND r=1.5 (>=1.2 rich vs peers) → hard-0, flagged.
    dt = dual_track_score(self_score=0.5, stock_pe=30.0, industry_avg_pe=20.0)
    assert dt.val_score == 0.0          # hard-0, NOT min(blend,0)
    assert dt.false_cheap is True
    assert dt.industry_reason == "false_cheap_clamp"


def test_false_cheap_clamp_boundary_at_richness_threshold():
    # r EXACTLY 1.2 with self>0 → clamp fires (>= boundary).
    dt = dual_track_score(self_score=1.0, stock_pe=24.0, industry_avg_pe=20.0)
    assert dt.val_score == 0.0 and dt.false_cheap is True


def test_clamp_does_not_fire_when_self_not_cheap():
    # self=-0.5 (expensive vs own), r=1.5 → no clamp; blend = 0.6*-0.5+0.4*-1.0=-0.7
    dt = dual_track_score(self_score=-0.5, stock_pe=30.0, industry_avg_pe=20.0)
    assert dt.false_cheap is False
    assert dt.val_score == _pt.approx(-0.7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k dual_track -v`
Expected: FAIL — `ImportError: cannot import name 'dual_track_score'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/holding_metrics.py — add after industry_band

@dataclass(frozen=True)
class DualTrack:
    industry_score: float | None
    val_score: float | None
    false_cheap: bool
    industry_reason: str | None  # None | industry_no_data | false_cheap_clamp
    industry_richness: float | None


def _industry_leg(stock_pe: float | None, industry_avg_pe: float | None):
    """(richness, score) or (None, None) when the industry denominator is unusable."""
    if (stock_pe is None or stock_pe <= 0.0
            or industry_avg_pe is None or industry_avg_pe <= 0.0):
        return None, None
    r = stock_pe / industry_avg_pe
    return r, industry_band(r)


def dual_track_score(
    *, self_score: float | None, stock_pe: float | None, industry_avg_pe: float | None,
) -> DualTrack:
    """Pure: 0.60·self + 0.40·industry, with industry-N/A → self-only and a
    hard-0 False-Cheap clamp (self>0 AND r>=1.2). self-N/A → no val_score."""
    r, industry_score = _industry_leg(stock_pe, industry_avg_pe)
    if self_score is None:                       # self leg N/A → no score
        return DualTrack(industry_score, None, False, None, r)
    if industry_score is None:                   # industry leg N/A → self-only
        return DualTrack(None, self_score, False, _REASON_INDUSTRY_NO_DATA, None)
    if self_score > 0.0 and r >= _FALSE_CHEAP_RICHNESS:  # value-trap quadrant
        return DualTrack(industry_score, 0.0, True, _REASON_FALSE_CHEAP_CLAMP, r)
    blend = _SELF_W * self_score + _INDUSTRY_W * industry_score
    return DualTrack(industry_score, blend, False, None, r)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k dual_track -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): per-stock dual-track score + False-Cheap clamp (slice 2)"
```

### Task 2.4: Extend `StockValuation` + `HoldingMetric` + `per_stock_metrics` with dual-track fields

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

Extend the two frozen dataclasses with the dual-track fields and have `per_stock_metrics` thread `industry_pe_by_industry` + `industry_by_symbol` to populate them. Keep flow on top-5 untouched.

`StockValuation` gains: `industry`, `industry_pe`, `industry_richness`, `industry_score`, `self_score`, `val_score`, `false_cheap` (the `valuation_reason` field already exists; reuse it for the per-stock self reason; add a separate `industry_reason`).

`HoldingMetric` gains: `industry`, `industry_pe`, `industry_richness`, `industry_score`, `self_score`, `val_score`, `false_cheap`, `industry_reason` — all **trailing, defaulted** so existing constructors (tests/trace) stay green.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from irc.monitor.holding_metrics import per_stock_valuation_dual, StockValuation


def _mature_rising_series(code="600519"):
    from datetime import date
    base = date(2025, 1, 1).toordinal()
    pts = tuple((date.fromordinal(base + 2 * i).isoformat(), 18.0 + i * 0.01, 2.0)
                for i in range(200))
    return MetricSeries(code=code, source="eastmoney", points=pts)


def test_per_stock_valuation_dual_populates_industry_fields():
    series = _mature_rising_series("600519")  # latest PE is max → state very_expensive
    sv = per_stock_valuation_dual("600519", series, industry="酿酒行业",
                                  industry_avg_pe=10.0)
    assert isinstance(sv, StockValuation)
    assert sv.valuation_state == "very_expensive"  # self leg
    assert sv.self_score == -1.0                    # very_expensive → -1.0
    assert sv.industry == "酿酒行业"
    assert sv.industry_pe == 10.0
    assert sv.industry_score is not None            # stock_pe/10 banded
    assert sv.val_score is not None


def test_per_stock_valuation_dual_industry_na_self_only():
    series = _mature_rising_series("600519")
    sv = per_stock_valuation_dual("600519", series, industry=None, industry_avg_pe=None)
    assert sv.self_score == -1.0
    assert sv.val_score == -1.0                      # self-only fallback
    assert sv.industry_reason == "industry_no_data"
```

Note `per_stock_valuation_dual`'s `stock_pe` for the industry leg is the latest positive PE (`_latest_value(series, 1)`). When `series` is None → delegate to the existing `per_stock_valuation` shape (no series → all-None, no score).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k per_stock_valuation_dual -v`
Expected: FAIL — `ImportError: cannot import name 'per_stock_valuation_dual'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/holding_metrics.py — REPLACE the StockValuation dataclass with:

@dataclass(frozen=True)
class StockValuation:
    """Per-stock dual-track valuation: self-history PE percentile/state/score +
    industry-relative richness/score + blended val_score + clamp flag."""
    pe: float | None
    pb: float | None
    pe_percentile: float | None
    valuation_state: str | None
    valuation_reason: str | None  # self leg: None|pe_not_positive|pe_immature|no_series
    self_score: float | None = None
    industry: str | None = None
    industry_pe: float | None = None
    industry_richness: float | None = None
    industry_score: float | None = None
    val_score: float | None = None
    false_cheap: bool = False
    industry_reason: str | None = None  # None|industry_no_data|false_cheap_clamp


def per_stock_valuation_dual(
    code: str, series: MetricSeries | None, *,
    industry: str | None, industry_avg_pe: float | None,
) -> StockValuation:
    """Pure: the #168 self-history StockValuation EXTENDED with the dual-track
    legs. self_score = valuation_state_score(state); industry leg from latest
    positive PE vs industry_avg_pe; blend + clamp via dual_track_score."""
    base = per_stock_valuation(code, series)            # self leg (existing #168 fn)
    self_score = valuation_state_score(base.valuation_state)
    dt = dual_track_score(self_score=self_score, stock_pe=base.pe,
                          industry_avg_pe=industry_avg_pe)
    return StockValuation(
        pe=base.pe, pb=base.pb, pe_percentile=base.pe_percentile,
        valuation_state=base.valuation_state, valuation_reason=base.valuation_reason,
        self_score=self_score, industry=industry, industry_pe=industry_avg_pe,
        industry_richness=dt.industry_richness, industry_score=dt.industry_score,
        val_score=dt.val_score, false_cheap=dt.false_cheap,
        industry_reason=dt.industry_reason,
    )
```

Add the import at the top of `holding_metrics.py`:

```python
from irc.monitor.factor_maps import valuation_state_score
```

> NOTE on circular import: `factor_maps.py` imports `flow_band` FROM `holding_metrics`. Adding `holding_metrics → factor_maps` would cycle. AVOID by importing `valuation_state_score` **inside** `per_stock_valuation_dual` (function-local import), matching the house pattern used in `valuation.py:_resolve_lookthrough`. Replace the top-level import above with a function-local `from irc.monitor.factor_maps import valuation_state_score` at the start of `per_stock_valuation_dual` and `aggregate_valuation` is unaffected. Confirm no cycle by running the import in step 4.

- [ ] **Step 4: Run test to verify it passes (and no import cycle)**

Run: `uv run python -c "import irc.monitor.holding_metrics, irc.monitor.factor_maps"` (Expected: no ImportError)
Run: `uv run pytest tests/monitor/test_holding_metrics.py -k per_stock_valuation_dual -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): dual-track StockValuation + per_stock_valuation_dual (slice 2)"
```

### Task 2.5: Extend `HoldingMetric` + `per_stock_metrics`/`build_holding_metrics` to thread industry inputs

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
def test_per_stock_metrics_threads_industry_inputs():
    class _H:
        def __init__(self, s, n, w):
            self.symbol, self.name_cn, self.weight_pct = s, n, w
    holdings = (_H("600519", "贵州茅台", 35.0),)
    series = {"600519": _mature_rising_series("600519")}
    metrics = per_stock_metrics(
        holdings, series, flow_series_by_code={},
        industry_by_symbol={"600519": "酿酒行业"},
        industry_pe_by_industry={"酿酒行业": 10.0},
    )
    m = metrics[0]
    assert m.industry == "酿酒行业"
    assert m.industry_pe == 10.0
    assert m.val_score is not None
    assert m.self_score == -1.0  # very_expensive


def test_per_stock_metrics_backward_compatible_without_industry():
    # The two new params default empty → industry leg N/A, val_score == self_score.
    class _H:
        def __init__(self, s, n, w):
            self.symbol, self.name_cn, self.weight_pct = s, n, w
    holdings = (_H("600519", "贵州茅台", 35.0),)
    series = {"600519": _mature_rising_series("600519")}
    metrics = per_stock_metrics(holdings, series, flow_series_by_code={})
    assert metrics[0].industry_reason == "industry_no_data"
    assert metrics[0].val_score == metrics[0].self_score == -1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k per_stock_metrics_threads -v`
Expected: FAIL — `TypeError: per_stock_metrics() got an unexpected keyword argument 'industry_by_symbol'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/holding_metrics.py — REPLACE the HoldingMetric dataclass + per_stock_metrics + build_holding_metrics

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
    # Dual-track valuation (trailing-defaulted for back-compat).
    self_score: float | None = None
    industry: str | None = None
    industry_pe: float | None = None
    industry_richness: float | None = None
    industry_score: float | None = None
    val_score: float | None = None
    false_cheap: bool = False
    industry_reason: str | None = None


def per_stock_metrics(
    top_holdings, series_by_code, flow_series_by_code,
    *, industry_by_symbol: dict | None = None,
    industry_pe_by_industry: dict | None = None,
) -> tuple[HoldingMetric, ...]:
    """Pure: holdings + per-code PE/PB series + per-code flow series + optional
    industry maps → HoldingMetric rows. Industry maps default empty (back-compat:
    industry leg N/A → val_score == self_score)."""
    ind_by_sym = industry_by_symbol or {}
    ind_pe = industry_pe_by_industry or {}
    out: list[HoldingMetric] = []
    for h in top_holdings:
        industry = ind_by_sym.get(h.symbol)
        industry_avg_pe = ind_pe.get(industry) if industry is not None else None
        val = per_stock_valuation_dual(
            h.symbol, series_by_code.get(h.symbol),
            industry=industry, industry_avg_pe=industry_avg_pe)
        p5, p20, score, reason = _flow_metric(flow_series_by_code.get(h.symbol))
        out.append(HoldingMetric(
            symbol=h.symbol, name=h.name_cn, weight_pct=h.weight_pct,
            pe=val.pe, pb=val.pb, pe_percentile=val.pe_percentile,
            valuation_state=val.valuation_state, valuation_reason=val.valuation_reason,
            flow_pct_5d=p5, flow_pct_20d=p20, flow_score=score, flow_reason=reason,
            self_score=val.self_score, industry=val.industry, industry_pe=val.industry_pe,
            industry_richness=val.industry_richness, industry_score=val.industry_score,
            val_score=val.val_score, false_cheap=val.false_cheap,
            industry_reason=val.industry_reason,
        ))
    return tuple(out)


def build_holding_metrics(
    top_holdings, series_by_code, flow_series_by_code,
    *, industry_by_symbol: dict | None = None,
    industry_pe_by_industry: dict | None = None,
) -> tuple[HoldingMetric, ...]:
    """Pure assembly entry called from the edge (monitor_cmd). Effects
    (fetch_flow_series, _stock_series_by_code, industry fetch) stay in monitor_cmd."""
    return per_stock_metrics(
        top_holdings, series_by_code, flow_series_by_code,
        industry_by_symbol=industry_by_symbol,
        industry_pe_by_industry=industry_pe_by_industry,
    )
```

- [ ] **Step 4: Run test to verify it passes (and existing holding_metrics tests stay green)**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -v`
Expected: PASS (all, incl. existing flow/valuation tests — the new fields default).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): thread industry inputs into HoldingMetric (slice 2)"
```

### Task 2.6: `aggregate_valuation` + `ValuationAggregate` (full basket, NAV floor 0.40)

**Files:**
- Modify: `src/irc/monitor/holding_metrics.py`
- Test: `tests/monitor/test_holding_metrics.py`

Mirror `aggregate_flow`'s **value** shape (`Σwᵢvᵢ/Σwᵢ` over covered) but the **coverage gate uses the NAV denominator** `Σ covered weight_pct / 100.0` (NOT flow's covered/total). Clamped stocks (`val_score==0.0`, covered) count as covered.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_holding_metrics.py
from irc.monitor.holding_metrics import aggregate_valuation, ValuationAggregate


def _hm(symbol, weight, val_score):
    # minimal HoldingMetric with a val_score (other fields irrelevant to aggregate).
    return HoldingMetric(symbol=symbol, name=symbol, weight_pct=weight,
                         pe=None, pb=None, pe_percentile=None, valuation_state=None,
                         valuation_reason=None, flow_pct_5d=None, flow_pct_20d=None,
                         flow_score=None, flow_reason=None, val_score=val_score)


def test_aggregate_valuation_value_is_nav_weighted_mean():
    # 50%@+1.0, 30%@-1.0 covered; NAV coverage = (50+30)/100 = 0.80 >= 0.40.
    # value = (50*1 + 30*-1)/(50+30) = 0.25
    metrics = (_hm("a", 50.0, 1.0), _hm("b", 30.0, -1.0))
    agg = aggregate_valuation(metrics)
    assert agg == ValuationAggregate(value=0.25, reason=None, covered_weight_ratio=0.80)


def test_aggregate_valuation_clamped_counts_as_covered_zero():
    # a clamped stock has val_score 0.0 (NOT None) → covered, contributes 0.
    metrics = (_hm("a", 50.0, 0.0), _hm("b", 30.0, 1.0))
    agg = aggregate_valuation(metrics)
    # value = (50*0 + 30*1)/(80) = 0.375 ; coverage 0.80
    assert agg.value == _pt.approx(0.375)
    assert agg.covered_weight_ratio == _pt.approx(0.80)


def test_aggregate_valuation_zero_covered_is_no_data():
    metrics = (_hm("a", 50.0, None), _hm("b", 30.0, None))
    agg = aggregate_valuation(metrics)
    assert agg.value is None and agg.reason == "valuation_no_data"
    assert agg.covered_weight_ratio == 0.0


def test_aggregate_valuation_below_nav_floor_is_no_coverage():
    # only 35% NAV covered < 0.40 floor → valuation_no_coverage.
    metrics = (_hm("a", 35.0, 1.0), _hm("b", 30.0, None))
    agg = aggregate_valuation(metrics)
    assert agg.value is None and agg.reason == "valuation_no_coverage"
    assert agg.covered_weight_ratio == _pt.approx(0.35)


def test_aggregate_valuation_exactly_at_floor_is_covered():
    # exactly 0.40 NAV covered → accepted (>= floor, matches _meets_floor).
    metrics = (_hm("a", 40.0, 1.0),)
    agg = aggregate_valuation(metrics)
    assert agg.value == 1.0 and agg.reason is None
    assert agg.covered_weight_ratio == _pt.approx(0.40)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k aggregate_valuation -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate_valuation'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/holding_metrics.py — add (near aggregate_flow)

@dataclass(frozen=True)
class ValuationAggregate:
    value: float | None
    reason: str | None
    covered_weight_ratio: float


def aggregate_valuation(metrics: tuple[HoldingMetric, ...]) -> ValuationAggregate:
    """Pure: Σ(wᵢ·val_scoreᵢ)/Σ(wᵢ) over holdings with a non-None val_score
    (weight-renormalized; clamped stocks have val_score 0.0 → covered, contribute 0).
    Coverage uses the NAV denominator (D10): covered_weight_ratio = Σ covered
    weight_pct / 100.0. Zero covered → valuation_no_data; ratio < 0.40 (the
    MONITOR floor, distinct from lookthrough's 0.50) → valuation_no_coverage."""
    covered = [m for m in metrics if m.val_score is not None]
    covered_w = sum(m.weight_pct for m in covered)
    ratio = covered_w / 100.0
    if not covered or covered_w <= 0.0:
        return ValuationAggregate(None, _NA_VALUATION_NO_DATA, ratio)
    if ratio < _MONITOR_COVERAGE_FLOOR:
        return ValuationAggregate(None, _NA_VALUATION_NO_COVERAGE, ratio)
    value = sum(m.weight_pct * m.val_score for m in covered) / covered_w
    return ValuationAggregate(value, None, ratio)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_holding_metrics.py -k aggregate_valuation -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Full Slice-2 regression + lint + commit**

Run: `uv run pytest tests/monitor/test_holding_metrics.py tests/monitor/test_factor_maps.py -v`
Expected: PASS (all).
Run: `uv run ruff check src/irc/monitor/holding_metrics.py tests/monitor/test_holding_metrics.py`
Expected: no errors. Confirm `holding_metrics.py` line count (if near 200, extract `_industry_leg`/banding to a sub-helper — but it should fit).

```bash
git add -A && git commit -m "feat(monitor): aggregate_valuation NAV-floor coverage (slice 2 complete)"
```

---

# SLICE 3 — Factor re-base → bias + report + engine bump

**Spec:** §5.C, §5.D, §5.F, §7 step 3, §7.1. This is the HIGH-RISK slice (dark-factor trap). The integration test MUST drive the real `_process_fund`.

Order: (3.1) `ValuationResolution.path` + short-circuit, (3.2) delete dead path, (3.3) `factors._valuation` numeric path + `FactorInputs` field + KNOWN_NA_REASONS, (3.4) `_process_fund` wiring + engine bump (end-to-end integration test), (3.5) board columns + badge.

### Task 3.1: Add `ValuationResolution.path` + short-circuit look-through

**Files:**
- Modify: `src/irc/monitor/valuation.py`
- Test: `tests/monitor/test_valuation.py`

`path: Literal["index","lookthrough"]` is a **trailing-defaulted** field so existing `ValuationResolution(state, cached, reason)` constructors stay green. The look-through branch short-circuits: returns `(None, False, None, path="lookthrough")` WITHOUT computing the old portfolio-harmonic state.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_valuation.py
def test_lookthrough_branch_returns_path_lookthrough(tmp_path):
    # tracked_index is None → look-through path; short-circuit: state None, NO
    # portfolio-harmonic computation. path tags it for the numeric-aggregate feed.
    con = duckdb.connect(str(tmp_path / "p1.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519069", None)
    res = resolve_valuation_state(_fund("519069", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.path == "lookthrough"
    assert res.state is None and res.cached is False and res.reason is None
    con.close()


def test_index_branch_returns_path_index(tmp_path):
    con = duckdb.connect(str(tmp_path / "p2.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi300", pairs)
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.path == "index"
    assert res.state == "very_expensive" and res.cached is True
    con.close()


def test_resolution_path_defaults_to_index_for_back_compat():
    r = ValuationResolution(state="cheap", cached=True, reason=None)
    assert r.path == "index"  # trailing default keeps old 3-arg constructors green
```

Also DELETE these now-invalid look-through tests from `tests/monitor/test_valuation.py` (the portfolio-harmonic path is being removed in 3.2; they will be replaced by the bottom-up integration tests): `test_lookthrough_sufficient_coverage_returns_state`, `test_lookthrough_coverage_below_floor_is_na`, `test_lookthrough_low_percentile_is_cheap`, `test_lookthrough_holdings_but_no_stock_valuations_is_na`, `test_lookthrough_non_ashare_holding_is_na`, `test_lookthrough_no_snapshot_is_na`, and `test_lookthrough_branch_is_na_stub`. Keep `test_index_*`, `test_china_internet_*`, `test_index_anchored_unactivated_sector_*`, `test_unknown_fund_*`, `test_index_path_unchanged_by_lookthrough` (the latter: update its assertion — the look-through no longer produces a state, so the index path is still very_expensive; the regression intent holds), and the degrade tests.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_valuation.py -k "path_" -v`
Expected: FAIL — `AttributeError: 'ValuationResolution' object has no attribute 'path'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/valuation.py — modify

from typing import Literal  # add to imports

@dataclass(frozen=True)
class ValuationResolution:
    """Frozen result of resolving one fund's monitor valuation state.

    path: which branch resolved — "index" (state path) or "lookthrough" (the
          numeric bottom-up aggregate is fed downstream, NOT this state).
    """
    state: str | None
    cached: bool
    reason: str | None
    path: Literal["index", "lookthrough"] = "index"


def _resolve_index(con: duckdb.DuckDBPyConnection, tracked_index: str) -> ValuationResolution:
    _, _, _, pe_pct, _ = _index_valuation_metrics(con, tracked_index)
    state = percentile_to_valuation_state(pe_pct)
    if state is None:
        return ValuationResolution(None, False, _NA_NO_ANCHOR, path="index")
    return ValuationResolution(state, True, None, path="index")


def _resolve(fund, *, con: duckdb.DuckDBPyConnection, root: Path) -> ValuationResolution:
    """Inner dispatch — may raise on DuckDB read errors. Look-through SHORT-CIRCUITS:
    the bottom-up dual-track aggregate (holding_metrics) supersedes the old
    portfolio-harmonic state, so we tag path and return state=None (no old compute)."""
    tracked_index = _tracked_index_for_fund(con, fund.id)
    if tracked_index is not None:
        return _resolve_index(con, tracked_index)
    return ValuationResolution(None, False, None, path="lookthrough")
```

Also update the top-level degrade fallback in `resolve_valuation_state` to keep `path="index"` (default) — the existing `ValuationResolution(None, False, _NA_NO_ANCHOR)` stays valid (trailing default). Update the module docstring: remove the "look-through branch is an honest N/A stub" line and the `_resolve_lookthrough` reference (that fn is deleted in 3.2).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_valuation.py -k "path_" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(monitor): ValuationResolution.path + look-through short-circuit (slice 3)"
```

### Task 3.2: Delete the dead portfolio-harmonic look-through path

**Files:**
- Delete: `src/irc/monitor/lookthrough.py`, `tests/monitor/test_lookthrough.py`
- Modify: `src/irc/monitor/valuation.py` (remove `_resolve_lookthrough`)

- [ ] **Step 1: Delete the files + the dead function**

```bash
git rm src/irc/monitor/lookthrough.py tests/monitor/test_lookthrough.py
```

Then remove `_resolve_lookthrough` from `valuation.py` (the whole function, lines defining `def _resolve_lookthrough(...)` through its `return`), and remove its now-unused imports if any (`_stock_series_by_code` import — KEEP `_index_valuation_metrics`; remove `_stock_series_by_code` from the `from irc.opportunity.inputs_loader import (...)` block since the look-through resolver was its only user in this module — verify with grep first).

- [ ] **Step 2: Verify no dangling references**

Run: `grep -rn "_resolve_lookthrough\|monitor.lookthrough\|lookthrough_valuation_state\|monitor/lookthrough" src tests`
Expected: NO matches (the only hits should have been deleted). If `irc.monitor.lookthrough` is imported anywhere else, that import must be removed.

Run: `uv run python -c "import irc.monitor.valuation"`
Expected: no ImportError.

- [ ] **Step 3: Run the valuation suite**

Run: `uv run pytest tests/monitor/test_valuation.py -v`
Expected: PASS (the deleted look-through tests are gone; index + degrade + path tests stay green).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor(monitor): delete dead portfolio-harmonic look-through path (slice 3)"
```

### Task 3.3: `factors._valuation` numeric path + `FactorInputs.valuation_aggregate` + KNOWN_NA_REASONS 10→12

**Files:**
- Modify: `src/irc/monitor/factors.py`
- Test: `tests/monitor/test_factors.py`, `tests/monitor/test_known_na_reasons.py`

`FactorInputs` gains `valuation_aggregate: ValuationAggregate | None = None` (trailing-defaulted — back-compat with the 2 src construction sites + tests). `_valuation` branches: when `valuation_aggregate is not None` → numeric path (look-through); else → existing state path (index). Two new reachable `_NA_*` branches map `ValuationAggregate.reason`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/monitor/test_factors.py
from irc.monitor.holding_metrics import ValuationAggregate


def _inp(**kw):
    base = dict(acc_nav=(), minimum_observations=2, valuation_state=None,
                valuation_cached=False, restricted=None, aum_delta_pct=None,
                macro_rows=(), constituent_rows=())
    base.update(kw)
    from irc.monitor.factors import FactorInputs
    return FactorInputs(**base)


def test_valuation_numeric_path_eligible_from_aggregate():
    from irc.monitor.factors import build_factor_scores
    inp = _inp(valuation_aggregate=ValuationAggregate(0.25, None, 0.8))
    scores = {s.name: s for s in build_factor_scores("active_cn_equity", inp)}
    assert scores["valuation"].eligible is True
    assert scores["valuation"].value == 0.25


def test_valuation_numeric_path_no_data_reason():
    from irc.monitor.factors import build_factor_scores
    inp = _inp(valuation_aggregate=ValuationAggregate(None, "valuation_no_data", 0.0))
    scores = {s.name: s for s in build_factor_scores("active_cn_equity", inp)}
    assert scores["valuation"].eligible is False
    assert scores["valuation"].reason == "valuation_no_data"


def test_valuation_numeric_path_no_coverage_reason():
    from irc.monitor.factors import build_factor_scores
    inp = _inp(valuation_aggregate=ValuationAggregate(None, "valuation_no_coverage", 0.35))
    scores = {s.name: s for s in build_factor_scores("active_cn_equity", inp)}
    assert scores["valuation"].eligible is False
    assert scores["valuation"].reason == "valuation_no_coverage"


def test_valuation_state_path_unchanged_when_no_aggregate():
    # index path: valuation_aggregate None → state path (existing behavior).
    from irc.monitor.factors import build_factor_scores
    inp = _inp(valuation_state="cheap", valuation_cached=True)
    scores = {s.name: s for s in build_factor_scores("active_cn_equity", inp)}
    assert scores["valuation"].eligible is True and scores["valuation"].value == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_factors.py -k valuation_numeric -v`
Expected: FAIL — `TypeError: FactorInputs.__init__() got an unexpected keyword argument 'valuation_aggregate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/factors.py — modify

# import additions at top:
from irc.monitor.holding_metrics import (
    FlowAggregate, ValuationAggregate, _NA_FLOW_NO_DATA, _NA_FLOW_NO_COVERAGE,
    _NA_VALUATION_NO_DATA, _NA_VALUATION_NO_COVERAGE,
)

# add the two factor-level constants near the other _NA_* (alias the holding_metrics
# values so KNOWN_NA_REASONS references a name the reachability test can resolve):
_NA_VALUATION_NO_DATA_FACTOR = _NA_VALUATION_NO_DATA          # "valuation_no_data"
_NA_VALUATION_NO_COVERAGE_FACTOR = _NA_VALUATION_NO_COVERAGE  # "valuation_no_coverage"

KNOWN_NA_REASONS: frozenset[str] = frozenset({
    _NA_PROFILE_INELIGIBLE,
    _NA_TREND_INSUFFICIENT_HISTORY,
    _NA_VALUATION_NO_ANCHOR,
    _NA_VALUATION_UNKNOWN_STATE,
    _NA_HEAT_NO_DATA,
    _NA_MACRO_INSUFFICIENT_FAMILIES,
    _NA_MACRO_EMPTY_POOL,
    _NA_CONSTITUENT_NO_COVERAGE,
    _NA_FLOW_NO_DATA,
    _NA_FLOW_NO_COVERAGE,
    _NA_VALUATION_NO_DATA_FACTOR,
    _NA_VALUATION_NO_COVERAGE_FACTOR,
})
```

> CAUTION (reachability test): `test_known_na_reasons._emitted_reason_constants()` regexes `_NA_[A-Z_]+` names in `factors.py` source and resolves each to its value. Both `_NA_VALUATION_NO_DATA_FACTOR` and `_NA_VALUATION_NO_COVERAGE_FACTOR` MUST be **referenced in a real `_valuation` branch** (below) so they count as emitted. The imported `_NA_VALUATION_NO_DATA`/`_NA_VALUATION_NO_COVERAGE` also match the regex; since they alias the same string values, the emitted-set still equals KNOWN_NA_REASONS. Verify in step 4.

```python
# src/irc/monitor/factors.py — add field + rewrite _valuation

@dataclass(frozen=True)
class FactorInputs:
    acc_nav: tuple[tuple[str, float], ...]
    minimum_observations: int
    valuation_state: str | None
    valuation_cached: bool
    restricted: bool | None
    aum_delta_pct: float | None
    macro_rows: tuple[ImpactRow, ...]
    constituent_rows: tuple[ImpactRow, ...]
    flow: FlowAggregate | None = None
    valuation_aggregate: ValuationAggregate | None = None


def _valuation(profile: str, inp: FactorInputs) -> FactorScore:
    if "valuation" not in eligible_factors(profile):
        return _na("valuation", _NA_PROFILE_INELIGIBLE)
    agg = inp.valuation_aggregate
    if agg is not None:  # look-through bottom-up numeric path
        if agg.reason == _NA_VALUATION_NO_DATA_FACTOR or agg.value is None and agg.reason is None:
            return _na("valuation", _NA_VALUATION_NO_DATA_FACTOR)
        if agg.reason == _NA_VALUATION_NO_COVERAGE_FACTOR:
            return _na("valuation", _NA_VALUATION_NO_COVERAGE_FACTOR)
        if agg.value is None:
            return _na("valuation", _NA_VALUATION_NO_DATA_FACTOR)
        return FactorScore("valuation", agg.value, True, "", 1.0)
    # index state path (unchanged)
    if not inp.valuation_cached or inp.valuation_state is None:
        return _na("valuation", _NA_VALUATION_NO_ANCHOR)
    score = valuation_state_score(inp.valuation_state)
    if score is None:
        return _na("valuation", _NA_VALUATION_UNKNOWN_STATE)
    return FactorScore("valuation", score, True, "", 1.0)
```

> Simplify the numeric branch to clearly map both reasons (keep < 20 lines):
> ```python
>     agg = inp.valuation_aggregate
>     if agg is not None:
>         if agg.value is not None:
>             return FactorScore("valuation", agg.value, True, "", 1.0)
>         if agg.reason == _NA_VALUATION_NO_COVERAGE_FACTOR:
>             return _na("valuation", _NA_VALUATION_NO_COVERAGE_FACTOR)
>         return _na("valuation", _NA_VALUATION_NO_DATA_FACTOR)
> ```
> Use this cleaner form; it keeps both `_NA_*_FACTOR` constants referenced (reachable) and is < 20 lines.

- [ ] **Step 4: Run tests + KNOWN_NA_REASONS reachability**

Run: `uv run pytest tests/monitor/test_factors.py -k valuation -v`
Expected: PASS.

- [ ] **Step 5: Update the locked KNOWN_NA_REASONS test (ten→twelve)**

```python
# tests/monitor/test_known_na_reasons.py — edits:
# 1. docstring line ~16: "The ten named constants" → "The twelve named constants"
# 2. add to _EXPECTED:
#     "valuation_no_data",
#     "valuation_no_coverage",
# 3. rename test_known_na_reasons_is_exactly_the_ten_codes → ..._is_exactly_the_twelve_codes
```

Apply exactly:

```python
# _EXPECTED set — add the two factor codes (industry_no_data / false_cheap_clamp NOT added):
_EXPECTED = {
    "profile_ineligible",
    "trend_insufficient_history",
    "valuation_no_anchor",
    "valuation_unknown_state",
    "heat_no_data",
    "macro_insufficient_families",
    "macro_empty_pool",
    "constituent_no_coverage",
    "flow_no_data",
    "flow_no_coverage",
    "valuation_no_data",
    "valuation_no_coverage",
}


def test_known_na_reasons_is_exactly_the_twelve_codes():
    assert KNOWN_NA_REASONS == frozenset(_EXPECTED)
```

Also change the comment at line 16 from `# The ten named constants the spec enumerates (§6).` → `# The twelve named constants the spec enumerates (§6 + ADR 0020).`

- [ ] **Step 6: Run the locked test**

Run: `uv run pytest tests/monitor/test_known_na_reasons.py -v`
Expected: PASS (3 tests — exact-twelve, every-branch-emits-known, every-known-reachable).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat(monitor): _valuation numeric path + KNOWN_NA_REASONS 10->12 (slice 3)"
```

### Task 3.4: `_process_fund` wiring (full-basket + industry fetch + gate) + engine bump + END-TO-END integration test

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_cmd_drilldown.py` (or a new `tests/commands/test_monitor_cmd_valuation.py`)

This is the dark-factor trap. The wiring:
1. Build per-stock metrics over the **FULL disclosed basket** (not top-5) for valuation/board.
2. Compute `aggregate_flow` over the **top-5 weight slice** only (flow byte-identical).
3. Fetch industry-PE (1 call) + per-symbol industry map (full-basket symbols) at the edge.
4. Feed `valuation_aggregate=aggregate_valuation(holding_metrics)` into `FactorInputs` **only when `val.path == "lookthrough"` AND `holding_metrics` non-empty**.

> IMPLEMENTATION NOTE (full vs top-5): currently `_process_fund` slices `top_holdings[:_TOP_N_HOLDINGS]` and builds metrics over that. Change: build `full_holdings` (all disclosed, sorted desc) for valuation/board; keep `top5 = full_holdings[:_TOP_N_HOLDINGS]` for flow. Build ONE metric tuple over `full_holdings` with industry inputs; pass `flow_series` keyed only on top-5 symbols (holdings 6–N get `flow_no_data` naturally since their symbol isn't in `flow_series_by_code`). `aggregate_flow(holding_metrics)` then renormalizes over covered (top-5) rows — flow value unchanged because rows 6–N have `flow_score=None`. Confirm flow byte-identity with the existing `test_flow_wired_into_composite_for_active_cn_equity` staying green.

- [ ] **Step 1: Write the failing integration tests (drive REAL `_process_fund`)**

```python
# tests/commands/test_monitor_cmd_valuation.py  (NEW)
from __future__ import annotations
from pathlib import Path

from irc.monitor.types import MonitorFund, NarrativeDoc
from irc.monitor.valuation import ValuationResolution
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


class _Cfg:
    class history:
        minimum_observations = 2


class _FakeImpacts:
    impacts = ()
    cost_entries = []
    status = "ok"


class _FakeNarr:
    cost_entries = []
    def __init__(self, fid):
        self.doc = NarrativeDoc(fid, (), (), (), "ok")


def _active_fund(fid="110011"):
    return MonitorFund(
        id=fid, name_cn="易方达蓝筹", market="cn_off_exchange",
        analysis_profile="active_cn_equity", themes=("cn_equity_property_policy",),
        constituent_news=True,
        weights={"trend": 0.25, "valuation": 0.20, "flow": 0.15,
                 "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50)


def _qdii_fund():
    return MonitorFund(
        id="009225", name_cn="QDII互联网", market="qdii",
        analysis_profile="qdii_china_us_internet", themes=("us_monetary",),
        constituent_news=False,
        weights={"trend": 0.30, "valuation": 0.20, "heat": 0.15,
                 "macro_tilt": 0.20, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50)


def _snap(fid, holdings):
    return ActiveFundSnapshot(
        fund_id=fid, source_report_date="2026-03-31", source_report_quarter="2026Q1",
        cache_probed_at="2026-06-21T09:00:00",
        constituent_analyses=tuple(
            ConstituentAnalysis(symbol=s, name_cn=n, weight_pct=w,
                                evidence=(), failure_reasons=(), one_line_view="x")
            for s, n, w in holdings),
        failure_reasons_by_symbol={})


def _mature_series_map(*codes):
    from datetime import date
    from irc.opportunity.lookthrough_valuation import MetricSeries
    base = date(2025, 1, 1).toordinal()
    out = {}
    for c in codes:
        pts = tuple((date.fromordinal(base + 2 * i).isoformat(), 40.0 - i * 0.1, 2.0)
                    for i in range(200))  # descending PE → cheap vs own → self>0
        out[c] = MetricSeries(code=c, source="eastmoney", points=pts)
    return out


def _patch_common(monkeypatch, mc):
    monkeypatch.setattr(mc, "nav_series_for", lambda _fid: None)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, repo_root: ())
    monkeypatch.setattr(mc, "gather_impacts", lambda **_kw: _FakeImpacts())
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())
    monkeypatch.setattr(mc, "heat_inputs_for", lambda fid, purchase_table: (None, None))
    monkeypatch.setattr(mc, "fetch_flow_series", lambda symbols, cache_dir, today: {})
    # industry edge fetchers — injected to avoid network
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda cache_dir, today: {"酿酒行业": 60.0})
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, cache_dir, today: {s: "酿酒行业" for s in symbols})


def test_lookthrough_active_fund_gets_eligible_bottomup_valuation(monkeypatch, tmp_path):
    """(a) A look-through active fund with A-share holdings gets a bottom-up
    valuation FactorScore (eligible) end-to-end via the REAL _process_fund."""
    import irc.commands.monitor_cmd as mc
    import irc.opportunity.inputs_loader as il
    _patch_common(monkeypatch, mc)
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr("110011"))
    monkeypatch.setattr(mc, "load_latest_active_fund_cached",
                        lambda fid, data_dir: _snap("110011", [("600519", "茅台", 60.0)]))
    # look-through path (no tracked_index)
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(None, False, None, path="lookthrough"))
    monkeypatch.setattr(il, "_stock_series_by_code",
                        lambda con, syms: _mature_series_map(*syms))

    view, _c, _b = mc._process_fund(_active_fund(), _Cfg(), tmp_path, object(),
                                    con=object(), today="2026-06-21")
    val = [s for s in view.factor_scores if s.name == "valuation"][0]
    assert val.eligible is True, f"valuation must be eligible; reason={val.reason!r}"
    assert val.value is not None


def test_qdii_009225_stays_valuation_no_anchor_via_state_path(monkeypatch, tmp_path):
    """(b) 009225 lookthrough path but NO holding_metrics (fund_level profile
    builds none) → valuation_aggregate stays None → state path → valuation_no_anchor."""
    import irc.commands.monitor_cmd as mc
    _patch_common(monkeypatch, mc)
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr("009225"))
    # qdii_china_us_internet profile.lookthrough == "fund_level" → NO active_fund
    # holdings branch → holding_metrics empty.
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: None)
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(None, False, "valuation_no_anchor", path="lookthrough"))

    view, _c, _b = mc._process_fund(_qdii_fund(), _Cfg(), tmp_path, object(),
                                    con=object(), today="2026-06-21")
    val = [s for s in view.factor_scores if s.name == "valuation"][0]
    assert val.eligible is False
    assert val.reason == "valuation_no_anchor"


def test_synthetic_index_path_fund_rides_index_state(monkeypatch, tmp_path):
    """(c) A SYNTHETIC index-path fixture fund rides the index state — NOT 018132
    (look-through in prod). path=="index" → valuation_aggregate stays None → state."""
    import irc.commands.monitor_cmd as mc
    import irc.opportunity.inputs_loader as il
    _patch_common(monkeypatch, mc)
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr("510300"))
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: None)
    monkeypatch.setattr(il, "_stock_series_by_code", lambda con, syms: {})
    # index path resolves a real state
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution("cheap", True, None, path="index"))

    fund = _active_fund("510300")
    view, _c, _b = mc._process_fund(fund, _Cfg(), tmp_path, object(),
                                    con=object(), today="2026-06-21")
    val = [s for s in view.factor_scores if s.name == "valuation"][0]
    assert val.eligible is True
    assert val.value == 1.0  # "cheap" → +1.0 via the state path (NOT the aggregate)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_monitor_cmd_valuation.py -v`
Expected: FAIL — `fetch_industry_pe`/`fetch_stock_industry_map` not importable in `monitor_cmd`, and/or valuation aggregate not wired (test (a) gets `valuation_no_anchor`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/commands/monitor_cmd.py — modify

# 1. import the new edge fetchers + aggregate_valuation
from irc.monitor.industry_valuation import fetch_industry_pe, fetch_stock_industry_map
from irc.monitor.holding_metrics import build_holding_metrics, aggregate_flow, aggregate_valuation

# 2. bump the engine version
_ENGINE_VERSION = "3"
```

Rewrite the look-through holdings block in `_process_fund` (the `if profile_spec and profile_spec.lookthrough == "active_fund":` body that builds `top_holdings` + `holding_metrics`). Replace the holdings/flow/metrics construction with full-basket + top-5 flow + industry:

```python
    holding_metrics: tuple = ()
    profile_spec = PROFILES.get(fund.analysis_profile)
    if profile_spec and profile_spec.lookthrough == "active_fund":
        const_pool = build_constituent_pool(fund.id, root=root)
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        full_holdings: tuple = ()
        if snap is not None:
            full_holdings = tuple(sorted(
                snap.constituent_analyses, key=lambda c: c.weight_pct, reverse=True))
        top5 = full_holdings[:_TOP_N_HOLDINGS]
        if const_pool and top5:
            holding_symbols = tuple(h.symbol for h in top5)
            const_impacts_result = gather_impacts(
                fund_id=fund.id, themes=holding_symbols, pool=const_pool,
                route=llm_config, call=llm_call)
            cost_history.extend(const_impacts_result.cost_entries)
            constituent_rows = _make_constituent_rows(const_impacts_result, top5)
        if full_holdings and today is not None:
            holding_metrics = _build_full_basket_metrics(
                full_holdings, top5, fund.id, root=root, today=today, con=con)

    # ... (valuation resolution below) ...
```

Add a small EDGE helper (effects confined here) above `_process_fund`:

```python
def _build_full_basket_metrics(full_holdings, top5, fund_id, *, root, today, con):
    """EDGE: fetch flow (top-5) + industry (full basket) → full-basket HoldingMetrics.
    Flow stays top-5 (byte-identical); valuation/board span the full basket."""
    from irc.opportunity.inputs_loader import _stock_series_by_code
    flow_symbols = tuple(h.symbol for h in top5)
    try:
        flow_series = fetch_flow_series(
            flow_symbols, cache_dir=root / "data" / "monitor" / "fund_flow", today=today)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("flow_fetch failed for %s", fund_id, exc_info=True)
        flow_series = {s: None for s in flow_symbols}
    full_symbols = tuple(h.symbol for h in full_holdings)
    series_by_code = _stock_series_by_code(con, full_symbols) if con is not None else {}
    industry_pe = fetch_industry_pe(
        cache_dir=root / "data" / "monitor" / "industry_pe", today=today)
    industry_map = fetch_stock_industry_map(
        full_symbols, cache_dir=root / "data" / "monitor" / "stock_industry", today=today)
    return build_holding_metrics(
        full_holdings, series_by_code, flow_series,
        industry_by_symbol=industry_map, industry_pe_by_industry=industry_pe)
```

> `fetch_industry_pe`/`fetch_stock_industry_map` MUST be referenced as module attributes (`mc.fetch_industry_pe`) so the integration test's monkeypatch hits. They are imported at module top, so `monkeypatch.setattr(mc, "fetch_industry_pe", ...)` works — but `_build_full_basket_metrics` calls them by bare name, which resolves to the module global → patch applies. Good.

Now the FactorInputs wiring — the gate (`path=="lookthrough"` AND holding_metrics non-empty):

```python
    inp = FactorInputs(
        acc_nav=nav.acc_series if nav else (),
        minimum_observations=cfg.history.minimum_observations,
        valuation_state=val.state,
        valuation_cached=val.cached,
        restricted=restricted,
        aum_delta_pct=aum_delta_pct,
        macro_rows=macro_rows,
        constituent_rows=constituent_rows,
        flow=aggregate_flow(holding_metrics) if holding_metrics else None,
        valuation_aggregate=(
            aggregate_valuation(holding_metrics)
            if val.path == "lookthrough" and holding_metrics else None
        ),
    )
```

> The second clause (`and holding_metrics`) is load-bearing: 009225 has `path="lookthrough"` but no holding_metrics → `valuation_aggregate=None` → `_valuation` state path → `valuation_no_anchor` (today's behavior).

- [ ] **Step 4: Run integration tests to verify they pass**

Run: `uv run pytest tests/commands/test_monitor_cmd_valuation.py -v`
Expected: PASS (3 tests: (a) eligible bottom-up, (b) 009225 valuation_no_anchor, (c) synthetic index state).

- [ ] **Step 5: Verify flow byte-identity not broken**

Run: `uv run pytest tests/monitor/test_valuation_wiring.py -v`
Expected: PASS (the existing `test_flow_wired_into_composite_for_active_cn_equity` must update its `build_holding_metrics` call only if it passes positional args — it uses the keyword path via monkeypatched `fetch_flow_series`, so it should pass as-is; if it breaks because `_process_fund` now calls `fetch_industry_pe`, add `monkeypatch.setattr(mc, "fetch_industry_pe", lambda cache_dir, today: {})` and `fetch_stock_industry_map` to that test). Apply the patch if needed.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(monitor): wire bottom-up valuation into _process_fund + engine 2->3 (slice 3)"
```

### Task 3.5: Board columns + value-trap badge + industry-coverage rollup + sub-0.50 note

**Files:**
- Modify: `src/irc/monitor/render_drilldown.py`
- Test: `tests/monitor/test_render_drilldown.py`

Board gains `行业 · 行业PE · r · 行业分` columns + a value-trap badge on `false_cheap` rows with a `便宜(自身)/偏贵(行业)→中性` annotation. Rollup ALWAYS shows `行业覆盖 X%` (fraction of covered-valuation weight whose industry leg resolved) + a non-gating note when industry coverage `< 0.50`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/monitor/test_render_drilldown.py
def test_board_renders_industry_columns():
    m = _m("600519", 12.0, pe=30.0, pb=8.0, pe_percentile=0.82,
           valuation_state="cheap", self_score=1.0, industry="酿酒行业",
           industry_pe=20.0, industry_richness=1.5, industry_score=-1.0,
           val_score=0.0, false_cheap=True, industry_reason="false_cheap_clamp")
    html = holdings_board_html((m,))
    assert "酿酒行业" in html        # 行业 column
    assert "20.0" in html            # 行业PE
    assert "1.5" in html or "1.50" in html  # r
    assert "中性" in html            # value-trap badge annotation


def test_board_value_trap_badge_only_on_clamped_rows():
    clean = _m("000858", 8.0, val_score=0.5, false_cheap=False)
    html = holdings_board_html((clean,))
    assert "价值陷阱" not in html     # no badge on a non-clamped row


def test_valuation_rollup_always_shows_industry_coverage():
    metrics = (_m("a", 60.0, val_score=1.0, industry="X", industry_score=1.0),)
    agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.60)
    html = valuation_rollup_html(metrics, agg)
    assert "行业覆盖" in html


def test_valuation_rollup_sub_50_industry_coverage_note():
    # one covered row WITHOUT an industry leg → industry coverage 0% < 0.50 → note.
    metrics = (_m("a", 60.0, val_score=1.0, industry=None, industry_score=None),)
    agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.60)
    html = valuation_rollup_html(metrics, agg)
    assert "价值陷阱检测数据有限" in html or "不可用" in html


def test_valuation_rollup_no_imperative_language():
    metrics = (_m("a", 60.0, val_score=1.0, industry="X", industry_score=1.0),)
    agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.60)
    html = valuation_rollup_html(metrics, agg)
    assert "买入" not in html and "卖出" not in html
```

Update the `_m` helper at the top of the test file to default the new dual-track fields:

```python
def _m(symbol, weight, **kw):
    base = dict(pe=None, pb=None, pe_percentile=None, valuation_state=None,
                valuation_reason=None, flow_pct_5d=None, flow_pct_20d=None,
                flow_score=None, flow_reason=None,
                self_score=None, industry=None, industry_pe=None,
                industry_richness=None, industry_score=None, val_score=None,
                false_cheap=False, industry_reason=None)
    base.update(kw)
    return HoldingMetric(symbol=symbol, name=symbol, weight_pct=weight, **base)
```

Add the import: `from irc.monitor.holding_metrics import ValuationAggregate` to the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -k "industry or value_trap or valuation_rollup" -v`
Expected: FAIL — `ImportError: cannot import name 'valuation_rollup_html'` and/or missing columns.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_drilldown.py — modify

from irc.monitor.holding_metrics import FlowAggregate, HoldingMetric, ValuationAggregate

_INDUSTRY_COVERAGE_NOTE_FLOOR = 0.50  # reuses lookthrough's 0.50 (D10); no new threshold


def _trap_badge(m: HoldingMetric) -> str:
    if not m.false_cheap:
        return ""
    return " <span class='trap-badge'>价值陷阱 便宜(自身)/偏贵(行业)→中性</span>"


def _row(i: int, m: HoldingMetric) -> str:
    return (
        f"<tr><td>{i}</td><td>{escape(m.symbol)}</td><td>{escape(m.name)}</td>"
        f"<td>{m.weight_pct:.2f}</td>"
        f"<td>{_cell_num(m.pb)}</td><td>{_cell_num(m.pe)}</td>"
        f"<td>{_cell_num(m.pe_percentile, '{:.0%}')}</td>"
        f"<td>{_cell_state(m.valuation_state, m.valuation_reason)}</td>"
        f"<td>{escape(m.industry) if m.industry else '—'}</td>"
        f"<td>{_cell_num(m.industry_pe)}</td>"
        f"<td>{_cell_num(m.industry_richness)}</td>"
        f"<td>{_cell_num(m.industry_score, '{:+.1f}')}{_trap_badge(m)}</td>"
        f"<td>{_cell_num(m.flow_pct_5d)}</td><td>{_cell_num(m.flow_pct_20d)}</td>"
        f"<td>{_flow_cell(m.flow_score, m.flow_reason)}</td></tr>"
    )


def holdings_board_html(metrics: tuple[HoldingMetric, ...]) -> str:
    head = (
        "<tr><th>#</th><th>代码</th><th>名称</th><th>权重%</th><th>PB</th><th>PE</th>"
        "<th>PE分位</th><th>估值</th><th>行业</th><th>行业PE</th><th>r</th><th>行业分</th>"
        "<th>5d净占比</th><th>20d净占比</th><th>资金流分</th></tr>"
    )
    ordered = sorted(metrics, key=lambda m: m.weight_pct, reverse=True)
    rows = "".join(_row(i, m) for i, m in enumerate(ordered, start=1))
    return f"<table class='holdings-board'>{head}{rows}</table>"


def _industry_coverage_ratio(metrics: tuple[HoldingMetric, ...]) -> float | None:
    """Fraction of COVERED-valuation weight whose industry leg resolved.
    None when nothing is covered (no denominator)."""
    covered = [m for m in metrics if m.val_score is not None]
    cw = sum(m.weight_pct for m in covered)
    if cw <= 0.0:
        return None
    with_industry = sum(m.weight_pct for m in covered if m.industry_score is not None)
    return with_industry / cw


def valuation_rollup_html(
    metrics: tuple[HoldingMetric, ...], agg: ValuationAggregate,
) -> str:
    """PURE: dual-track reconciliation line — valuation factor = Σ(wᵢ·vᵢ)/Σ(wᵢ),
    covered NAV ratio, and ALWAYS the industry-leg coverage 行业覆盖 X% (Q7). A
    sub-0.50 industry coverage fires a non-gating data-limited note. Lean only."""
    ind_cov = _industry_coverage_ratio(metrics)
    clamped = [m for m in metrics if m.false_cheap]
    if agg.value is None:
        body = f"估值因子 = N/A（{escape(agg.reason or 'valuation_no_data')}）"
    else:
        ind_txt = f"{ind_cov:.0%}" if ind_cov is not None else "—"
        body = (
            f"估值因子 = Σ(wᵢ·vᵢ)/Σ(wᵢ) = {agg.value:+.4f} "
            f"（NAV覆盖 {agg.covered_weight_ratio:.0%}；行业覆盖 {ind_txt}）"
        )
    if clamped:
        body += f"·已剔除价值陷阱 {len(clamped)} 只"
    if ind_cov is not None and ind_cov < _INDUSTRY_COVERAGE_NOTE_FLOOR:
        body += "·价值陷阱检测数据有限/不可用"
    return f"<div class='valuation-rollup'>{body}</div>"
```

Extend the CSS string (`_DRILLDOWN_CSS`) with a `.trap-badge` style and a `.valuation-rollup` style:

```python
    ".trap-badge{color:#9a6700;font-size:11px;background:#fff8c5;padding:0 4px;border-radius:3px}"
    ".valuation-rollup{margin:8px 0;padding:6px 8px;background:#f6f8fa;border-left:3px solid #8250df;font-size:13px}"
```

Wire the valuation rollup into the per-fund section so the drilldown page renders it next to the flow rollup:

```python
def drilldown_section_html(name_cn: str, fund_id: str, metrics, agg, signal, val_agg=None) -> str:
    """PURE: one fund's board + flow roll-up + valuation roll-up section."""
    val_html = valuation_rollup_html(metrics, val_agg) if val_agg is not None else ""
    return (
        f"<section class='drilldown' id='dd-{escape(fund_id)}'>"
        f"<h2>{escape(name_cn)} ({escape(fund_id)})</h2>"
        f"{holdings_board_html(metrics)}{flow_rollup_html(metrics, agg, signal)}{val_html}"
        "</section>"
    )
```

> The `drilldown_page_html` views tuple stays `(fund_id, name_cn, metrics, agg, signal)` for back-compat. `val_agg` defaults None (the standalone page can omit it). Update `_write_drilldown` in `monitor_cmd.py` only if you want the valuation rollup in the standalone page — OPTIONAL; the reconciliation oracle (Slice 4) reads the trace, not the HTML, so the HTML wiring is display-only. To include it: pass `aggregate_valuation(v.holding_metrics)` as a 6th tuple element and update `drilldown_page_html`'s unpack. Keep the existing 5-tuple if simpler; the board columns + badge are the locked deliverable.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_drilldown.py -v`
Expected: PASS (all, incl. the existing flow-board tests — they use the updated `_m` defaults).

- [ ] **Step 5: Lint + size + commit**

Run: `uv run ruff check src/irc/monitor/render_drilldown.py tests/monitor/test_render_drilldown.py`
Expected: no errors. If `render_drilldown.py` exceeds 200 lines, extract `_trap_badge`/`_industry_coverage_ratio` is already small — it should fit.

```bash
git add -A && git commit -m "feat(monitor): board industry columns + value-trap badge + valuation rollup (slice 3)"
```

### Task 3.6: Slice-3 regression sweep (per-file — tests/commands HANGS as a whole dir)

**Files:** none (verification only)

- [ ] **Step 1: Run the three required dirs PER FILE**

> CRITICAL (project memory): FactorInputs gained a trailing field; run every dir that exercises it, but `tests/commands/` HANGS on suite ordering — run PER FILE.

Run each, expecting PASS:
```bash
uv run pytest tests/monitor/test_valuation.py -q
uv run pytest tests/monitor/test_factors.py -q
uv run pytest tests/monitor/test_factors_property.py -q
uv run pytest tests/monitor/test_known_na_reasons.py -q
uv run pytest tests/monitor/test_holding_metrics.py -q
uv run pytest tests/monitor/test_render_drilldown.py -q
uv run pytest tests/monitor/test_valuation_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -q
uv run pytest tests/commands/test_monitor_cmd_valuation.py -q
uv run pytest tests/commands/test_monitor_cmd_heat.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
uv run pytest tests/commands/test_monitor_constituent.py -q
```

If any FAILs because a `FactorInputs(...)` or `build_holding_metrics(...)` call site lacks the new keyword, fix the call site (new fields default — the failure would be a positional-arg mismatch, unlikely). Fix + re-run.

- [ ] **Step 2: Lint the whole touched set**

Run: `uv run ruff check src tests`
Expected: no errors.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "test(monitor): slice-3 regression fixes" --allow-empty
```

---

# SLICE 4 — Eval (schema 4 + determinism + coverage + reconciliation) + engine isolation + ADR

**Spec:** §5.E, §5.F, §7 step 4, §7.1, §8.

### Task 4.1: Trace schema `"3"→"4"` + holding_metrics dual-track fields + valuation aggregate block

**Files:**
- Modify: `src/irc/monitor/eval/trace.py`
- Test: `tests/monitor/eval/test_trace.py`

The `_holding_metrics` block gains the dual-track per-row fields + a `valuation_aggregate` sub-block (alongside the existing `aggregate` flow block).

- [ ] **Step 1: Rename the locked schema test + assert new fields**

```python
# tests/monitor/eval/test_trace.py
# 1. RENAME test_schema_version_is_3 → test_schema_version_is_4, bump the literal:

def test_schema_version_is_4():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="3", run_date="2026-06-21")
    assert t["schema_version"] == "4"
```

Then extend the holding_metrics block test (`test_trace_emits_holding_metrics_block`) to construct a HoldingMetric with dual-track fields and assert they serialize:

```python
def test_trace_emits_holding_metrics_block():
    from irc.monitor.holding_metrics import HoldingMetric
    hm = HoldingMetric("600519", "贵州茅台", 12.0, 30.0, 8.0, 0.8, "expensive",
                       None, 4.0, 3.5, 1.0, None,
                       self_score=-0.5, industry="酿酒行业", industry_pe=20.0,
                       industry_richness=1.5, industry_score=-1.0, val_score=-0.7,
                       false_cheap=False, industry_reason=None)
    view = _good_view()
    view = dataclasses.replace(view, holding_metrics=(hm,))
    fund = _fund("519069", profile="active_cn_equity")
    bundle = FundTraceBundle("519069", (), (), ())
    gate = apply_eval_gate(view.signal, health=(), gating_stages=GATING_STAGES_M0)
    t = build_eval_trace(((fund, view, gate, bundle),), engine_version="3",
                         run_date="2026-06-21")
    block = t["funds"]["519069"]["holding_metrics"]
    row = block["rows"][0]
    assert row["symbol"] == "600519"
    assert row["val_score"] == -0.7
    assert row["industry"] == "酿酒行业"
    assert row["industry_score"] == -1.0
    assert row["false_cheap"] is False
    assert "valuation_aggregate" in block
    assert block["valuation_aggregate"]["value"] == -0.7  # single covered row
```

Also update the two `engine_version="2"` literals in the existing holding_metrics test if present, and `test_top_level_keys` / `test_per_fund_schema_keys` need NO change (the `holding_metrics` key already exists).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_trace.py -k "schema_version or holding_metrics_block" -v`
Expected: FAIL — `test_schema_version_is_4` asserts `"4"` but module emits `"3"`; row lacks `val_score`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/trace.py — modify

from irc.monitor.holding_metrics import aggregate_flow, aggregate_valuation

_SCHEMA_VERSION = "4"


def _holding_metrics(view: FundView) -> dict:
    metrics = view.holding_metrics
    flow_agg = aggregate_flow(metrics)
    val_agg = aggregate_valuation(metrics)
    return {
        "rows": [{"symbol": m.symbol, "name": m.name, "weight_pct": m.weight_pct,
                  "pe": m.pe, "pb": m.pb, "pe_percentile": m.pe_percentile,
                  "valuation_state": m.valuation_state, "valuation_reason": m.valuation_reason,
                  "flow_pct_5d": m.flow_pct_5d, "flow_pct_20d": m.flow_pct_20d,
                  "flow_score": m.flow_score, "flow_reason": m.flow_reason,
                  "self_score": m.self_score, "industry": m.industry,
                  "industry_pe": m.industry_pe, "industry_richness": m.industry_richness,
                  "industry_score": m.industry_score, "val_score": m.val_score,
                  "false_cheap": m.false_cheap, "industry_reason": m.industry_reason}
                 for m in metrics],
        "aggregate": {"value": flow_agg.value, "reason": flow_agg.reason,
                      "covered_weight_ratio": flow_agg.covered_weight_ratio},
        "valuation_aggregate": {"value": val_agg.value, "reason": val_agg.reason,
                                "covered_weight_ratio": val_agg.covered_weight_ratio},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_trace.py -v`
Expected: PASS (all). The JSON-round-trip test confirms `false_cheap` bool + new fields serialize.

- [ ] **Step 5: Update the acceptance test schema literals**

```bash
grep -n 'schema_version"\] == "3"' tests/monitor/test_acceptance_eval.py
```
Edit BOTH occurrences `"3"` → `"4"` in `tests/monitor/test_acceptance_eval.py` (the `assert trace["schema_version"] == "3"` lines).

Run: `uv run pytest tests/monitor/test_acceptance_eval.py -q`
Expected: PASS (or the same pre-existing skips/failures as baseline — diff-scope if any fail; the schema assertion must now be `"4"`).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(monitor): trace schema 3->4 + dual-track holding_metrics fields (slice 4)"
```

### Task 4.2: Reconciliation oracle — board Σwᵢvᵢ/Σwᵢ == valuation factor value (4dp)

**Files:**
- Modify: `src/irc/monitor/eval/structural.py`
- Test: `tests/monitor/eval/test_structural.py`

Mirror `flow_reconciliation`. Reads `val_score` (post-clamp) from the trace `holding_metrics.rows`; compares the covered weighted mean to the `valuation` factor value (from `signal.contributions`). Clamped rows sum as 0 (covered). No valuation contribution → PASS.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/monitor/eval/test_structural.py
from irc.monitor.eval.structural import valuation_reconciliation, valuation_coverage_health


def _trace_with_valuation(rows, factor_value):
    return {
        "signal": {"contributions": [{"name": "valuation", "value": factor_value}]},
        "holding_metrics": {"rows": rows},
    }


def test_valuation_reconciliation_passes_when_board_matches_factor():
    rows = [{"weight_pct": 50.0, "val_score": 1.0},
            {"weight_pct": 30.0, "val_score": -1.0}]
    # board = (50*1 + 30*-1)/80 = 0.25
    t = _trace_with_valuation(rows, 0.25)
    assert valuation_reconciliation(t).status == "PASS"


def test_valuation_reconciliation_clamped_row_counts_as_zero():
    rows = [{"weight_pct": 50.0, "val_score": 0.0},   # clamped
            {"weight_pct": 30.0, "val_score": 1.0}]
    # board = (50*0 + 30*1)/80 = 0.375
    t = _trace_with_valuation(rows, 0.375)
    assert valuation_reconciliation(t).status == "PASS"


def test_valuation_reconciliation_fails_on_mismatch():
    rows = [{"weight_pct": 50.0, "val_score": 1.0}]
    t = _trace_with_valuation(rows, -0.99)
    assert valuation_reconciliation(t).status == "FAIL"


def test_valuation_reconciliation_no_factor_is_pass():
    t = {"signal": {"contributions": []}, "holding_metrics": {"rows": []}}
    assert valuation_reconciliation(t).status == "PASS"


def test_valuation_coverage_health_is_informational_pass():
    rows = [{"weight_pct": 50.0, "val_score": 1.0, "industry_score": 1.0, "false_cheap": False},
            {"weight_pct": 30.0, "val_score": 0.0, "industry_score": -1.0, "false_cheap": True}]
    t = {"holding_metrics": {"rows": rows,
         "valuation_aggregate": {"value": 0.375, "reason": None, "covered_weight_ratio": 0.80}}}
    h = valuation_coverage_health(t)
    assert h.status == "PASS"
    assert any("false_cheap 1" in r for r in h.reasons)
    assert any("industry_cover" in r for r in h.reasons)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/eval/test_structural.py -k valuation_ -v`
Expected: FAIL — `ImportError: cannot import name 'valuation_reconciliation'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/eval/structural.py — add (after flow_coverage_health)

def _board_valuation_value(rows: list[dict]) -> float | None:
    covered = [r for r in rows if r.get("val_score") is not None]
    cw = sum(r["weight_pct"] for r in covered)
    if cw <= 0.0:
        return None
    return sum(r["weight_pct"] * r["val_score"] for r in covered) / cw


def _valuation_factor_value(t: dict) -> float | None:
    for c in t.get("signal", {}).get("contributions", []):
        if c.get("name") == "valuation":
            return c.get("value")
    return None


def valuation_reconciliation(t: dict) -> StageHealth:
    """PURE: the board's Σ(wᵢ·val_scoreᵢ)/Σ(wᵢ) over covered rows (clamped rows
    sum as 0) must equal the valuation factor value (4dp). No valuation
    contribution → PASS. Panel-only — NOT in any GATING_STAGES list (§5.E)."""
    factor_value = _valuation_factor_value(t)
    if factor_value is None:
        return StageHealth("valuation_reconciliation", "PASS", ())
    board = _board_valuation_value(t.get("holding_metrics", {}).get("rows", []))
    if board is None or abs(round(board, 4) - round(factor_value, 4)) >= _EPS:
        return StageHealth("valuation_reconciliation", "FAIL",
                           (f"board {board} != factor {factor_value}",))
    return StageHealth("valuation_reconciliation", "PASS", ())


def valuation_coverage_health(t: dict) -> StageHealth:
    """PURE informational dual-track coverage tally (§5.E, panel-only, always PASS).
    Surfaces NAV coverage, industry-leg coverage over covered rows, and false_cheap
    tally. Empty holding_metrics → PASS with no reasons, never raises."""
    hm = t.get("holding_metrics") or {}
    rows = hm.get("rows") or []
    agg = hm.get("valuation_aggregate") or {}
    if not rows and not agg:
        return StageHealth("valuation_coverage", "PASS", ())
    covered = [r for r in rows if r.get("val_score") is not None]
    cw = sum(r["weight_pct"] for r in covered)
    industry_cov = (
        sum(r["weight_pct"] for r in covered if r.get("industry_score") is not None) / cw
        if cw > 0.0 else 0.0
    )
    nav_cov = agg.get("covered_weight_ratio")
    false_cheap = sum(1 for r in rows if r.get("false_cheap"))
    reasons: list[str] = []
    if nav_cov is not None:
        reasons.append(f"nav_cover {round(nav_cov, 2)}")
    reasons.append(f"industry_cover {round(industry_cov, 2)}")
    reasons.append(f"false_cheap {false_cheap}")
    return StageHealth("valuation_coverage", "PASS", tuple(reasons))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/eval/test_structural.py -k valuation_ -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire the two new healths into the command panel (parallel to flow)**

In `commands/monitor_cmd.py`:
- import: `from irc.monitor.eval.structural import (monitor_signal_health, flow_reconciliation, flow_coverage_health, valuation_reconciliation, valuation_coverage_health,)`
- In `_compute_gates`, add two dicts `val_recon_healths`, `val_cov_healths`, fill them inside the per-fund loop with the same try/except WARN-fallback pattern as flow (status `"WARN"` on exception for reconciliation; `"WARN"` for coverage). Return them.
- In `run_monitor`, unpack the two extra dicts and pass to `build_panel_rows` via two new kwargs.

In `eval/determinism.py::build_panel_rows`, add two optional kwargs `valuation_reconciliation_healths=None`, `valuation_coverage_healths=None`, and append their `_row(...)` after the flow rows (same default-empty → omitted pattern).

> This is purely additive panel plumbing. Write one focused test in `tests/commands/test_monitor_cmd_eval_wiring.py` mirroring the existing `test_flow_health_exception_fallback_is_warn` but for `valuation_reconciliation` (patch it to raise, assert the fallback health is `"WARN"`). Add the test FIRST (red), then wire (green).

```python
# tests/commands/test_monitor_cmd_eval_wiring.py — append (mirrors flow finding 2)
def test_valuation_health_exception_fallback_is_warn(monkeypatch, tmp_path):
    import irc.commands.monitor_cmd as mc
    from irc.monitor.eval.types import FundTraceBundle
    from irc.monitor.render_types import FundView
    from irc.monitor.types import SignalRecord, FactorContribution, NarrativeDoc

    def _sig(fid):
        return SignalRecord(fund_id=fid, status="ok", bias="ADD_BIAS", composite=0.3,
                            signal_confidence=1.0, available_weight=1.0,
                            present_families=("price-momentum",),
                            contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                            divergence_codes=())

    def _view(fid):
        return FundView(fund_id=fid, name_cn="x", latest_nav=2.0, as_of_date="2026-06-21",
                        nav_series=(("2026-06-18", 2.4), ("2026-06-19", 2.5)),
                        signal=_sig(fid), narrative=NarrativeDoc(fid, (), (), (), "ok"),
                        evidence_pool=(), return_table={}, factor_freshness={},
                        missing_factor_reasons=(), factor_scores=())

    fund = _active_fund()  # reuse the helper from test_valuation_wiring or define locally
    view = _view(fund.id)
    bundle = FundTraceBundle(fund.id, (), (), ())
    monkeypatch.setattr(mc, "valuation_reconciliation",
                        lambda proj: (_ for _ in ()).throw(RuntimeError("boom")))
    result = mc._compute_gates([fund], [view], [bundle], min_obs=2,
                               suite_healths=(), trading_days=None)
    # _compute_gates now returns the valuation dicts too — assert WARN fallback.
    val_recon = result[-2]  # adjust index to the val_recon dict position
    assert val_recon[fund.id].status == "WARN"
```

> The exact return-tuple position depends on how you extend `_compute_gates`. Document the new return shape in the function docstring and index the test accordingly. Keep flow's positions stable; append valuation dicts at the end.

- [ ] **Step 6: Run the eval-wiring + structural tests per-file**

Run: `uv run pytest tests/monitor/eval/test_structural.py -q`
Run: `uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat(monitor): valuation reconciliation oracle + coverage health (slice 4)"
```

### Task 4.3: Engine isolation — confirm `"2"/"3"` filtering (no code change expected)

**Files:** none (verification only)

Per §7.1, no test asserts the literal `_ENGINE_VERSION`; the forward-eval isolation uses `target_engine` as a version-agnostic fixture. The `"2"→"3"` bump (done in 3.4) flows through automatically. This task confirms.

- [ ] **Step 1: Run the forward-score isolation tests**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -q`
Expected: PASS (the engine-isolation fixtures are version-agnostic). If any test hard-codes `"2"`, update it to `"3"` ONLY if it asserts the CURRENT engine; if it uses arbitrary version fixtures, leave it.

- [ ] **Step 2: Confirm Follow-up 1 `engine_population` still recognizes the transition**

Run: `uv run pytest tests/monitor/eval/ -q -k "forward or engine or population"`
Expected: PASS. The `engine_population` WARN covers the `"2"→"3"` transition (attribution-only, never gates).

- [ ] **Step 3: Commit (empty if nothing changed)**

```bash
git add -A && git commit -m "test(monitor): confirm engine 2/3 isolation (slice 4)" --allow-empty
```

### Task 4.4: Author ADR 0020

**Files:**
- Create: `docs/adr/0020-monitor-dual-track-valuation.md`

Record the rationale from spec §8 + the Q-resolutions. Use the ADR 0019 format (read `docs/adr/0019-monitor-capital-flow-factor.md` for the header/Status/Builds-on/Decision structure).

- [ ] **Step 1: Write the ADR**

```markdown
# ADR 0020 — Monitor dual-track valuation + False-Cheap clamp

**Status:** Accepted as a **prior** (2026-06-21). Records the design rationale for re-basing the monitor look-through valuation factor bottom-up (per-stock dual-track + clamp); the quantitative validation stays deferred behind ADR 0018's evidence gate (priors are justified, never auto-tuned).

**Builds on:** [ADR 0017 — monitor evidence isolation](0017-monitor-evidence-isolation.md), [ADR 0018 — monitor scoring rationale + weight/band governance](0018-monitor-scoring-rationale-and-governance.md), [ADR 0019 — monitor capital-flow factor](0019-monitor-capital-flow-factor.md) (D4 deferred this work; per-symbol fetch posture reused).

**Relates to:** #156 / [ADR 0015](0015-portfolio-action-emission-contract.md) (a better-reasoned lean, never an order), [ADR 0014](0014-legulegu-rate-limit-handling.md) (per-symbol cached fetch), [ADR 0012](0012-fundamental-led-equity-valuation.md)/[ADR 0009](0009-consensus-upside-degrade-to-none.md) (why PEG/DCF stay out). **Spec:** [`docs/superpowers/specs/2026-06-19-monitor-dual-track-valuation-design.md`](../superpowers/specs/2026-06-19-monitor-dual-track-valuation-design.md).

**Source of truth:** [holding_metrics.py](../../src/irc/monitor/holding_metrics.py) (dual-track score, clamp, aggregate_valuation, named-constant priors), [industry_valuation.py](../../src/irc/monitor/industry_valuation.py) (industry data edge), [factors.py](../../src/irc/monitor/factors.py) (`_valuation` numeric path + KNOWN_NA_REASONS), [valuation.py](../../src/irc/monitor/valuation.py) (`ValuationResolution.path`), [monitor_cmd.py](../../src/irc/commands/monitor_cmd.py) (`_ENGINE_VERSION`, wiring), [eval/structural.py](../../src/irc/monitor/eval/structural.py) (reconciliation oracle).

## Context

The look-through valuation factor collapsed a fund's holdings into one portfolio earnings-yield series and took its self-history percentile. Self-history alone is value-trap-blind: a stock cheap vs its own (possibly de-rated) history can be expensive vs its peers. Separately, #168 surfaced a per-stock board that did not drive the bias. This ADR re-bases the factor bottom-up so the board and the factor agree, and adds an industry-relative leg + clamp to detect value traps. This touches a governed scoring surface (ADR 0018) and therefore records the priors here.

## Decision

### D1 — Bottom-up dual-track REPLACES the portfolio-harmonic percentile (methodology replacement, not a value re-base)
The new path is a cross-sectional weighted mean of per-stock dual-track scores, NOT the old portfolio-harmonic-series percentile. Consequences: (1) the factor value moves for look-through funds even with zero industry data (no "industry-off ⇒ byte-identical" fallback); (2) maturity is gated per stock (a fund near the floor with short-history holdings can newly read `valuation_no_coverage`); (3) no portfolio-harmonic fallback — under-coverage → honest N/A. The old `src/irc/monitor/lookthrough.py` + `_resolve_lookthrough` are deleted.

### D2 — Dual-track blend = 0.60·self-history + 0.40·industry-richness
`self_score = valuation_state_score(state)` (reuses the existing percentile→band→state→{1.0..-1.0} ladder verbatim, so the board's displayed state and self_score can never disagree). `industry_score` from richness `r = stock_pe / industry_avg_pe`, additive ASYMMETRIC raw-`r` bands (`r≤0.70→+1.0 · 0.70–0.90→+0.5 · 0.90–1.10→0.0 · 1.10–1.20→−0.5 · r≥1.20→−1.0`), matching the codebase's "slow to call cheap" conservatism. Industry leg N/A → `val_score = self_score` (honest 1.0·self fallback; per-stock `industry_no_data`, never a fabricated leg).

### D3 — Industry leg = Option A, EastMoney-coherent, per-symbol
Stock PE vs industry-average PE under ONE taxonomy (东财行业): industry-average PE from market-wide `stock_board_industry_name_em` (1 cached call/day); stock→industry per-symbol via `stock_individual_info_em` (~15–25 deduped cached calls/run). No single-call market-wide stock→industry table exists under a PE-matching taxonomy, so the leg is per-symbol — and that is fine: it reuses the proven flow per-symbol cached pattern (ADR 0014/0019), NOT a new rate-limit risk. Rejected: Option B (per-peer true percentile, ~N×constituents fetch), Option D (sector-blind absolute ceiling). **Denominator-robustness risk:** EM's 市盈率 is a single column (cap-weighting unverified, no median variant); non-positive/NaN PE is dropped to `industry_no_data`. A breadth guard is added ONLY if EM proves arithmetic-mean — recorded here as a risk, not a pre-built knob.

### D4 — False-Cheap clamp = hard-0 in the value-trap quadrant (deliberately NOT min(blend,0))
`self_score > 0 AND r ≥ 1.2` → hard-assign `val_score = 0.0`, `false_cheap=True`. The clamp fires ONLY in the value-trap quadrant (cheap-vs-self AND rich-vs-peers), where the correct stance is to discard the whole valuation verdict to neutral (epistemic humility on a detected trap + the noise-prone industry denominator), NOT to preserve the industry leg's magnitude. The one cell `self=+0.5 ∧ r≥1.2` (unclamped blend ≈ −0.1) is nudged UP to 0.0 ON PURPOSE — that is the verdict-discard, and it keeps the board annotation `→中性` literally true. Clamp to 0, never negative (the guard removes a false bullish signal; it does not assert bearishness).

### D5 — Coverage = fraction of fund NAV; monitor floor 0.40 (deliberate divergence from opportunity's 0.50)
`covered_weight_ratio = Σ covered weight_pct / 100.0` (NAV denominator, matching `lookthrough_valuation._coverage_ratio`). The aggregate uses the FULL disclosed basket (~top-10), NOT flow's top-5 (top-5 NAV coverage is 26–41% — fatal at any floor). Monitor floor = 0.40, NOT 0.50: at 0.50 the factor fired for 1 of 7 funds and was a phantom for 6/7; at 0.40 → 6/7 (only the most diversified fund, 260112 at 0.34, stays honest-N/A). The 0.40 is a monitor-specific named constant distinct from `lookthrough._COVERAGE_FLOOR=0.50` — the monitor valuation is a 0.20-weight research lean, not a publishability gate. Coverage-scaled confidence is a deferred follow-up.

### D6 — No PEG/DCF; valuation weight unchanged at .20; engine bump "2"→"3" (global)
PEG/DCF stay dropped (D6 of the spec); the industry leg + clamp IS the False-Cheap mechanism. The valuation weight stays `.20` on `active_cn_equity` (re-base the value, not the weight — no profile change). Engine bumps `"2"→"3"` globally (all 7 active funds change look-through→bottom-up); gold/qdii's needless forward-clock reset is accepted (per-fund engine versioning is not worth the complexity on a 10-fund set). Forward-eval isolation targets `"3"`; Follow-up 1's `engine_population` WARN covers the transition.

### D7 — Reasons: factor codes vs per-stock codes
`valuation_no_data` (zero covered) + `valuation_no_coverage` (below the NAV floor) are FACTOR N/A reasons → added to `KNOWN_NA_REASONS` (10→12) with reachable `_valuation` branches. `industry_no_data` + `false_cheap_clamp` are PER-STOCK `HoldingMetric` reasons, NEVER in `KNOWN_NA_REASONS` (the factor stays eligible on self-only / the clamped stock is covered).

### D8 — Named-constant priors (governed, never auto-tuned per ADR 0018)
blend `0.60/0.40`, `_FALSE_CHEAP_RICHNESS = 1.2`, monitor floor `0.40`, industry bands `0.70/0.90/1.10/1.20`. Promote to `config/monitor.yaml` only if later tuned.

## Consequences

- The board's weighted dual-track equals the valuation factor value (reconciliation oracle, 4dp) — the methodology is legible and verifiable.
- 018132 (sector-concentrated, holdings ≈ the industry → r≈1) collapses to ~self-only; the clamp rarely fires. Acceptable; a cleaner sector-index read needs its `tracked_index` populated (out of scope).
- The post-composite veto tier (conflict hard-suppression, flow-reversal guard) stays deferred (spec §10) — judged against forward evidence that resets to engine "3" here.
- Framing held: 研究参考信号，非买卖指令 (ADR 0015).
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0020-monitor-dual-track-valuation.md
git commit -m "docs(adr): 0020 monitor dual-track valuation + False-Cheap clamp (slice 4)"
```

### Task 4.5: Final full-slice verification

**Files:** none

- [ ] **Step 1: Run all touched dirs PER FILE (tests/commands HANGS as a whole)**

```bash
uv run pytest tests/monitor/ -q              # whole monitor dir is safe
uv run pytest tests/monitor/eval/ -q         # whole eval dir is safe
# tests/commands PER FILE:
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -q
uv run pytest tests/commands/test_monitor_cmd_valuation.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd_heat.py -q
uv run pytest tests/commands/test_monitor_cmd_nav_history.py -q
uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py -q
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
uv run pytest tests/commands/test_monitor_constituent.py -q
uv run pytest tests/commands/test_monitor_snapshot.py -q
```
Expected: PASS (diff-scope any failure against the known baseline before assuming a regression — see memory "Test suite baseline").

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests`
Expected: no errors.

- [ ] **Step 3: Final commit (empty if clean)**

```bash
git add -A && git commit -m "test(monitor): dual-track valuation final verification (slice 4 complete)" --allow-empty
```

---

## Self-Review checklist (done by the plan author)

**Spec coverage:**
- §5.A `industry_valuation.py` → Slice 1 (Tasks 1.1–1.4). ✓
- §5.B dual-track + clamp + `aggregate_valuation` → Slice 2 (Tasks 2.1–2.6). ✓
- §5.C factor re-base + `ValuationResolution.path` + delete dead path + `_valuation` + `FactorInputs` field + KNOWN_NA_REASONS + `_process_fund` gate + engine bump → Slice 3 (Tasks 3.1–3.4). ✓
- §5.D board columns + badge + industry-coverage rollup + sub-0.50 note → Slice 3 (Task 3.5). ✓
- §5.E trace schema 4 + determinism + coverage + reconciliation → Slice 4 (Tasks 4.1–4.2). ✓
- §5.F engine isolation → Slice 4 (Task 4.3). ✓
- §7.1 locked tests: KNOWN_NA_REASONS ten→twelve (3.3), schema_version_3→4 (4.1), delete test_lookthrough.py (3.2), board golden (3.5), engine-isolation re-run (4.3), regression per-file (3.6/4.5). ✓
- §8 ADR 0020 → Task 4.4. ✓

**Placeholder scan:** no TBD/TODO; all code blocks complete. ✓

**Type consistency:** `DualTrack`, `StockValuation`, `HoldingMetric`, `ValuationAggregate`, `ValuationResolution.path`, `FactorInputs.valuation_aggregate`, `aggregate_valuation`, `dual_track_score`, `industry_band`, `per_stock_valuation_dual`, `build_holding_metrics(industry_by_symbol=, industry_pe_by_industry=)`, `valuation_reconciliation`, `valuation_coverage_health` — names consistent across tasks. ✓

**Known real-code deltas from spec assumptions (recorded for the impl agent):**
- `ValuationResolution` currently has 3 fields (state/cached/reason); `path` is ADDED as a trailing default (`="index"`) so existing 3-arg constructors in `holding_metrics`/tests stay green.
- `factor_maps.valuation_state_score` already returns `None` for `.get(None)` — Task 2.1 verifies; only widen the signature if the runtime narrows.
- `holding_metrics.py` imports `flow_band` is re-exported by `factor_maps`; to avoid a cycle, `valuation_state_score` is imported FUNCTION-LOCALLY inside `per_stock_valuation_dual` (Task 2.4 note).
- `eval/backtest.py::_evidence_free_composite` constructs `FactorInputs` WITHOUT `flow=` and WITHOUT `valuation_aggregate=` — it rides BOTH trailing defaults; no change needed (confirms the back-compat pattern). Re-run `tests/monitor/eval/test_backtest*.py` in Slice 3.6 to confirm.
- The standalone `drilldown_page_html` views-tuple stays 5-wide; the valuation rollup HTML is display-only (the reconciliation oracle reads the trace, not the HTML) — Task 3.5 makes it optional to avoid churning the page contract.
```
