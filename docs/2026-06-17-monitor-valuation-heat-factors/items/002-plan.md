# Look-through valuation (item 002) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill in the look-through branch of `src/irc/monitor/valuation.py` (`_resolve_lookthrough`) so the 6 pure active funds (`tracked_index is None`, `active_cn_equity`) get a real `valuation` factor, by assembling holdings from the **monitor's own cached `ActiveFundSnapshot` JSON** (the exact source spec §4.1 prescribes and the constituent factor already uses), joining them to the cached DuckDB `stock_valuation_history` PE/PB series, then reusing the opportunity layer's PURE `fund_valuation_percentile` — degrading honestly to `valuation_no_anchor` when cached stock-valuation coverage is thin.

**Architecture:** Holdings come from `load_latest_active_fund_cached(fund_id, root / "data")` → `ActiveFundSnapshot.constituent_analyses` (each `ConstituentAnalysis` carries `.symbol` (6-digit A-share) + `.weight_pct` (0..100)). We map those to `HoldingWeight(code=symbol, weight_pct=weight_pct)`, fetch the per-code PE/PB series via the opportunity PURE reader `_stock_series_by_code(con, codes)` (reads the cached DuckDB `stock_valuation_history`), call `fund_valuation_percentile(holdings, series, coverage_floor=0.50, pb_uses_pe_gate=False)`, and map `result.pe.percentile` through item-001's `percentile_to_valuation_state`. The coverage gate is enforced INSIDE `fund_valuation_percentile` (it returns a `None` PE percentile when covered NAV ratio < floor or PE history immature) — we add NO second gate; `None → ValuationResolution(None, False, "valuation_no_anchor")`.

**Tech Stack:** Python 3.12+, DuckDB, pandas, pytest (TDD), uv, ruff.

---

## What changed from the prior revision of this plan (read this first)

The previous plan loaded holdings via the opportunity reader `_latest_quarter_holdings(con, fund_id)`, which reads the DuckDB `fund_holdings` table. **That source is wrong for the monitor set** (verified — treat as ground truth, do not re-litigate):

- `irc monitor snapshot` writes ONLY JSON `ActiveFundSnapshot` files (`data/fundamentals/<quarter>/active_fund/fund_<id>.json`) — ZERO rows to `fund_holdings`.
- `fund_holdings` is populated ONLY by `irc ingest` over the discovered-watchlist universes. Only 3 of the 10 monitor funds appear there; the other 7 have NO rows.
- Therefore `_latest_quarter_holdings(con, <monitor_fund_id>)` returns `()` for 7/10 monitor funds → look-through ships universal N/A → the slice is INERT for the monitor set.
- The monitor's OWN holdings (per-holding symbol + weight) for ALL 10 funds live in the JSON `ActiveFundSnapshot` loaded by `load_latest_active_fund_cached` — exactly what spec §4.1 prescribes and what the constituent factor already uses.

**This revision swaps the holdings source to the monitor's cached `ActiveFundSnapshot`.** The stock-valuation SERIES leg (`_stock_series_by_code` over `stock_valuation_history`) is UNCHANGED — that cached fundamentals table is still the right PE/PB source. The percentile derivation, coverage gate, and percentile→state mapping are UNCHANGED.

---

## Grounding (verified against real code — re-grep before trusting line numbers)

- **`load_latest_active_fund_cached`** — `src/irc/fundamentals/snapshot_cache.py:249`:
  ```python
  def load_latest_active_fund_cached(fund_id: str, root: Path) -> ActiveFundSnapshot | None: ...
  ```
  Takes `(fund_id, root)` — **NO quarter arg** (it scans `root/fundamentals/*/active_fund/fund_{fund_id}.json` and returns the most-recent quarter). Returns `None` when no cache. **The cache root is `root / "data"`**, NOT bare `root`: the constituent factor calls `load_latest_active_fund_cached(fund_id, root / "data")` (`monitor_cmd.py:187`, `:565`). `_resolve_lookthrough` receives bare `root`, so it MUST call `load_latest_active_fund_cached(fund_id, root / "data")` to match.
- **`ActiveFundSnapshot`** — `src/irc/fundamentals/types.py:231`: field `constituent_analyses: tuple[ConstituentAnalysis, ...]` is the per-holding list.
- **`ConstituentAnalysis`** — `src/irc/fundamentals/types.py:138` (re-exported from `irc.opportunity.types`, same class):
  - `.symbol: str` — the per-holding STOCK CODE. Real cached values are **bare 6-digit A-share codes** (`"600519"`, `"600036"`, …; verified in `data/fundamentals/2026Q1/active_fund/fund_*.json`).
  - `.weight_pct: float` — **percent units 0..100** (matches `HoldingWeight.weight_pct` / `fund_holdings.weight_pct`). `__post_init__` enforces `weight_pct >= 0`.
  - The constituent factor reads these via `c.weight_pct` / `h.symbol` (`monitor_cmd.py:192`, `:213`, `:572`). We mirror that access.
