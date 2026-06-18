# 001 — Index-path valuation + vocabulary unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Light up the index-anchored `valuation` factor in `irc monitor` for funds whose `tracked_index` resolves to a real index-valuation key (e.g. `csi300`), reusing the opportunity layer's pure derivation on monitor-loaded cached DuckDB data, and unify the monitor valuation vocabulary onto the opportunity layer's five states. (See the SPEC GAP note: `009225`/`china_internet` is *not* a valuation key today, so it honestly ships N/A — the wiring + map are proven via a real anchor.)

**Architecture:** A new pure module `src/irc/monitor/valuation.py` resolves a fund's valuation state. It reads `tracked_index` from the cached `instruments` table (same source as the opportunity layer's `instr.tracked_index`), dispatches by it: the index branch calls the opportunity layer's pure `_index_valuation_metrics(con, tracked_index)` → `pe_percentile`, then maps the percentile to a band via the opportunity layer's shared `_VALUATION_BANDS`/`_band` (DRY — no re-defined numbers); the look-through branch is an honest N/A stub that item 002 fills in. The command edge (`monitor_cmd.py`) opens the cached DuckDB connection once per run and threads it into `_process_fund`, replacing the two hardcoded `None`s. No new network calls (cache-read only). ADR 0017 evidence isolation is preserved: we call opportunity *pure functions* on monitor-loaded cached tables — never read opportunity output files, never depend on the opportunity pipeline having run.

**Tech Stack:** Python 3.12, frozen dataclasses, DuckDB (cached read at the edge only), pytest, hypothesis (existing oracle tests), ruff.

---

## Grounding (verified by grep — do NOT trust the spec's line numbers blindly; re-confirm if drift)

- **`_index_valuation_metrics`** — `src/irc/opportunity/inputs_loader.py:155`
  Signature: `_index_valuation_metrics(con: duckdb.DuckDBPyConnection, tracked_index: str | None, *, activated_sector_slugs: frozenset[str] = frozenset()) -> tuple[float|None, float|None, float|None, float|None, float|None]`
  Returns `(pe_ttm, pb, dividend_yield, pe_percentile, pb_percentile)`. We use element **[3]** (`pe_percentile`, a 0..1 percentile or `None`). The function internally normalises the `tracked_index` display name to a slug via `_INDEX_NAME_TO_SLUG`, gates on `_INDEX_VALUATION_KEYS` membership, short-circuits an un-activated sector slug to all-`None`, and applies the PE-maturity gate — so a miss / immature history / un-activated sector → `pe_percentile is None`. **We do not re-implement any of this.**
- **Shared band constants** — `src/irc/opportunity/states.py:160`
  `_VALUATION_BANDS: tuple[tuple[float, str], ...] = ((0.20, "cheap"), (0.40, "reasonable_low"), (0.70, "fair"), (0.90, "expensive"))`
  and `def _band(pct: float) -> str` (`states.py:168`) which returns the tier, defaulting to `"very_expensive"` for `pct >= 0.90`. `_band` takes a **non-None** float and never returns `None`. We reuse `_band` (DRY) and wrap it with a `None`/NaN guard.
- **`tracked_index` source** — the `instruments` DuckDB table has a `tracked_index VARCHAR` column (`src/irc/data/duckdb_helper.py:39`). The opportunity layer reads it via `instr.tracked_index` (`inputs_build.py:31`). The monitor config (`config/monitor.yaml`) does **not** carry `tracked_index`, so we read it from `instruments` keyed by `fund.id` — same source of truth.
- **DuckDB connection** — `connect(db_path)` from `src/irc/data/duckdb_helper.py:117`; the opportunity command opens `connect(root / "data" / "local.duckdb")` (`opportunity_cmd.py:1521`). The monitor currently opens no DuckDB connection (grep of `src/irc/monitor/` for `duckdb`/`connect` is empty), so the edge wiring adds the first one.
- **`_VALUATION_MAP`** — `src/irc/monitor/factor_maps.py:3` currently `{"cheap":1.0,"fair_cheap":0.5,"fair":0.0,"fair_expensive":-0.5,"expensive":-1.0}`. We replace with the unified 5-state vocab.
- **N/A reasons** — `KNOWN_NA_REASONS` in `src/irc/monitor/factors.py:21`. `valuation_no_anchor` and `valuation_unknown_state` are already members. **We add no new reason codes.** The `_valuation` gate (`factors.py:57`) already produces `valuation_no_anchor` when `not valuation_cached or valuation_state is None`, and `valuation_unknown_state` when `valuation_state_score` returns `None`. `gold`/`qdii_global` valuation stays `profile_ineligible` because `_valuation` first checks `"valuation" not in eligible_factors(profile)` — **our change touches neither `eligible_factors` nor that gate**, so this invariant is structurally preserved.
- **Test conventions** — monitor tests live under `tests/monitor/` (NOT `tests/irc/monitor/`). DuckDB-fixture pattern is in `tests/opportunity/test_inputs_loader.py`: `con = duckdb.connect(str(tmp_path / "x.duckdb")); ensure_schema(con)`, then `con.executemany("INSERT INTO index_valuation_history VALUES (?,?,?,?,?, TIMESTAMP '2026-05-15','test','test:iv')", rows)`. **Provenance columns (`_ingested_at TIMESTAMP`, `_source VARCHAR`, `_raw_ref VARCHAR`) are NOT NULL on every table** (verified — a partial-column `instruments` INSERT that omits them raises a NOT NULL constraint error), so the `instruments` seed helper MUST name those three columns and supply literals.

