# Look-through valuation (item 002) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill in the look-through branch of `src/irc/monitor/valuation.py` (`_resolve_lookthrough`) so the 6 pure active funds (`tracked_index is None`, `active_cn_equity`) get a real `valuation` factor, by reusing the opportunity layer's PURE cached-DuckDB look-through readers + `fund_valuation_percentile` — degrading honestly to `valuation_no_anchor` when cached stock-valuation coverage is thin.

**Architecture:** The opportunity layer already has two PURE cached-DuckDB readers — `_latest_quarter_holdings(con, instrument_id) -> tuple[HoldingWeight, ...]` and `_stock_series_by_code(con, codes) -> dict[str, MetricSeries]` (both in `src/irc/opportunity/inputs_loader.py`) — that read the SAME `fund_holdings` + `stock_valuation_history` DuckDB tables the monitor already consumes. The look-through branch imports and reuses these, calls the pure `fund_valuation_percentile(...)` with the opportunity's `coverage_floor=0.50` / `pb_uses_pe_gate=False` defaults, and maps `result.pe.percentile` through the item-001 helper `percentile_to_valuation_state`. The coverage gate is enforced INSIDE `fund_valuation_percentile` (it returns a `None` percentile when the covered NAV ratio < `coverage_floor` or PE history is immature) — we do NOT add a second gate; we map `None → ValuationResolution(None, False, "valuation_no_anchor")`.

**Tech Stack:** Python 3.12+, DuckDB, pandas, pytest (TDD), uv, ruff.

---

## Grounding (verified against real code — re-grep before trusting line numbers)

- **`fund_valuation_percentile`** — `src/irc/opportunity/lookthrough_valuation.py:193`:
  ```python
  def fund_valuation_percentile(
      holdings: tuple[HoldingWeight, ...],
      series_by_code: dict[str, MetricSeries],
      *, coverage_floor: float, pb_uses_pe_gate: bool,
  ) -> FundValuationResult: ...
  ```
  Returns `FundValuationResult(pe: MetricCoverage, pb: MetricCoverage)`; `MetricCoverage.percentile` is `float | None` (`None` when below the coverage floor OR PE history immature per the 120pts/180d gate). **We read `result.pe.percentile`.**
- **`HoldingWeight`** — `lookthrough_valuation.py:37`: `code: str`, `weight_pct: float` (percent units 0..100, matches `fund_holdings.weight_pct`).
- **`MetricSeries`** — `lookthrough_valuation.py:43`: `code: str`, `source: str`, `points: tuple[tuple[str, float | None, float | None], ...]` (date_iso, pe, pb).
- **Reuse readers (PURE cached DuckDB)** — both in `src/irc/opportunity/inputs_loader.py`:
  - `_latest_quarter_holdings(con, instrument_id)` (`:202`) → reads `fund_holdings` (cols `holding_ticker`, `weight_pct`) at the latest `report_date`; `()` when empty.
  - `_stock_series_by_code(con, codes)` (`:221`) → reads `stock_valuation_history` (cols `stock_code`, `date`, `pe_ttm`, `pb`, `_source`); codes with no cached rows are simply absent from the map.
- **Coverage floor / PB gate** — `ActiveFundLookthroughConfig` (`src/irc/schemas/valuation.py:21`): `coverage_floor` default `0.50`, `pb_uses_pe_gate` default `False`. The opportunity look-through call (`inputs_loader.py:258`) passes exactly these. We use the literals `coverage_floor=0.50, pb_uses_pe_gate=False` (the look-through factor keys on PE; PB is not consumed by the monitor map).
- **Tables** — `src/irc/data/duckdb_helper.py`: `fund_holdings` (`:69`, cols above + provenance), `stock_valuation_history` (`:105`, cols above + provenance). Populated by `irc ingest` (holdings) and `irc fundamentals` (stock valuations) — the shared cached fundamentals tables, NOT by `irc monitor snapshot`'s JSON `ActiveFundSnapshot`.
- **Band mapping** — item 001's `percentile_to_valuation_state(pct)` (`valuation.py:30`) wraps `opportunity/states._band` (thresholds `_VALUATION_BANDS`: `<0.20 cheap, <0.40 reasonable_low, <0.70 fair, <0.90 expensive, ≥0.90 very_expensive`; `None`/NaN → `None`).
- **`_resolve_lookthrough` signature** is already `(con, fund_id, root)` and is called from `_resolve` (`valuation.py:105`). The DuckDB readers need only `con` + `fund_id`, so **no signature change** to `resolve_valuation_state` / `_resolve` / `_resolve_lookthrough` and **no `monitor_cmd.py` change** and **no item-001 test change** are required.