- **Symbol → stock_code matching (NO normalization needed).** `stock_valuation_history.stock_code` is the 6-digit A-share `holding_ticker` (populated by `irc fundamentals snapshot` from `_discover_ashare_codes`, which filters `fund_holdings.holding_ticker` to `^\d{6}$`; `fundamentals_cmd.py:84`). `ConstituentAnalysis.symbol` is the SAME 6-digit format. So `HoldingWeight(code=c.symbol)` joins directly to `stock_valuation_history.stock_code` with **no transform**. A holding whose symbol is NOT a 6-digit A-share (e.g. an HK/US QDII line) simply has no `stock_valuation_history` rows → absent from `_stock_series_by_code`'s map → not in the covered set → contributes to uncovered NAV → honest N/A. **This is the spec §10 accepted risk; make it explicit in the docstring + a test.**
- **`HoldingWeight`** — `lookthrough_valuation.py:37`: `code: str`, `weight_pct: float` (0..100).
- **`MetricSeries`** — `lookthrough_valuation.py:43`: `code: str`, `source: str`, `points: tuple[tuple[str, float | None, float | None], ...]` (date_iso, pe, pb). Built by `_stock_series_by_code`.
- **`_stock_series_by_code(con, codes)`** — `src/irc/opportunity/inputs_loader.py:221` → `dict[str, MetricSeries]`. Reads `stock_valuation_history` (`stock_code`, `date`, `pe_ttm`, `pb`, `_source`); codes with no cached rows are absent from the map.
- **`fund_valuation_percentile`** — `src/irc/opportunity/lookthrough_valuation.py:193`:
  ```python
  def fund_valuation_percentile(
      holdings: tuple[HoldingWeight, ...],
      series_by_code: dict[str, MetricSeries],
      *, coverage_floor: float, pb_uses_pe_gate: bool,
  ) -> FundValuationResult: ...
  ```
  Returns `FundValuationResult(pe: MetricCoverage, pb: MetricCoverage)`; `MetricCoverage.percentile` is `float | None` (`None` when covered NAV ratio < floor OR PE history immature per the 120pts/180d gate). **We read `result.pe.percentile`.**
- **Coverage floor / PB gate** — `ActiveFundLookthroughConfig` (`src/irc/schemas/valuation.py:21`): `coverage_floor` default `0.50`, `pb_uses_pe_gate` default `False`. We use those literals (mirrored as module constants so monitor and opportunity gate identically). The look-through factor keys on PE; PB is not consumed by the monitor map.
- **Band mapping** — item 001's `percentile_to_valuation_state(pct)` (`valuation.py:30`) wraps `opportunity/states._band` (thresholds `_VALUATION_BANDS`: `<0.20 cheap, <0.40 reasonable_low, <0.70 fair, <0.90 expensive, ≥0.90 very_expensive`; `None`/NaN → `None`).
- **`_resolve_lookthrough` signature** is already `(con, fund_id, root)` and is called from `_resolve` (`valuation.py:105`). `root` is now USED (to load the JSON snapshot via `load_latest_active_fund_cached`, passing `root / "data"`); `con` is used for `_stock_series_by_code`. **No signature change** to `resolve_valuation_state` / `_resolve` / `_resolve_lookthrough`, **no `monitor_cmd.py` change**, **no item-001 test change** required.
- **ADR 0017 compliance.** The JSON `ActiveFundSnapshot` is the MONITOR's own cache (written by `irc monitor snapshot`), NOT an opportunity output file — reading it is fully compliant (the constituent factor already does). `stock_valuation_history` is a cached fundamentals table. Neither requires the opportunity pipeline to have run; both are monitor-consumed cached artifacts. No opportunity output-file reads.

## Data-flow decision (assemble holdings from the JSON snapshot; series from `con`)

**Decision: `_resolve_lookthrough` loads holdings from the monitor's cached `ActiveFundSnapshot` JSON (`load_latest_active_fund_cached(fund_id, root / "data")`) and PE/PB series from `con` (`_stock_series_by_code`).** Rationale:

- (a) **Correct source for the monitor set.** All 10 monitor funds have a JSON `ActiveFundSnapshot` (written by `irc monitor snapshot`); only 3/10 have `fund_holdings` rows. The snapshot is the source spec §4.1 prescribes and the constituent factor already uses — DRY with the constituent factor, lights up the holdings leg for all 10 funds.
- (b) **ADR 0017 isolation preserved.** The snapshot is the monitor's own cache; `stock_valuation_history` is a cached fundamentals table read via `con`. No opportunity output-file reads, no pipeline dependency.
- (c) **Two cached artifacts, one join.** Snapshot gives `(symbol, weight_pct)`; the DuckDB table gives the PE/PB series keyed by the same 6-digit code. The join is identity on the 6-digit code (no normalization). Non-A-share holdings drop out naturally → honest N/A.