> **SPEC GAP — verified empirically, judgment call (spec §3 table / §9 slice 1 / AC 5).** The spec says `009225` (profile `qdii_china_us_internet`, tracked index "China Internet" / `中概互联` → slug `china_internet`) "shows a real valuation factor when cache present". **It does not.** `china_internet` is **not** a member of `opportunity/lookthrough._INDEX_VALUATION_KEYS` (it's a QDII-US display name, not a recognised *index-valuation* key), so `_index_valuation_metrics(con, "china_internet")[3]` returns `None` → the index branch correctly ships `valuation_no_anchor` for `009225`. The wiring is still proven end-to-end, just with a **working** anchor: `csi300` (a real `_INDEX_VALUATION_KEYS` member) yields `pe_pct=1.0 → very_expensive`. The integration tests therefore use `csi300` for the "present state" case and treat `009225`/`china_internet` as a documented N/A. `018132`'s sector slug `csi_nonferrous_mining` lights only when its slug is on the `activated_sector_slugs` allowlist (un-activated → N/A, per spec §3). Lighting an actual `009225`/`018132` valuation is a follow-up (add `china_internet` to the index-valuation key set / thread the sector allowlist into `resolve_valuation_state`) — out of scope for slice 1, which proves the *wiring + map*. Empirical confirmation: `_index_valuation_metrics(con, "csi300")[3] == 1.0`; `_index_valuation_metrics(con, "china_internet")[3] is None`; `_index_valuation_metrics(con, "中证有色金属矿业主题", activated_sector_slugs=frozenset({"csi_nonferrous_mining"}))[3] == 1.0` while the un-activated call returns `None`.

## File Structure

- **Create** `src/irc/monitor/valuation.py` (pure resolution + the percentile→state helper + frozen result type; < 60 lines). The only effect is the cached DuckDB reads, confined to thin query wrappers in this module; the dispatch/mapping logic is pure.
- **Create** `tests/monitor/test_valuation.py` (mirror of the new source).
- **Modify** `src/irc/monitor/factor_maps.py` (`_VALUATION_MAP` → unified 5-state vocab).
- **Modify** `tests/monitor/test_factor_maps.py`, `tests/monitor/test_factor_maps_oracle.py`, `tests/monitor/_oracle.py` (update the vocab in the existing valuation oracle + parametrize tables so the suite stays green).
- **Modify** `src/irc/commands/monitor_cmd.py` (open `con` once in `run_monitor`, thread into `_process_fund`, call `resolve_valuation_state`, feed `valuation_state`/`valuation_cached`).

---

## Task 1: Unify `_VALUATION_MAP` onto the opportunity 5-state vocabulary

**Files:**
- Modify: `src/irc/monitor/factor_maps.py:3-6`
- Test: `tests/monitor/test_factor_maps.py`, `tests/monitor/test_factor_maps_oracle.py`, `tests/monitor/_oracle.py`

- [ ] **Step 1: Update the failing test table in `tests/monitor/test_factor_maps.py`**

Replace the parametrize block (lines 5-10) so it asserts the NEW vocabulary:

```python
@pytest.mark.parametrize("state,expected", [
    ("cheap", 1.0), ("reasonable_low", 0.5), ("fair", 0.0),
    ("expensive", -0.5), ("very_expensive", -1.0),
])
def test_valuation_map(state, expected):
    assert valuation_state_score(state) == expected
```

(Leave `test_valuation_unknown_state_is_none` and the heat tests in that file unchanged.)

- [ ] **Step 2: Run the test to verify it fails (red)**

Run: `uv run pytest tests/monitor/test_factor_maps.py::test_valuation_map -v`
Expected: FAIL — `valuation_state_score("reasonable_low")` returns `None` (state not yet in the map).

- [ ] **Step 3: Edit `_VALUATION_MAP` to the unified vocabulary**

In `src/irc/monitor/factor_maps.py`, replace lines 3-6:

```python
_VALUATION_MAP: dict[str, float] = {
    "cheap": 1.0, "reasonable_low": 0.5, "fair": 0.0,
    "expensive": -0.5, "very_expensive": -1.0,
}
```

(Do NOT touch `_RAPID_INFLOW_PCT`, `valuation_state_score`, or `heat_score` — `valuation_state_score` already returns `None` for any unrecognised state via `.get`, which is the `valuation_unknown_state` contract.)

- [ ] **Step 4: Run the test to verify it passes (green)**

Run: `uv run pytest tests/monitor/test_factor_maps.py::test_valuation_map -v`
Expected: PASS.

- [ ] **Step 5: Update the test-only oracle `tests/monitor/_oracle.py` to the new vocab**

In `valuation_oracle` (the if-ladder near line 69), replace the two renamed states:

```python
def valuation_oracle(state: str):
    """Re-expressed as an explicit if-ladder instead of a dict lookup."""
    if state == "cheap":
        return 1.0
    if state == "reasonable_low":
        return 0.5
    if state == "fair":
        return 0.0
    if state == "expensive":
        return -0.5
    if state == "very_expensive":
        return -1.0
    return None
```

- [ ] **Step 6: Update the oracle-driven test states in `tests/monitor/test_factor_maps_oracle.py`**

Replace `_KNOWN_STATES` (line 11):

```python
_KNOWN_STATES = ("cheap", "reasonable_low", "fair", "expensive", "very_expensive")
```

(The body of `test_valuation_ordering_cheaper_is_higher`, `test_valuation_matches_oracle`, and `test_valuation_none_on_unrecognised` already reference `_KNOWN_STATES` and the oracle, so they need no further edits. `test_valuation_ordering_cheaper_is_higher` still asserts `scores[0] == 1.0 and scores[-1] == -1.0` and strictly-descending order — true for the new 5-state vocab.)

- [ ] **Step 7: Run the full factor-maps test set to verify all green**

Run: `uv run pytest tests/monitor/test_factor_maps.py tests/monitor/test_factor_maps_oracle.py -v`
Expected: PASS (every parametrize case + both oracle properties).

- [ ] **Step 8: Commit**

```bash
git add src/irc/monitor/factor_maps.py tests/monitor/test_factor_maps.py \
        tests/monitor/test_factor_maps_oracle.py tests/monitor/_oracle.py
git commit -m "feat(monitor): unify _VALUATION_MAP onto opportunity 5-state vocab"
```

---

## Task 2: Pure `percentile_to_valuation_state` helper (DRY band reuse)

**Files:**
- Create: `src/irc/monitor/valuation.py`
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing test for the band boundaries + None/NaN guard**

Create `tests/monitor/test_valuation.py` with:

```python
from __future__ import annotations

import math

import pytest

from irc.monitor.valuation import percentile_to_valuation_state


@pytest.mark.parametrize("pct,expected", [
    (0.0, "cheap"),
    (0.19, "cheap"),
    (0.20, "reasonable_low"),   # boundary: < 0.20 is cheap; 0.20 rolls to next band
    (0.39, "reasonable_low"),
    (0.40, "fair"),
    (0.69, "fair"),
    (0.70, "expensive"),
    (0.89, "expensive"),
    (0.90, "very_expensive"),
    (1.0, "very_expensive"),
])
def test_percentile_maps_to_band(pct, expected):
    assert percentile_to_valuation_state(pct) == expected


def test_none_percentile_is_none():
    assert percentile_to_valuation_state(None) is None


def test_nan_percentile_is_none():
    assert percentile_to_valuation_state(float("nan")) is None
```

- [ ] **Step 2: Run the test to verify it fails (red)**

Run: `uv run pytest tests/monitor/test_valuation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.valuation'`.

- [ ] **Step 3: Create `src/irc/monitor/valuation.py` with the pure helper only**

```python
"""PURE valuation resolution for `irc monitor` (reuses the opportunity engine).

Reuse boundary (ADR 0017 monitor evidence isolation): this module calls the
opportunity layer's *pure functions* (`_index_valuation_metrics`, the shared
`_VALUATION_BANDS`/`_band`) on monitor-loaded CACHED DuckDB tables. It does NOT
depend on the opportunity *pipeline* having run, and NEVER reads opportunity
*output files*. The only effect here is cached DuckDB reads, confined to the
thin query wrapper `_tracked_index_for_fund`; the dispatch + mapping is pure.

Slice 1 (item 001) wires the INDEX-anchored branch. The look-through branch is
an honest N/A stub filled in by item 002 (see `_resolve_lookthrough`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from irc.opportunity.states import _band

_NA_NO_ANCHOR = "valuation_no_anchor"


def percentile_to_valuation_state(pct: float | None) -> str | None:
    """Map a 0..1 valuation percentile to a unified-vocab state, or None.

    DRY: the band thresholds live in opportunity/states._VALUATION_BANDS and are
    applied by `_band`; we only add the None/NaN guard. None/NaN → None (→ N/A).
    """
    if pct is None or math.isnan(pct):
        return None
    return _band(float(pct))
```

- [ ] **Step 4: Run the test to verify it passes (green)**

Run: `uv run pytest tests/monitor/test_valuation.py -v`
Expected: PASS (all 13 cases).

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/irc/monitor/valuation.py tests/monitor/test_valuation.py`
Expected: no errors. (`_band` is a private import from a sibling package, intentional per the DRY reuse boundary documented in the module docstring; if ruff flags the leading-underscore import, it does not by default — leave as-is.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/valuation.py tests/monitor/test_valuation.py
git commit -m "feat(monitor): pure percentile_to_valuation_state reusing opportunity bands"
```

---

## Task 3: `ValuationResolution` result type + `resolve_valuation_state` dispatch (index branch live, look-through stub)

**Files:**
- Modify: `src/irc/monitor/valuation.py`
- Test: `tests/monitor/test_valuation.py`

- [ ] **Step 1: Write the failing tests for the result type + dispatch**

Append to `tests/monitor/test_valuation.py`:

```python
import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.monitor.types import MonitorFund
from irc.monitor.valuation import ValuationResolution, resolve_valuation_state


def _fund(fund_id: str, profile: str = "active_cn_equity") -> MonitorFund:
    return MonitorFund(
        id=fund_id, name_cn="x", market="cn_off_exchange",
        analysis_profile=profile, themes=(), constituent_news=False,
        weights={}, bands={}, minimum_confidence=0.5,
    )


def _seed_instrument(con, fund_id, tracked_index):
    # NOTE: provenance cols (_ingested_at/_source/_raw_ref) are NOT NULL → name them.
    con.execute(
        "INSERT INTO instruments (instrument_id, ticker, market, name_cn, "
        "asset_class, currency, tracked_index, _ingested_at, _source, _raw_ref) "
        "VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:i')",
        [fund_id, fund_id, "cn_off_exchange", "x", "cn_etf", "cny", tracked_index],
    )


def _seed_index_valuation_history(con, index_key, pe_pb_pairs):
    from datetime import date
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(date(2025, 1, 1).toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_result_type_is_frozen():
    r = ValuationResolution(state="cheap", cached=True, reason=None)
    with pytest.raises(Exception):
        r.state = "fair"  # frozen dataclass → FrozenInstanceError


def test_index_anchored_present_state(tmp_path):
    # Use csi300 — a REAL _INDEX_VALUATION_KEYS member (china_internet is NOT one;
    # see the SPEC GAP note in the plan header). 200 rising PE points: >120
    # MIN_PE_POINTS, span >180d → mature; latest is max → pct 1.0 → very_expensive.
    con = duckdb.connect(str(tmp_path / "iv.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi300", pairs)
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.cached is True
    assert res.state == "very_expensive"   # pct 1.0 → >=0.90 band
    assert res.reason is None
    con.close()


def test_index_anchored_immature_history_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv2.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    _seed_index_valuation_history(con, "csi300", [(12.0, 1.3)] * 10)  # <120 pts → immature
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_china_internet_anchor_is_na_documented_gap(tmp_path):
    # 009225's tracked index china_internet is NOT a valuation key → N/A even with
    # cache. Locks the documented spec gap (plan header) so a future fix is intentional.
    con = duckdb.connect(str(tmp_path / "iv3.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "009225", "china_internet")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "china_internet", pairs)
    res = resolve_valuation_state(_fund("009225", "qdii_china_us_internet"),
                                  con=con, root=tmp_path)
    assert res.state is None and res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_index_anchored_unactivated_sector_is_na(tmp_path):
    # 018132 → display 中证有色金属矿业主题 → slug csi_nonferrous_mining (a SECTOR key).
    # resolve_valuation_state does NOT pass activated_sector_slugs, so the sector
    # short-circuits to all-None → N/A. (Spec §3: acceptable, surfaced.)
    con = duckdb.connect(str(tmp_path / "iv4.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "018132", "中证有色金属矿业主题")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi_nonferrous_mining", pairs)
    res = resolve_valuation_state(_fund("018132", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_lookthrough_branch_is_na_stub(tmp_path):
    # tracked_index is None (pure active fund) → honest N/A placeholder (item 002 fills in).
    con = duckdb.connect(str(tmp_path / "iv5.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519069", None)
    res = resolve_valuation_state(_fund("519069", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_unknown_fund_no_instrument_row_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv5.duckdb"))
    ensure_schema(con)
    res = resolve_valuation_state(_fund("999999", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None and res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()
```

- [ ] **Step 2: Run the tests to verify they fail (red)**

Run: `uv run pytest tests/monitor/test_valuation.py -v -k "result_type or index_anchored or lookthrough or unknown_fund"`
Expected: FAIL — `ImportError: cannot import name 'ValuationResolution'` / `resolve_valuation_state`.

- [ ] **Step 3: Add the result type, the `tracked_index` read, the dispatch, and the look-through stub to `src/irc/monitor/valuation.py`**

Add the imports at the top (alongside the existing ones):

```python
from pathlib import Path

import duckdb

from irc.opportunity.inputs_loader import _index_valuation_metrics
```

Add the frozen result type below `_NA_NO_ANCHOR`:

```python
@dataclass(frozen=True)
class ValuationResolution:
    """Frozen result of resolving one fund's monitor valuation state.

    state: unified-vocab valuation state (factor_maps._VALUATION_MAP key) or None.
    cached: True iff a real cached percentile produced the state (drives
            FactorInputs.valuation_cached → the _valuation eligibility gate).
    reason: N/A reason code (a KNOWN_NA_REASONS member) when state is None, else None.
    """
    state: str | None
    cached: bool
    reason: str | None
```

Add the cached-read wrapper, the dispatch entry point, and the two branch helpers:

```python
def _tracked_index_for_fund(con: duckdb.DuckDBPyConnection, fund_id: str) -> str | None:
    """EDGE (cached read): the fund's tracked_index from the instruments table —
    the SAME source the opportunity layer uses (inputs_build.py: instr.tracked_index),
    so monitor and opportunity agree. Absent row / null → None (→ look-through)."""
    df = con.execute(
        "SELECT tracked_index FROM instruments WHERE instrument_id = ?",
        [fund_id],
    ).fetchdf()
    if df.empty:
        return None
    value = df.iloc[0]["tracked_index"]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _resolve_index(con: duckdb.DuckDBPyConnection, tracked_index: str) -> ValuationResolution:
    """Index-anchored branch: reuse the opportunity pure derivation on cached data.
    _index_valuation_metrics returns (pe, pb, div, pe_pct, pb_pct); we map pe_pct."""
    _, _, _, pe_pct, _ = _index_valuation_metrics(con, tracked_index)
    state = percentile_to_valuation_state(pe_pct)
    if state is None:
        return ValuationResolution(None, False, _NA_NO_ANCHOR)
    return ValuationResolution(state, True, None)


def _resolve_lookthrough(
    con: duckdb.DuckDBPyConnection, fund_id: str, root: Path
) -> ValuationResolution:
    """Look-through branch (tracked_index is None, pure active funds).

    STUB — item 002 fills this in: assemble the cached look-through inputs from
    the monitor's already-loaded active-fund snapshot holdings + cached stock
    valuations, call opportunity/lookthrough_valuation.fund_valuation_percentile,
    then percentile_to_valuation_state. Until then, honest N/A (never fabricate).
    Contract item 002 must preserve: return ValuationResolution(state, cached,
    reason) where cached is True ONLY on a real percentile, reason is a
    KNOWN_NA_REASONS member (valuation_no_anchor) on a miss, and the (con, fund_id,
    root) inputs are sufficient (no opportunity output-file reads — ADR 0017)."""
    return ValuationResolution(None, False, _NA_NO_ANCHOR)


def resolve_valuation_state(
    fund, *, con: duckdb.DuckDBPyConnection, root: Path
) -> ValuationResolution:
    """PURE-ish dispatch (cached reads only): index path when the fund has a
    tracked_index, else the look-through stub. Never raises on a data miss —
    degrades to an honest N/A so the brief never crashes."""
    tracked_index = _tracked_index_for_fund(con, fund.id)
    if tracked_index is not None:
        return _resolve_index(con, tracked_index)
    return _resolve_lookthrough(con, fund.id, root)
```

- [ ] **Step 4: Run the tests to verify they pass (green)**

Run: `uv run pytest tests/monitor/test_valuation.py -v`
Expected: PASS (the percentile cases from Task 2 + all dispatch cases).

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/irc/monitor/valuation.py tests/monitor/test_valuation.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/valuation.py tests/monitor/test_valuation.py
git commit -m "feat(monitor): resolve_valuation_state index branch + lookthrough N/A stub"
```

---

## Task 4: Wire `resolve_valuation_state` into the monitor command edge

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (imports; `_process_fund` signature + body ~543-587; `run_monitor` ~604-618 to open + thread `con`)
- Test: `tests/monitor/test_valuation_wiring.py` (new)

- [ ] **Step 1: Write the failing wiring test**

Create `tests/monitor/test_valuation_wiring.py`. This tests the SEAM directly (not a full `irc monitor` run): that `_process_fund` consumes a `con` and feeds a real `valuation_state`/`valuation_cached` into the FactorScores for an index-anchored fund, and that gold/qdii_global stay `profile_ineligible`.

```python
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.commands import monitor_cmd
from irc.data.duckdb_helper import ensure_schema
from irc.monitor.types import MonitorFund


def _fund(fund_id, profile):
    return MonitorFund(
        id=fund_id, name_cn="x", market="cn_off_exchange",
        analysis_profile=profile, themes=(), constituent_news=False,
        weights={}, bands={}, minimum_confidence=0.5,
    )


def _seed_instrument(con, fund_id, tracked_index):
    # provenance cols are NOT NULL → name + supply them.
    con.execute(
        "INSERT INTO instruments (instrument_id, ticker, market, name_cn, "
        "asset_class, currency, tracked_index, _ingested_at, _source, _raw_ref) "
        "VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:i')",
        [fund_id, fund_id, "cn_off_exchange", "x", "cn_etf", "cny", tracked_index],
    )


def _seed_iv(con, index_key, pairs):
    rows = []
    for i, (pe, pb) in enumerate(pairs):
        d = date.fromordinal(date(2025, 1, 1).toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_index_fund_gets_real_valuation_state(tmp_path):
    # Use csi300 — a working index anchor (china_internet is NOT a valuation key;
    # see the SPEC GAP note in the plan header). Profile active_cn_equity makes
    # valuation eligible, so the mapped state surfaces as an eligible FactorScore.
    con = duckdb.connect(str(tmp_path / "local.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    _seed_iv(con, "csi300", [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)])

    from irc.monitor.valuation import resolve_valuation_state
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state == "very_expensive" and res.cached is True
    # The state is consumed by _valuation → an eligible FactorScore (vocab maps it).
    from irc.monitor.factors import FactorInputs, build_factor_scores
    inp = FactorInputs(
        acc_nav=(), minimum_observations=251,
        valuation_state=res.state, valuation_cached=res.cached,
        restricted=None, aum_delta_pct=None, macro_rows=(), constituent_rows=(),
    )
    scores = {s.name: s for s in build_factor_scores("active_cn_equity", inp)}
    assert scores["valuation"].eligible is True
    assert scores["valuation"].value == -1.0   # very_expensive → _VALUATION_MAP -1.0
    con.close()


def test_gold_and_qdii_global_valuation_stay_profile_ineligible(tmp_path):
    con = duckdb.connect(str(tmp_path / "local.duckdb"))
    ensure_schema(con)
    from irc.monitor.valuation import resolve_valuation_state
    from irc.monitor.factors import FactorInputs, build_factor_scores
    for profile in ("gold", "qdii_global"):
        res = resolve_valuation_state(_fund("0", profile), con=con, root=tmp_path)
        inp = FactorInputs(
            acc_nav=(), minimum_observations=251,
            valuation_state=res.state, valuation_cached=res.cached,
            restricted=None, aum_delta_pct=None, macro_rows=(), constituent_rows=(),
        )
        scores = {s.name: s for s in build_factor_scores(profile, inp)}
        assert scores["valuation"].eligible is False
        assert scores["valuation"].reason == "profile_ineligible"
    con.close()
```

- [ ] **Step 2: Run the test to verify the first case fails (red)**

Run: `uv run pytest tests/monitor/test_valuation_wiring.py -v`
Expected: PASS already? No — `test_gold_and_qdii_global...` passes (eligibility gate is structural), but `test_index_fund_gets_real_valuation_state` exercises `resolve_valuation_state` which already exists from Task 3, so BOTH may pass. That is acceptable: these are regression locks proving the seam is correct **before** we touch `monitor_cmd.py`. If both pass, proceed to wire the edge (the edge change is covered by Step 5's import/structure assertions). Record the run output.

- [ ] **Step 3: Add the DuckDB-helper import to `monitor_cmd.py`**

After the existing `from irc.config_loader import ...` import (line 15), add:

```python
from irc.data.duckdb_helper import connect
from irc.monitor.valuation import resolve_valuation_state
```

- [ ] **Step 4: Open the cached connection once in `run_monitor` and thread it into `_process_fund`**

In `run_monitor` (`monitor_cmd.py`), after `cfg = load_monitor_config(root)` and `funds = resolve_funds(cfg)` (around line 611-612), open the connection defensively (the cached DB may be absent on a fresh checkout — degrade to N/A, never crash):

```python
    con = None
    db_path = root / "data" / "local.duckdb"
    if db_path.exists():
        try:
            con = connect(db_path)
        except Exception:  # noqa: BLE001 — degrade, never crash the brief
            _log.warning("valuation DB open failed; valuation → N/A", exc_info=True)
            con = None
```

Change the per-fund loop call (around line 618) from:

```python
        view, costs, bundle = _process_fund(fund, cfg, root, llm_config)
```

to:

```python
        view, costs, bundle = _process_fund(fund, cfg, root, llm_config, con=con)
```

After the loop finishes (before the outputs are written, i.e. right after the `for fund in funds:` block ends, around line 621), close it:

```python
    if con is not None:
        con.close()
```

- [ ] **Step 5: Thread `con` through `_process_fund` and replace the hardcoded valuation `None`s**

Change the `_process_fund` signature (line 543-545) from:

```python
def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config,
) -> tuple[FundView, list, FundTraceBundle]:
```

to:

```python
def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config, *, con=None,
) -> tuple[FundView, list, FundTraceBundle]:
```

Just before the `inp = FactorInputs(` construction (around line 578), resolve valuation (guarding the absent-`con` case):

```python
    from irc.monitor.valuation import ValuationResolution
    if con is not None:
        val = resolve_valuation_state(fund, con=con, root=root)
    else:
        val = ValuationResolution(None, False, "valuation_no_anchor")
```

Then in the `FactorInputs(...)` call, replace the two hardcoded lines:

```python
        valuation_state=None,
        valuation_cached=False,
```

with:

```python
        valuation_state=val.state,
        valuation_cached=val.cached,
```

(Leave `restricted=None, aum_delta_pct=None` unchanged — heat is slice 3.)

- [ ] **Step 6: Run the wiring test + the existing monitor factor/acceptance tests**

Run: `uv run pytest tests/monitor/test_valuation_wiring.py tests/monitor/test_valuation.py tests/monitor/test_factors.py tests/monitor/test_known_na_reasons.py -v`
Expected: PASS (no new N/A reason codes; eligibility gate unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/monitor/test_valuation_wiring.py
git commit -m "feat(monitor): wire index-path valuation into FactorInputs at the command edge"
```

---

## Task 5: Full monitor-suite regression + determinism guard

**Files:** none (verification only)

- [ ] **Step 1: Run the whole monitor unit suite**

Run: `uv run pytest tests/monitor/ -v`
Expected: PASS. Pay attention to `test_acceptance.py`, `test_render_*`, `test_signal*`, and `test_known_na_reasons.py` — they confirm the vocab change + new valuation wiring did not regress the signal, the N/A-reason set, or the renderers.

- [ ] **Step 2: Run the eval determinism + signal recompute tests**

Run: `uv run pytest tests/evals/test_monitor_signal_runner.py tests/evals/test_monitor_signal_metrics.py -v`
Expected: PASS. (All emitted reasons remain in `KNOWN_NA_REASONS`, so the `monitor_signal` recompute over `eval_trace.json` still matches and `apply_eval_gate` is unaffected — no regression to `caveated`/`gated`.)

- [ ] **Step 3: Lint the whole touched surface**

Run: `uv run ruff check src/irc/monitor/valuation.py src/irc/monitor/factor_maps.py src/irc/commands/monitor_cmd.py tests/monitor/test_valuation.py tests/monitor/test_valuation_wiring.py`
Expected: no errors.

- [ ] **Step 4: Final acceptance commit (if any incidental fixes were needed)**

```bash
git add -A
git commit -m "test(monitor): green full monitor suite after valuation slice 1" || echo "nothing to commit"
```

---

## Definition of Done (maps to spec acceptance criteria)

- [ ] `src/irc/monitor/valuation.py` exists with `ValuationResolution` (frozen `(state, cached, reason)`), `resolve_valuation_state(fund, *, con, root)` dispatching by `tracked_index`, `percentile_to_valuation_state` (DRY band reuse via `opportunity/states._band`), and an honest look-through N/A stub clearly marked for item 002. *(AC 1)*
- [ ] `tracked_index` is resolved from the cached `instruments` table — the same source the opportunity layer uses (`instr.tracked_index`). `018132`'s un-activated sector slug short-circuits to N/A inside `_index_valuation_metrics`. *(AC 2)*
- [ ] `_VALUATION_MAP` = `{"cheap":1.0,"reasonable_low":0.5,"fair":0.0,"expensive":-0.5,"very_expensive":-1.0}`; unrecognised state → `None` → `valuation_unknown_state`. *(AC 3)*
- [ ] `monitor_cmd.py` opens the cached `con` once, threads it into `_process_fund`, and feeds `valuation_state=val.state, valuation_cached=val.cached`. *(AC 4)*
- [ ] A fund whose `tracked_index` is a real index-valuation key (e.g. `csi300`) shows a real valuation factor when the cache is present; look-through active funds, cache-miss funds, the un-activated sector fund (`018132`), and the documented-gap `009225`/`china_internet` show `valuation_no_anchor`; `gold`/`qdii_global` stay `profile_ineligible`. *(AC 5 + §6 invariants; the `009225`-specific clause is the documented spec gap.)*
- [ ] No new N/A reason codes (`KNOWN_NA_REASONS` unchanged); eval recompute still PASS (§6 determinism).

---

## Self-Review notes (for the executing agent)

- **Boundary semantics.** `_band` uses strict `<` (`pct < upper`), so `0.20 → reasonable_low`, `0.40 → fair`, `0.70 → expensive`, `0.90 → very_expensive` — the test table in Task 2 encodes exactly this. Do not "fix" the boundaries; they are the opportunity layer's locked thresholds.
- **Why `cached` flips the gate.** `factors._valuation` requires BOTH `valuation_cached` truthy AND `valuation_state is not None`. The stub/miss path returns `cached=False`, which correctly yields `valuation_no_anchor` even though `state is None` would too — belt and suspenders, matching the existing gate.
- **ADR 0017.** Only cached tables (`instruments`, `index_valuation_history`) are read, via the opportunity layer's *pure* `_index_valuation_metrics`. No opportunity output files; no dependency on the opportunity pipeline having run.
- **`con` may be absent.** Fresh checkouts have no `data/local.duckdb`. The edge guards this (`db_path.exists()` + try/except) and the stub-path inside `_process_fund` returns N/A — the brief never crashes, valuation simply ships `valuation_no_anchor`.
- **Look-through contract for item 002.** `_resolve_lookthrough(con, fund_id, root)` is the single insertion point. Item 002 must keep the `ValuationResolution` contract (cached True only on a real percentile; reason a `KNOWN_NA_REASONS` member on a miss) and stay within ADR 0017 (no output-file reads).