## Data-flow decision (load inside the branch from `con` — do NOT thread holdings in)

**Decision: `_resolve_lookthrough` loads holdings itself from `con` via the reused `_latest_quarter_holdings`.** Rationale:

- (a) **No redundant load that matters.** `_process_fund` does load a holdings object (`load_latest_active_fund_cached`), but that is the JSON `ActiveFundSnapshot` (constituent-news source for the *constituent* factor), keyed `symbol`/`weight_pct`. The look-through valuation needs PE/PB series joined to holding codes, which lives in the DuckDB `stock_valuation_history` table keyed by `stock_code`. The matching holdings source for that join is the DuckDB `fund_holdings` table (`holding_ticker`). These are two different cached artifacts; the snapshot object is the WRONG source to thread in. So there is no "already-loaded" DuckDB holdings to thread.
- (b) **ADR 0017 isolation preserved.** Both readers operate on `con` (monitor-loaded cached DuckDB tables); no opportunity output-file reads, no pipeline dependency. The `root` param stays unused here (kept for signature stability / future cache-path use).
- (c) **Smallest function.** Loading via the two reused readers keeps `_resolve_lookthrough` to ~8 lines and adds zero new args to the public API.

> **Note for the impl agent (spec wording vs. reuse target):** the spec (§4.1, 002-spec AC1) says "the same `load_latest_active_fund_cached` / `build_constituent_pool` the constituent factor uses." That describes the *intent* (reuse the monitor's already-cached holdings, no new fetch). The precise PURE reuse target that joins to `stock_valuation_history` is the opportunity DuckDB pair `_latest_quarter_holdings` + `_stock_series_by_code` — same cached fundamentals tables, fully DRY with the opportunity look-through, and the only source that carries the PE/PB series the percentile needs. We follow the reuse *principle* (§4 "reuse, do not reimplement"; reuse boundary §4.1) using the DuckDB readers. This is a documented judgment call, not a deviation from the isolation contract.

## File structure

- **Modify:** `src/irc/monitor/valuation.py` — fill in `_resolve_lookthrough`; add two imports. Stays < 200 lines (currently 123; this adds ~6 lines of body + 1 import line). No helper-module extraction needed.
- **Modify (tests):** `tests/monitor/test_valuation.py` — add look-through tests (holdings + stock-valuation DuckDB seeding) alongside item 001's tests. Test file already mirrors source.

No new source file. No `monitor_cmd.py` change. No `factor_maps.py` change (item 001 already unified the vocab).

---

### Task 1: Coverage-miss → N/A (too few priced holdings)

**Files:**
- Modify: `src/irc/monitor/valuation.py` (`_resolve_lookthrough`, imports)
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test (coverage below floor → N/A)**

Append to `tests/monitor/test_valuation.py`. This seeds a pure active fund holding only 30% of one priced name (below the 0.50 NAV coverage floor) → `fund_valuation_percentile` returns a `None` PE percentile → N/A.

```python
# ── Item 002: look-through branch ─────────────────────────────────────────────

from datetime import date as _date


def _seed_active_fund_holdings(con, fund_id, ticker, weight_pct, report_date="2026-03-31"):
    con.execute(
        "INSERT INTO fund_holdings VALUES (?, ?, ?, ?, ?, "
        "TIMESTAMP '2026-05-15', 'test', 'fh:r')",
        [fund_id, report_date, ticker, "x", weight_pct],
    )


def _seed_stock_valuation(con, stock_code, n=200, pe0=18.0, pe_step=0.01, pb=2.0):
    # n PE/PB points every 2 days → >120 pts spanning >180d → clears the PE maturity gate.
    base = _date(2025, 1, 1)
    rows = [
        (stock_code, _date.fromordinal(base.toordinal() + 2 * i),
         pe0 + i * pe_step, pb, None, "2026-05-15 00:00:00", "eastmoney", "sv:r")
        for i in range(n)
    ]
    con.executemany(
        "INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows
    )


def test_lookthrough_coverage_below_floor_is_na(tmp_path):
    # Pure active fund (tracked_index None) holding only 30% of one priced name →
    # NAV coverage 0.30 < 0.50 floor → fund_valuation_percentile PE pct is None → N/A.
    con = duckdb.connect(str(tmp_path / "lt1.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519069", None)
    _seed_active_fund_holdings(con, "519069", "600519", 30.0)
    _seed_stock_valuation(con, "600519")
    res = resolve_valuation_state(_fund("519069", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_coverage_below_floor_is_na -v`
Expected: PASS already? **No** — the current stub returns N/A unconditionally, so this test PASSES against the stub. That is acceptable for this first task (it locks the miss-path contract), but to drive the implementation TDD-style, this test is the *guard* and Task 2's sufficient-coverage test is the *driver*. Run it now and confirm PASS (green guard); the real red→green happens in Task 2.

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_coverage_below_floor_is_na -v`
Expected: PASS (stub returns N/A; this test pins that thin coverage stays N/A after Task 2's change).

- [ ] **Step 3: Commit the guard test**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through coverage-below-floor stays N/A"
```

---

### Task 2: Sufficient coverage → real look-through state (drives the implementation)

**Files:**
- Modify: `src/irc/monitor/valuation.py` (`_resolve_lookthrough`, imports)
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test (sufficient coverage → very_expensive)**

Append to `tests/monitor/test_valuation.py`. A pure active fund holding 60% of one priced name (clears the 0.50 floor) whose PE series rises monotonically (latest = max → self-history percentile 1.0 → `≥0.90` band → `very_expensive`).

```python
def test_lookthrough_sufficient_coverage_returns_state(tmp_path):
    # 60% in one priced name clears the 0.50 NAV floor; 200 rising PE points clear
    # the 120/180 maturity gate; latest PE is the max → percentile 1.0 → very_expensive.
    con = duckdb.connect(str(tmp_path / "lt2.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519069", None)
    _seed_active_fund_holdings(con, "519069", "600519", 60.0)
    _seed_stock_valuation(con, "600519")  # rising PE → latest is max → pct 1.0
    res = resolve_valuation_state(_fund("519069", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.cached is True
    assert res.state == "very_expensive"   # pct 1.0 → >=0.90 band
    assert res.reason is None
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_sufficient_coverage_returns_state -v`
Expected: FAIL — the stub returns `ValuationResolution(None, False, "valuation_no_anchor")`, so `res.cached is True` and `res.state == "very_expensive"` both fail.

- [ ] **Step 3: Implement `_resolve_lookthrough` (reuse the opportunity readers)**

In `src/irc/monitor/valuation.py`, add the reuse imports next to the existing `from irc.opportunity...` imports (top of file, after line 23):

```python
from irc.opportunity.inputs_loader import (
    _index_valuation_metrics,
    _latest_quarter_holdings,
    _stock_series_by_code,
)
from irc.opportunity.lookthrough_valuation import fund_valuation_percentile
from irc.opportunity.states import _band  # (unchanged item-001 import)
```

> Replace item 001's existing `from irc.opportunity.inputs_loader import _index_valuation_metrics` line with the grouped import above (3 names). Keep `from irc.opportunity.states import _band` as-is.

Add a module constant near `_NA_NO_ANCHOR` (top, after line 27) — the look-through coverage parameters, mirroring `ActiveFundLookthroughConfig` defaults so the monitor and opportunity agree:

```python
# Look-through coverage params — mirror ActiveFundLookthroughConfig defaults
# (schemas/valuation.py) so monitor and opportunity gate identically.
_LOOKTHROUGH_COVERAGE_FLOOR = 0.50
_LOOKTHROUGH_PB_USES_PE_GATE = False
```

Replace the stub body of `_resolve_lookthrough` (currently `return ValuationResolution(None, False, _NA_NO_ANCHOR)`) with:

```python
def _resolve_lookthrough(
    con: duckdb.DuckDBPyConnection, fund_id: str, root: Path
) -> ValuationResolution:
    """Look-through branch (tracked_index is None, pure active funds).

    Reuses the opportunity layer's PURE cached-DuckDB readers + percentile
    derivation (ADR 0017: pure functions on monitor-loaded cached tables; NO
    opportunity output-file reads, NO pipeline dependency). The coverage gate is
    enforced INSIDE fund_valuation_percentile (None PE pct when covered NAV ratio
    < floor or PE history immature) → None maps to honest N/A. `root` is unused
    here (cache lives in `con`); kept for signature stability.
    """
    holdings = _latest_quarter_holdings(con, fund_id)
    if not holdings:
        return ValuationResolution(None, False, _NA_NO_ANCHOR)
    series = _stock_series_by_code(con, tuple(h.code for h in holdings))
    result = fund_valuation_percentile(
        holdings, series,
        coverage_floor=_LOOKTHROUGH_COVERAGE_FLOOR,
        pb_uses_pe_gate=_LOOKTHROUGH_PB_USES_PE_GATE,
    )
    state = percentile_to_valuation_state(result.pe.percentile)
    if state is None:
        return ValuationResolution(None, False, _NA_NO_ANCHOR)
    return ValuationResolution(state, True, None)
```

- [ ] **Step 4: Run the two look-through tests to verify they pass**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_sufficient_coverage_returns_state tests/monitor/test_valuation.py::test_lookthrough_coverage_below_floor_is_na -v`
Expected: BOTH PASS — sufficient coverage → `very_expensive`/`cached=True`; thin coverage → N/A.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/valuation.py tests/monitor/test_valuation.py
git commit -m "feat(002): look-through valuation via opportunity pure derivation"
```

---

### Task 3: Band-boundary mapping for a real look-through percentile

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test (cheap band at a low percentile)**

Append. A 60% holding whose PE series is FLAT until the last point, which is the minimum → self-history percentile ≈ 0.0 → `<0.20` → `cheap`. (Uses a falling series so the latest point is the smallest.)

```python
def test_lookthrough_low_percentile_is_cheap(tmp_path):
    # Falling PE → latest point is the MIN → self-history percentile ~0.0 → cheap.
    con = duckdb.connect(str(tmp_path / "lt3.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "260112", None)
    _seed_active_fund_holdings(con, "260112", "600519", 60.0)
    _seed_stock_valuation(con, "600519", pe0=40.0, pe_step=-0.1)  # descending PE
    res = resolve_valuation_state(_fund("260112", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.cached is True
    assert res.state == "cheap"   # pct ~0.0 → <0.20 band
    assert res.reason is None
    con.close()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_low_percentile_is_cheap -v`
Expected: PASS (implementation from Task 2 already maps the percentile through `percentile_to_valuation_state`). This test locks the band-boundary behavior end-to-end through the look-through path; the per-band thresholds themselves are already exhaustively covered by item 001's `test_percentile_maps_to_band`.

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through low-percentile maps to cheap band"
```

---

### Task 4: Holdings present but NO cached stock valuations → N/A (honest coverage miss)

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test (holdings, zero priced names → N/A)**

Append. Seeds holdings but NO `stock_valuation_history` rows → `_stock_series_by_code` returns `{}` → covered set empty → coverage ratio 0.0 < floor → `None` pct → N/A. This is the primary spec §10 risk (thin/absent stock-valuation coverage → surfaced N/A, not an error).

```python
def test_lookthrough_holdings_but_no_stock_valuations_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt4.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "006533", None)
    _seed_active_fund_holdings(con, "006533", "600519", 60.0)
    # NO stock_valuation_history rows → no priced holdings → coverage 0.0 → N/A.
    res = resolve_valuation_state(_fund("006533", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_holdings_but_no_stock_valuations_is_na -v`
Expected: PASS (empty series → below-floor → `None` pct → N/A path).

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through with no cached stock valuations is N/A"
```

---

### Task 5: No holdings at all → N/A (cold cache); dispatch + item-001 regression

**Files:**
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test (no fund_holdings rows → N/A)**

Append. A pure active fund with zero `fund_holdings` rows → `_latest_quarter_holdings` returns `()` → early N/A. Also re-pins that the index path is untouched by the look-through change.

```python
def test_lookthrough_no_holdings_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt5.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "000083", None)  # no fund_holdings rows
    res = resolve_valuation_state(_fund("000083", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None and res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_index_path_unchanged_by_lookthrough(tmp_path):
    # Regression: a fund WITH tracked_index still takes the index path even when
    # fund_holdings rows exist — _resolve dispatches on tracked_index, not holdings.
    con = duckdb.connect(str(tmp_path / "lt6.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    _seed_active_fund_holdings(con, "510300", "600519", 60.0)
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

Run: `uv run pytest tests/monitor/test_valuation.py::test_lookthrough_no_holdings_is_na tests/monitor/test_valuation.py::test_index_path_unchanged_by_lookthrough -v`
Expected: BOTH PASS — cold cache → N/A; index dispatch unchanged.

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_valuation.py
git commit -m "test(002): look-through cold-cache N/A + index dispatch regression"
```

---

### Task 6: Full-file + lint verification (preserve all item-001 behavior)

**Files:** none (verification only)

- [ ] **Step 1: Run the full valuation test module**

Run: `uv run pytest tests/monitor/test_valuation.py -v`
Expected: ALL PASS — item 001's tests (percentile band table, index-anchored present/immature, china_internet gap, unactivated sector, lookthrough-stub *renamed/replaced* note below, unknown-fund, missing-table degrade-to-N/A) PLUS the 6 new look-through tests.

> **Item-001 stub test handling:** item 001 has `test_lookthrough_branch_is_na_stub` (asserts the pure active fund returns N/A). After this change, that fund (`519069` with NO holdings seeded) STILL returns N/A — `_latest_quarter_holdings` returns `()` → early N/A — so the test continues to PASS unchanged. **Do not delete or edit it.** It now documents "look-through with cold cache → N/A," which remains true. If you wish, you MAY rename it in a follow-up, but that is out of scope; leave it untouched to prove zero item-001 regression.

- [ ] **Step 2: Run the opportunity look-through tests (prove reuse target is unbroken)**

Run: `uv run pytest tests/opportunity/test_inputs_loader_lookthrough.py tests/opportunity/test_lookthrough_valuation.py -q`
Expected: ALL PASS — we only IMPORT the opportunity readers; we do not modify them, so these stay green.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/irc/monitor/valuation.py tests/monitor/test_valuation.py`
Expected: no errors. (If ruff flags the unused `root` param, it will NOT — it's a named positional, not an unused local; the `# root is unused here` docstring note documents intent. If ruff flags the leading-underscore imports as private-name usage, they are pre-existing project pattern — item 001 already imports `_index_valuation_metrics`/`_band` the same way.)

- [ ] **Step 4: Confirm file-size budget**

Run: `wc -l src/irc/monitor/valuation.py`
Expected: < 200 lines (≈ 135 after this change). If it somehow exceeds 200, extract the look-through body into a pure `src/irc/monitor/lookthrough.py` helper `lookthrough_state(con, fund_id) -> ValuationResolution` and call it — but this is NOT expected; do not pre-emptively split.

- [ ] **Step 5: Commit (no-op safety / final)**

```bash
git add -A
git commit -m "chore(002): verify look-through valuation + item-001 regression green" --allow-empty
```

---

## Self-review (run before handoff)

**Spec coverage (002-spec.md):**
- AC1 look-through branch assembles cached inputs + reuses `fund_valuation_percentile`/`HoldingWeight`/`MetricSeries` + `percentile_to_valuation_state` + coverage-gate→`valuation_no_anchor` → Tasks 1–4.
- AC2 pure reuse, no pipeline/output-file dependency (ADR 0017) → readers operate on `con` only; documented in `_resolve_lookthrough` docstring + data-flow decision.
- AC3 6 active funds light up with sufficient coverage; thin → `valuation_no_anchor`; `009225` index path + `gold`/`qdii_global` `profile_ineligible` unchanged → Task 5 regression + item-001 tests (untouched) + eligibility is gated upstream in `factors.py` (out of this file's scope; not changed).
- §6 invariants: N/A reason stays `valuation_no_anchor` (in `KNOWN_NA_REASONS`); determinism (same cached rows → same percentile → same state) — Tasks 1–5 all assert deterministic outputs.
- §8 tests: pure dispatch + band boundaries + coverage-fail + holdings-construction-from-cached-rows → Tasks 1–5 (DuckDB fixtures, no mocks, no opportunity pipeline). Integration (full monitor run over fixture DuckDB) is exercised by the existing monitor integration suite once this branch lights; this plan covers the unit/dispatch layer the spec scopes to slice 2.
- §10 primary risk (thin coverage → surfaced N/A, never error) → Task 4 + Task 1.

**Placeholder scan:** none — every code/test block is concrete.

**Type consistency:** `ValuationResolution(state, cached, reason)`, `HoldingWeight.code/.weight_pct`, `MetricSeries.code/.source/.points`, `result.pe.percentile`, `percentile_to_valuation_state`, `_latest_quarter_holdings`, `_stock_series_by_code`, `fund_valuation_percentile` signatures all match the grounded symbols above.

**Constraints encoded:** TDD (failing test before impl in Task 2); pure-where-possible (only effect is cached `con` reads via reused thin wrappers); no new N/A reason codes (only `valuation_no_anchor`); `KNOWN_NA_REASONS` untouched; `resolve_valuation_state` still wrapped in item-001's try/except so any read error degrades to N/A (never raises); index path + `gold`/`qdii_global` unchanged; no `monitor_cmd.py` / signature change; file < 200 lines.