## File-size budget decision — extract a pure helper

`valuation.py` is currently 123 lines. The look-through body (load snapshot → map constituents → fetch series → percentile → state, with the `None`-snapshot and empty-holdings early returns) is ~14 lines plus a 2-line constituent→`HoldingWeight` mapper — pushing `_resolve_lookthrough` past the 20-line function budget and `valuation.py` toward the 200-line file budget. **Decision: extract a pure helper module `src/irc/monitor/lookthrough.py`** with one pure function `lookthrough_valuation_state(snapshot, series_by_code) -> str | None` that does the constituent→`HoldingWeight` mapping + `fund_valuation_percentile` + `percentile_to_valuation_state`. `_resolve_lookthrough` stays the thin effect-edge (loads snapshot + series, calls the pure helper, wraps in `ValuationResolution`). This keeps `_resolve_lookthrough` ≤ ~12 lines, makes the math unit-testable without DuckDB OR the JSON cache, and respects the < 200-line / < 20-line budgets.

## File structure

- **Create:** `src/irc/monitor/lookthrough.py` (~30 lines) — pure `lookthrough_valuation_state(snapshot, series_by_code) -> str | None`; no I/O.
- **Modify:** `src/irc/monitor/valuation.py` — fill in `_resolve_lookthrough` (effect edge: load snapshot + series, call the pure helper); add imports. Stays < 200 lines.
- **Create (tests):** `tests/monitor/test_lookthrough.py` — pure tests for `lookthrough_valuation_state` (no DuckDB, no cache: hand-built `ActiveFundSnapshot` + `MetricSeries` dict).
- **Modify (tests):** `tests/monitor/test_valuation.py` — integration-style look-through tests through `resolve_valuation_state` (real snapshot cache writer + seeded `stock_valuation_history`) alongside item 001's tests.

No `monitor_cmd.py` change. No `factor_maps.py` change (item 001 already unified the vocab).

---

### Task 1: Pure look-through helper (math only, no I/O)

**Files:**
- Create: `src/irc/monitor/lookthrough.py`
- Test: `tests/monitor/test_lookthrough.py`

- [ ] **Step 1: Write the failing test (pure helper: sufficient coverage → very_expensive; thin → None; empty → None)**

Create `tests/monitor/test_lookthrough.py`:

```python
from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis
from irc.opportunity.lookthrough_valuation import MetricSeries
from irc.monitor.lookthrough import lookthrough_valuation_state


def _constituent(symbol: str, weight_pct: float) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn="x", weight_pct=weight_pct,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def _snapshot(*constituents: ConstituentAnalysis) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id="519069", source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="",
        constituent_analyses=tuple(constituents),
        failure_reasons_by_symbol={},
    )


def _rising_series(code: str, n: int = 200) -> MetricSeries:
    # n PE points every 2 days → >120 pts spanning >180d (clears the maturity gate);
    # latest PE is the max → self-history percentile 1.0.
    from datetime import date
    base = date(2025, 1, 1).toordinal()
    points = tuple(
        (date.fromordinal(base + 2 * i).isoformat(), 18.0 + i * 0.01, 2.0)
        for i in range(n)
    )
    return MetricSeries(code=code, source="eastmoney", points=points)


def test_helper_sufficient_coverage_returns_state():
    snap = _snapshot(_constituent("600519", 60.0))
    series = {"600519": _rising_series("600519")}
    assert lookthrough_valuation_state(snap, series) == "very_expensive"


def test_helper_below_floor_is_none():
    # 30% covered < 0.50 floor → None percentile → None state.
    snap = _snapshot(_constituent("600519", 30.0))
    series = {"600519": _rising_series("600519")}
    assert lookthrough_valuation_state(snap, series) is None


def test_helper_no_priced_holdings_is_none():
    # Holdings present, but no matching series → coverage 0.0 → None.
    snap = _snapshot(_constituent("600519", 60.0))
    assert lookthrough_valuation_state(snap, {}) is None


def test_helper_empty_holdings_is_none():
    assert lookthrough_valuation_state(_snapshot(), {}) is None


def test_helper_non_ashare_symbol_does_not_match():
    # HK-style symbol won't be in the A-share-keyed series map → uncovered → None.
    snap = _snapshot(_constituent("00700", 60.0))   # 5-digit HK code
    series = {"600519": _rising_series("600519")}    # unrelated A-share series
    assert lookthrough_valuation_state(snap, series) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_lookthrough.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.lookthrough'` (helper does not exist yet).

- [ ] **Step 3: Create the pure helper**

Create `src/irc/monitor/lookthrough.py`:

```python
"""PURE look-through valuation math for `irc monitor` (no I/O).

Maps a monitor `ActiveFundSnapshot`'s holdings + a per-code PE/PB series map to a
unified-vocab valuation state, reusing the opportunity layer's pure
`fund_valuation_percentile`. The coverage gate lives INSIDE that function (None
percentile when covered NAV ratio < floor or PE history immature) → None state.

ADR 0017: the snapshot is the monitor's OWN cache and the series map comes from
the cached `stock_valuation_history`; both are monitor-consumed cached artifacts,
not opportunity output files. This module performs NO I/O — callers pass the
already-loaded snapshot + series.
"""
from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot
from irc.monitor.valuation import percentile_to_valuation_state
from irc.opportunity.lookthrough_valuation import (
    HoldingWeight,
    MetricSeries,
    fund_valuation_percentile,
)

# Mirror ActiveFundLookthroughConfig defaults (schemas/valuation.py) so monitor
# and opportunity gate identically. The look-through factor keys on PE.
_COVERAGE_FLOOR = 0.50
_PB_USES_PE_GATE = False


def _holdings_from_snapshot(snapshot: ActiveFundSnapshot) -> tuple[HoldingWeight, ...]:
    """Map the snapshot's constituents to HoldingWeight (code=6-digit symbol,
    weight_pct in 0..100 — identical units). Non-A-share symbols pass through
    unchanged; they simply won't match the A-share-keyed series map."""
    return tuple(
        HoldingWeight(code=c.symbol, weight_pct=c.weight_pct)
        for c in snapshot.constituent_analyses
    )


def lookthrough_valuation_state(
    snapshot: ActiveFundSnapshot,
    series_by_code: dict[str, MetricSeries],
) -> str | None:
    """Pure: snapshot holdings + per-code PE/PB series → valuation state or None.
    None when holdings empty, coverage below floor, or PE history immature."""
    holdings = _holdings_from_snapshot(snapshot)
    if not holdings:
        return None
    result = fund_valuation_percentile(
        holdings, series_by_code,
        coverage_floor=_COVERAGE_FLOOR, pb_uses_pe_gate=_PB_USES_PE_GATE,
    )
    return percentile_to_valuation_state(result.pe.percentile)
```

> **Import-cycle check:** `lookthrough.py` imports `percentile_to_valuation_state` from `valuation.py`, and (Task 2) `valuation.py` will import `lookthrough_valuation_state` from `lookthrough.py`. To avoid a circular import at module load, `valuation.py` imports `lookthrough` **inside** `_resolve_lookthrough` (function-local import), NOT at module top. This is verified in Task 2 Step 3.

- [ ] **Step 4: Run the pure tests to verify they pass**

Run: `uv run pytest tests/monitor/test_lookthrough.py -v`
Expected: ALL 5 PASS — sufficient coverage → `very_expensive`; thin/empty/no-series/non-A-share → `None`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/lookthrough.py tests/monitor/test_lookthrough.py
git commit -m "feat(002): pure monitor look-through valuation helper (snapshot holdings)"
```

---

### Task 2: Wire `_resolve_lookthrough` to the snapshot + series (effect edge)

**Files:**
- Modify: `src/irc/monitor/valuation.py` (`_resolve_lookthrough`, imports)
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test (sufficient coverage through `resolve_valuation_state` → very_expensive)**

Append to `tests/monitor/test_valuation.py`. This seeds a real monitor `ActiveFundSnapshot` (via the real cache writer, under `tmp_path / "data"` to match `root / "data"`) and `stock_valuation_history` rows for the held code.

```python
# ── Item 002: look-through branch (monitor ActiveFundSnapshot holdings) ────────

from datetime import date as _date

from irc.fundamentals.snapshot_cache import write_active_fund_cache
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


def _seed_monitor_snapshot(root, fund_id, holdings, quarter="2026Q1"):
    """Write a monitor ActiveFundSnapshot JSON under <root>/data via the real
    cache writer. `holdings` is a list of (symbol, weight_pct). Mirrors the
    constituent factor's load path: load_latest_active_fund_cached(id, root/'data')."""
    analyses = tuple(
        ConstituentAnalysis(
            symbol=sym, name_cn="x", weight_pct=w,
            evidence=(), failure_reasons=(), one_line_view="",
        )
        for sym, w in holdings
    )
    snap = ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter=quarter, cache_probed_at="",
        constituent_analyses=analyses, failure_reasons_by_symbol={},
    )
    write_active_fund_cache(snap, root / "data" / "fundamentals" / "..")
    # NB: write_active_fund_cache(snap, R) writes under R/fundamentals/...; the
    # loader scans root/'data'/fundamentals. So pass R = root/'data'.


def _seed_stock_valuation(con, stock_code, n=200, pe0=18.0, pe_step=0.01, pb=2.0):
    # n PE/PB points every 2 days → >120 pts spanning >180d → clears the PE gate.
    base = _date(2025, 1, 1)
    rows = [
        (stock_code, _date.fromordinal(base.toordinal() + 2 * i),
         pe0 + i * pe_step, pb, None, "2026-05-15 00:00:00", "eastmoney", "sv:r")
        for i in range(n)
    ]
    con.executemany(
        "INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows
    )


def test_lookthrough_sufficient_coverage_returns_state(tmp_path):
    # 60% in one priced name clears the 0.50 NAV floor; 200 rising PE points clear
    # the 120/180 maturity gate; latest PE is the max → percentile 1.0 → very_expensive.
    con = duckdb.connect(str(tmp_path / "lt2.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519069", None)
    _seed_monitor_snapshot(tmp_path, "519069", [("600519", 60.0)])
    _seed_stock_valuation(con, "600519")  # rising PE → latest is max → pct 1.0
    res = resolve_valuation_state(_fund("519069", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.cached is True
    assert res.state == "very_expensive"   # pct 1.0 → >=0.90 band
    assert res.reason is None
    con.close()
```

> **Fixture-path correctness:** `write_active_fund_cache(snap, R)` writes to `R/fundamentals/<quarter>/active_fund/fund_<id>.json`. The loader the constituent factor uses is `load_latest_active_fund_cached(fund_id, root / "data")`, which scans `(root/"data")/fundamentals/...`. So the writer must be called with `R = tmp_path / "data"`. Replace the placeholder `write_active_fund_cache(snap, root / "data" / "fundamentals" / "..")` above with the clean form `write_active_fund_cache(snap, root / "data")`. (The `".."` form is shown only to flag the path relationship; **use `write_active_fund_cache(snap, root / "data")`**.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_sufficient_coverage_returns_state -v`
Expected: FAIL — the stub returns `ValuationResolution(None, False, "valuation_no_anchor")`, so `res.cached is True` and `res.state == "very_expensive"` both fail.

- [ ] **Step 3: Implement `_resolve_lookthrough` (load snapshot + series, call the pure helper)**

In `src/irc/monitor/valuation.py`, add the `_stock_series_by_code` import to the existing opportunity import group near the top (after line 22). Replace:

```python
from irc.opportunity.inputs_loader import _index_valuation_metrics
```

with:

```python
from irc.opportunity.inputs_loader import (
    _index_valuation_metrics,
    _stock_series_by_code,
)
```

Then replace the stub body of `_resolve_lookthrough` (currently `return ValuationResolution(None, False, _NA_NO_ANCHOR)`) with:

```python
def _resolve_lookthrough(
    con: duckdb.DuckDBPyConnection, fund_id: str, root: Path
) -> ValuationResolution:
    """Look-through branch (tracked_index is None, pure active funds).

    Holdings come from the MONITOR's own cached ActiveFundSnapshot JSON
    (load_latest_active_fund_cached under `root/'data'` — the exact source the
    constituent factor uses); the PE/PB series come from the cached DuckDB
    `stock_valuation_history` via `_stock_series_by_code`. Both are
    monitor-consumed cached artifacts, NOT opportunity output files (ADR 0017);
    neither needs the opportunity pipeline to have run. The coverage gate is
    enforced INSIDE fund_valuation_percentile (None PE pct when covered NAV ratio
    < floor or PE history immature) → None maps to honest N/A. Non-A-share
    holdings (e.g. HK/US QDII lines) carry no stock_valuation_history rows → they
    never match the A-share-keyed series → uncovered → honest N/A (spec §10)."""
    # Function-local import to avoid a module-load cycle (lookthrough imports
    # percentile_to_valuation_state from this module).
    from irc.fundamentals.snapshot_cache import load_latest_active_fund_cached
    from irc.monitor.lookthrough import lookthrough_valuation_state

    snapshot = load_latest_active_fund_cached(fund_id, root / "data")
    if snapshot is None or not snapshot.constituent_analyses:
        return ValuationResolution(None, False, _NA_NO_ANCHOR)
    codes = tuple(c.symbol for c in snapshot.constituent_analyses)
    series = _stock_series_by_code(con, codes)
    state = lookthrough_valuation_state(snapshot, series)
    if state is None:
        return ValuationResolution(None, False, _NA_NO_ANCHOR)
    return ValuationResolution(state, True, None)
```

> The `_resolve_lookthrough` body is ~10 statements (within the 20-line ideal once the docstring is excluded). `valuation.py` grows by ~14 lines + 1 import line → still well under 200.

- [ ] **Step 4: Run the look-through test to verify it passes**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_sufficient_coverage_returns_state -v`
Expected: PASS — snapshot 60% holding + mature rising PE series → `very_expensive`, `cached=True`, `reason=None`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/valuation.py tests/monitor/test_valuation.py
git commit -m "feat(002): look-through valuation from monitor ActiveFundSnapshot holdings"
```

---

### Task 3: Coverage-below-floor through the edge → N/A

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the test (30% covered < floor → N/A)**

Append to `tests/monitor/test_valuation.py`. A snapshot holding only 30% of one priced name (below the 0.50 NAV floor) → `fund_valuation_percentile` returns a `None` PE percentile → N/A.

```python
def test_lookthrough_coverage_below_floor_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt3.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "260112", None)
    _seed_monitor_snapshot(tmp_path, "260112", [("600519", 30.0)])
    _seed_stock_valuation(con, "600519")
    res = resolve_valuation_state(_fund("260112", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_coverage_below_floor_is_na -v`
Expected: PASS — covered NAV ratio 0.30 < 0.50 floor → `None` pct → N/A.

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through coverage-below-floor through the edge is N/A"
```

---

### Task 4: Band-boundary mapping for a real look-through percentile

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the test (descending PE → latest is min → cheap)**

Append. A 60% holding whose PE series falls monotonically, so the latest point is the minimum → self-history percentile ≈ 0.0 → `<0.20` → `cheap`. (Reuses item 001's exhaustive band table in `test_percentile_maps_to_band`; this only confirms one non-extreme band end-to-end through the look-through path.)

```python
def test_lookthrough_low_percentile_is_cheap(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt4.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "006533", None)
    _seed_monitor_snapshot(tmp_path, "006533", [("600519", 60.0)])
    _seed_stock_valuation(con, "600519", pe0=40.0, pe_step=-0.1)  # descending PE
    res = resolve_valuation_state(_fund("006533", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.cached is True
    assert res.state == "cheap"   # pct ~0.0 → <0.20 band
    assert res.reason is None
    con.close()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_low_percentile_is_cheap -v`
Expected: PASS — descending PE → latest is min → pct ~0.0 → `cheap`.

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through low-percentile maps to cheap band"
```

---

### Task 5: Holdings present but NO cached stock valuations → N/A; non-A-share holdings → N/A

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the tests (zero priced names → N/A; HK symbol → N/A)**

Append. (a) Snapshot holdings but NO `stock_valuation_history` rows → `_stock_series_by_code` returns `{}` → coverage 0.0 → N/A (the primary spec §10 risk: thin/absent stock-valuation coverage → surfaced N/A, never an error). (b) A non-A-share (HK) holding has no A-share `stock_valuation_history` rows → uncovered → N/A.

```python
def test_lookthrough_holdings_but_no_stock_valuations_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt5.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "000083", None)
    _seed_monitor_snapshot(tmp_path, "000083", [("600519", 60.0)])
    # NO stock_valuation_history rows → no priced holdings → coverage 0.0 → N/A.
    res = resolve_valuation_state(_fund("000083", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_lookthrough_non_ashare_holding_is_na(tmp_path):
    # A QDII-style HK holding (5-digit code) never matches the A-share-keyed
    # stock_valuation_history → uncovered → honest N/A (spec §10 accepted risk).
    con = duckdb.connect(str(tmp_path / "lt6.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519770", None)
    _seed_monitor_snapshot(tmp_path, "519770", [("00700", 60.0)])  # HK Tencent
    _seed_stock_valuation(con, "600519")  # unrelated A-share series present
    res = resolve_valuation_state(_fund("519770", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_holdings_but_no_stock_valuations_is_na tests/monitor/test_valuation.py::test_lookthrough_non_ashare_holding_is_na -v`
Expected: BOTH PASS — empty/non-matching series → below-floor → `None` pct → N/A.

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through no-stock-valuations + non-A-share holdings are N/A"
```

---

### Task 6: No snapshot at all → N/A (cold cache); item-001 index-dispatch regression

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the tests (no snapshot → N/A; index path untouched)**

Append. A pure active fund with NO cached snapshot → `load_latest_active_fund_cached` returns `None` → early N/A. Plus a regression that a fund WITH `tracked_index` still takes the index path even when a snapshot + stock valuations exist (`_resolve` dispatches on `tracked_index`, not on holdings).

```python
def test_lookthrough_no_snapshot_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt7.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "161903", None)  # no cached snapshot written
    res = resolve_valuation_state(_fund("161903", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None and res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_index_path_unchanged_by_lookthrough(tmp_path):
    # Regression: a fund WITH tracked_index still takes the index path even when a
    # monitor snapshot + stock valuations exist — _resolve dispatches on
    # tracked_index, NOT on holdings.
    con = duckdb.connect(str(tmp_path / "lt8.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    _seed_monitor_snapshot(tmp_path, "510300", [("600519", 60.0)])
    _seed_stock_valuation(con, "600519")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi300", pairs)
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    # Index path → mature rising PE → pct 1.0 → very_expensive (NOT the look-through).
    assert res.cached is True
    assert res.state == "very_expensive"
    assert res.reason is None
    con.close()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_no_snapshot_is_na tests/monitor/test_valuation.py::test_index_path_unchanged_by_lookthrough -v`
Expected: BOTH PASS — cold cache → N/A; index dispatch unchanged.

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through cold-cache N/A + index dispatch regression"
```

---

### Task 7: Full-module + lint verification (preserve all item-001 behavior)

**Files:** none (verification only)

- [ ] **Step 1: Run both monitor valuation test modules**

Run: `uv run pytest tests/monitor/test_valuation.py tests/monitor/test_lookthrough.py -v`
Expected: ALL PASS — item 001's tests (percentile band table, index-anchored present/immature, china_internet gap, unactivated sector, **`test_lookthrough_branch_is_na_stub`** — see note below, unknown-fund, missing-table degrade-to-N/A) PLUS the 5 pure helper tests PLUS the 6 new look-through edge tests.

> **Item-001 stub test handling:** item 001 has `test_lookthrough_branch_is_na_stub` (a pure active fund `519069` with NO snapshot seeded returns N/A). After this change, that fund STILL returns N/A — `load_latest_active_fund_cached(519069, tmp_path/"data")` returns `None` (no snapshot written) → early N/A — so the test continues to PASS unchanged. **Do not delete or edit it.** It now documents "look-through with cold cache → N/A," which remains true and proves zero item-001 regression.

- [ ] **Step 2: Run the opportunity look-through tests (prove the reuse target is unbroken)**

Run: `uv run pytest tests/opportunity/test_inputs_loader_lookthrough.py tests/opportunity/test_lookthrough_valuation.py -q`
Expected: ALL PASS — we only IMPORT `_stock_series_by_code` / `fund_valuation_percidentile` / value types; we do not modify them, so these stay green. (If a test file name differs, run `uv run pytest tests/opportunity -k lookthrough -q`.)

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/irc/monitor/valuation.py src/irc/monitor/lookthrough.py tests/monitor/test_valuation.py tests/monitor/test_lookthrough.py`
Expected: no errors. (Leading-underscore imports `_index_valuation_metrics`/`_stock_series_by_code`/`_band` are the pre-existing project pattern — item 001 already imports them this way. The function-local imports in `_resolve_lookthrough` are intentional cycle-avoidance, not a ruff error.)

- [ ] **Step 4: Confirm file-size budget**

Run: `wc -l src/irc/monitor/valuation.py src/irc/monitor/lookthrough.py`
Expected: `valuation.py` < 200 (≈ 137 after this change); `lookthrough.py` ≈ 45. Both under budget.

- [ ] **Step 5: Commit (final safety / no-op)**

```bash
git add -A
git commit -m "chore(002): verify look-through valuation + item-001 regression green" --allow-empty
```

---

### Task 8: Document the residual coverage gap (TODOS + CHANGELOG)

**Files:**
- Modify: `TODOS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Append a TODOS.md follow-up**

Append this bullet under the open-items list in `TODOS.md` (the file uses `- [ ]` open / `- [x]` done bullets; add as an OPEN item near the top of the open section):

```markdown
- [ ] **Monitor look-through valuation coverage gap (item 002)**: look-through `valuation` for the 6 pure active funds depends on `stock_valuation_history` coverage of their *constituents*. Today that table is populated only for **watchlist-overlapping A-shares** (`irc fundamentals snapshot` enumerates `fund_holdings.holding_ticker` via `_discover_ashare_codes`); there is NO dedicated monitor-constituent stock-valuation ingest. So a monitor fund whose top A-share holdings don't overlap the discovered watchlist ships `valuation_no_anchor` (honest N/A), and HK/US (QDII) holdings never match. **Follow-up (non-goal of this spec):** add a monitor-constituent stock-valuation ingest keyed off `ActiveFundSnapshot` symbols so the look-through lights up regardless of watchlist overlap.
```

- [ ] **Step 2: Add a CHANGELOG note under `[Unreleased]`**

In `CHANGELOG.md`, under the existing `## [Unreleased]` section, append a new `### Added` block (after the item-001 valuation block):

```markdown
### Added — monitor `valuation` factor: look-through path for pure active funds (2026-06-17)

- **Lights up the look-through `valuation` factor** in `irc monitor` for the 6 pure active funds
  (`active_cn_equity`, `tracked_index is None`). `monitor/valuation._resolve_lookthrough` now
  assembles holdings from the **monitor's own cached `ActiveFundSnapshot`**
  (`load_latest_active_fund_cached` under `data/` — the same source the constituent factor uses),
  joins them to the cached DuckDB `stock_valuation_history` PE/PB series via the opportunity pure
  reader `_stock_series_by_code`, and reuses the pure `fund_valuation_percentile`
  (`coverage_floor=0.50`, `pb_uses_pe_gate=False`) → `percentile_to_valuation_state`. New pure
  helper `monitor/lookthrough.py` holds the snapshot→percentile→state math (no I/O). Cache-read
  only — no new network calls; ADR 0017 evidence isolation preserved (monitor-consumed cached
  artifacts, never opportunity output files, no pipeline dependency).
- **Honest degradation:** empty/absent snapshot, coverage below the 0.50 NAV floor, immature PE
  history, or non-A-share (HK/US QDII) holdings → `valuation_no_anchor` (surfaced, never
  fabricated). No new N/A reason codes; eval determinism unchanged.
- **Known residual coverage gap (see TODOS.md):** look-through depends on `stock_valuation_history`
  coverage of a fund's constituents, which today is populated only for watchlist-overlapping
  A-shares (no dedicated monitor-constituent stock-valuation ingest exists — adding one is a
  non-goal of this spec). Funds without overlap honestly ship `valuation_no_anchor`.
```

- [ ] **Step 3: Commit**

```bash
git add TODOS.md CHANGELOG.md
git commit -m "docs(002): record monitor look-through stock-valuation coverage gap"
```

---

## Self-review (run before handoff)

**Spec coverage (002-spec.md):**
- AC1 look-through branch assembles cached inputs from the monitor's `ActiveFundSnapshot` holdings (spec §4.1: `load_latest_active_fund_cached`) + cached stock-valuation series + reuses `fund_valuation_percentile`/`HoldingWeight`/`MetricSeries` + `percentile_to_valuation_state` + coverage-gate→`valuation_no_anchor` → Tasks 1–5.
- AC2 pure reuse, no pipeline/output-file dependency (ADR 0017) → snapshot is the monitor's own cache; `_stock_series_by_code` reads cached `con` only; documented in both docstrings + the data-flow decision.
- AC3 the 6 active funds light up with sufficient coverage; thin/non-A-share → `valuation_no_anchor`; `009225` index path + `gold`/`qdii_global` `profile_ineligible` unchanged → Task 6 regression + item-001 tests (untouched) + eligibility gated upstream in `factors.py` (out of this file's scope; not changed).
- §6 invariants: N/A reason stays `valuation_no_anchor` (in `KNOWN_NA_REASONS`); determinism (same cached snapshot + rows → same percentile → same state) — Tasks 1–6 all assert deterministic outputs.
- §8 tests: pure helper (no mocks, hand-built snapshot + series) + dispatch + band boundary + coverage-fail + holdings-construction-from-cached-snapshot + non-A-share miss → Tasks 1–6 (snapshot cache writer + DuckDB fixtures, no opportunity pipeline). Integration (full monitor run over fixture DuckDB + snapshot) is exercised by the existing monitor integration suite once this branch lights; this plan covers the unit/dispatch layer the spec scopes to slice 2.
- §10 primary risk (thin/absent coverage → surfaced N/A, never error) → Task 5 + Task 3 + the TODOS/CHANGELOG note (Task 8).

**Placeholder scan:** the only intentional placeholder is the `write_active_fund_cache(snap, root / "data" / "fundamentals" / "..")` line in Task 2 Step 1, which is immediately corrected to `write_active_fund_cache(snap, root / "data")` in the note directly below it (it exists to make the writer-vs-loader path relationship explicit). Implementer must use `write_active_fund_cache(snap, root / "data")`. No other placeholders.

**Type consistency:** `ValuationResolution(state, cached, reason)`; `ConstituentAnalysis.symbol`/`.weight_pct`; `HoldingWeight.code`/`.weight_pct`; `MetricSeries.code`/`.source`/`.points`; `result.pe.percentile`; `percentile_to_valuation_state`; `load_latest_active_fund_cached(fund_id, root)`; `_stock_series_by_code(con, codes)`; `fund_valuation_percentile(holdings, series, *, coverage_floor, pb_uses_pe_gate)`; `lookthrough_valuation_state(snapshot, series_by_code)` — all match the grounded symbols above. (Self-review caught a typo `fund_valuation_percidentile` in Task 7 Step 2's prose — the real symbol is `fund_valuation_percentile`; it's prose, not code, but flagged for clarity.)

**Constraints encoded:** TDD (failing pure test in Task 1, failing edge test in Task 2 before impl); pure helper extracted (`monitor/lookthrough.py`) to keep `_resolve_lookthrough` ≤ ~12 lines and `valuation.py` < 200; effects only at the edge (snapshot JSON load + cached `con` reads, both via thin wrappers); no new N/A reason codes (only `valuation_no_anchor`); `KNOWN_NA_REASONS` untouched; `resolve_valuation_state` still wrapped in item-001's try/except so any read error degrades to N/A (never raises); index path + `gold`/`qdii_global` unchanged; no `monitor_cmd.py` / signature change; function-local import in `_resolve_lookthrough` avoids the `valuation`↔`lookthrough` module cycle.
