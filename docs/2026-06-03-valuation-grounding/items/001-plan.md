# Fundamental-Grounded Valuation (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the equity `valuation_state` for broad-index CN vehicles decided by an **index PE-TTM historical percentile** (a fundamental anchor) when available, falling back byte-for-byte to the NAV self-history percentile otherwise, and light up the dormant earnings-yield-vs-real-yield anchor with ratio-unit data.

**Architecture:** Two sub-phases inside one feature, shipping as one PR into `feat/fundamental-valuation-grounding`.
- **Phase 1a (data layer, effects at the edge):** a new AkShare-only history fetcher `fetch_cn_index_valuation_history`, a frozen `IndexValuationHistory`/`IndexValuationPoint` type pair, a new `index_valuation_history` DuckDB table, an ingest-stage writer that populates it, and the `real_yield_10y` ratio wiring off the already-ingested `cn_10y_yield`.
- **Phase 1b (classifier, pure):** new `OpportunityInput` fields, `populate_inputs` cached-read wiring (removing the live provider call), `classify_valuation` becoming fundamental-decides with a divergence reason note + PB corroboration note + lit earnings-yield anchor, a single pure `valuation_divergence_code` detector threaded into `advisory_gaps` via `build_opportunity_row`, the `ADVISORY_GAP_CODES` entry, and a discipline-report legend note.

**Tech Stack:** Python 3.12, uv, pytest, DuckDB, pandas, AkShare (legulegu endpoints `stock_index_pe_lg` / `stock_index_pb_lg`), frozen dataclasses, `dataclasses.replace` for immutable updates.

---

## Critical invariants (assert these; impl must not drift)

These are load-bearing. Each maps to a MASTER-SPEC AC or a §3.1 review finding. **Do not deviate.**

- **R1 — ratio units.** `real_yield_10y = cn_10y_yield / 100` (the percent-unit `cn_10y_yield` ≈ 2.45 becomes ≈ 0.0245). `earnings_yield = 1.0 / pe_ttm` (ratio). Both sides of `expected_real_return_positive` are ratios. **Never** reuse `real_yield_10y_tips` (US TIPS, percent). (AC5)
- **R2 — single detector + advisory routing.** Exactly one pure function `valuation_divergence_code(inp)` decides divergence. `classify_valuation` calls it for the reason note (signature stays `(state, reason)`); `build_opportunity_row` folds its output into `combined_gaps` *before* `_partition_gaps`. The code `valuation_price_fundamental_divergence` is registered in `ADVISORY_GAP_CODES` so it routes to `advisory_gaps`, never `evidence_gaps`. (AC4)
- **R3 — no live fetch in the opportunity stage.** Delete the `provider.fetch_index_valuation(...)` call inside `_index_valuation_metrics`. `populate_inputs` reads the cached `index_valuation_history` DuckDB table only. A provider stub whose `fetch_index_valuation` raises must never be invoked by the index path. (AC6)
- **R4 — provider stays 3-method.** `fetch_cn_index_valuation_history` is AkShare-only ingest infra called only by the ingest writer. Do **not** add it to the `CnFundamentalsProvider` Protocol. Provider tests are untouched. (AC7)
- **R5 — consensus veto preserved.** `compose_opportunity_state`'s `fundamental_contradiction` veto and `derive_contributing_dimensions` are **unchanged**. `valuation_state` is set only by the band input. (AC3)
- **H3 / SAME-3 untouched.** `_partition_gaps`'s H3 predicate stays `evidence_gaps == ()`. The divergence code lands in `advisory_gaps`, orthogonal to the H3 partition and the picks/evidence-pool/discipline citation-set equality. (AC4)
- **Forbidden `基金概况`.** Never appears in any fetch code. The acceptance grep test `tests/fundamentals/test_static_profile_invariant.py` must keep passing.
- **`self_history_percentile` reused verbatim.** ≥30 valid points required; `<30 → None` (clean fallback to NAV); rank-inclusive. Do not write a parallel percentile helper. (AC9)
- **`derive_position_risk_level` untouched.** `src/irc/narrative/risk.py` gets **zero edits** — risk inherits the grounded verdict for free. (AC8)
- **AC2 regression lock.** When `valuation_percentile_fundamental is None`, `classify_valuation` falls back to `_percentile(inp)` (today's behavior) byte-for-byte. The existing NAV-only suite stays green.

---

## File structure

**Phase 1a — data layer:**
- Create: `src/irc/fundamentals/index_valuation_types.py` — add `IndexValuationPoint` + `IndexValuationHistory` (alongside the existing `IndexValuation`).
- Modify: `src/irc/fundamentals/akshare_index_valuation.py` — add `fetch_cn_index_valuation_history` + a pure `_extract_series` helper. (Do NOT touch `fetch_cn_index_valuation` / `_extract_latest_value`.)
- Modify: `src/irc/data/duckdb_helper.py` — register `index_valuation_history` in `EXPECTED_TABLES` + add its DDL.
- Create: `src/irc/data/index_valuation_ingestor.py` — pure-ish ingest writer (`ingest_many`) that fetches each broad index's history and upserts rows.
- Modify: `src/irc/commands/ingest_cmd.py` — call the new ingestor inside `run_ingest`.

**Phase 1b — classifier:**
- Modify: `src/irc/opportunity/types.py` — add two `OpportunityInput` fields.
- Modify: `src/irc/opportunity/inputs_loader.py` — remove live fetch; add `_index_valuation_series` reader + `real_yield_10y` wiring; populate the new fields + `earnings_yield`.
- Modify: `src/irc/opportunity/states.py` — `_band` helper, `valuation_divergence_code`, fundamental-decides + notes in `classify_valuation`, `_divergence_gaps` + threading in `build_opportunity_row`.
- Modify: `src/irc/opportunity/advisory_gaps.py` — add `valuation_price_fundamental_divergence` to `ADVISORY_GAP_CODES`.
- Modify: `src/irc/opportunity/report.py` — add a divergence legend/advisory suffix in `_render_section`.

**Tests (mirror source one-for-one):**
- Modify: `tests/fundamentals/test_akshare_index_valuation.py`
- Create: `tests/data/test_index_valuation_ingestor.py`
- Modify: `tests/data/test_duckdb_helper.py` (if present; else create)
- Modify: `tests/opportunity/test_inputs_loader.py`
- Modify: `tests/opportunity/test_states.py`
- Modify: `tests/opportunity/test_earnings_yield_anchor.py`
- Modify: `tests/opportunity/test_report.py` (legend assertion; create if absent)

---

# PHASE 1a — DATA LAYER

## Task 1: `IndexValuationHistory` / `IndexValuationPoint` types

**Files:**
- Test: `tests/fundamentals/test_index_valuation_types.py` (create)
- Modify: `src/irc/fundamentals/index_valuation_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fundamentals/test_index_valuation_types.py`:

```python
from __future__ import annotations

import dataclasses

from irc.fundamentals.index_valuation_types import (
    IndexValuationHistory,
    IndexValuationPoint,
)


def test_point_is_frozen_with_nullable_metrics() -> None:
    pt = IndexValuationPoint(date_iso="2026-05-30", pe_ttm=12.1, pb=1.31, dividend_yield=None)
    assert pt.date_iso == "2026-05-30"
    assert pt.pe_ttm == 12.1
    assert pt.pb == 1.31
    assert pt.dividend_yield is None
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        pt.pe_ttm = 99.0  # type: ignore[misc]


def test_history_holds_ordered_points() -> None:
    rows = (
        IndexValuationPoint("2026-05-28", 11.8, 1.28, None),
        IndexValuationPoint("2026-05-30", 12.1, 1.31, None),
    )
    hist = IndexValuationHistory(index_key="csi300", rows=rows)
    assert hist.index_key == "csi300"
    assert len(hist.rows) == 2
    assert hist.rows[-1].pe_ttm == 12.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fundamentals/test_index_valuation_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'IndexValuationHistory'`.

- [ ] **Step 3: Add the types**

Append to `src/irc/fundamentals/index_valuation_types.py` (keep the existing `IndexValuation` unchanged):

```python
@dataclass(frozen=True)
class IndexValuationPoint:
    """One dated index-valuation observation (full history, item 001 Phase 1)."""
    date_iso: str
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None


@dataclass(frozen=True)
class IndexValuationHistory:
    """Full PE/PB/dividend series for one broad index. Degrades to None at the
    fetch edge (unknown key / adapter failure / empty frame), never raises."""
    index_key: str
    rows: tuple[IndexValuationPoint, ...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fundamentals/test_index_valuation_types.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/fundamentals/test_index_valuation_types.py src/irc/fundamentals/index_valuation_types.py
git commit -m "feat(001): IndexValuationHistory/IndexValuationPoint frozen types"
```

---

## Task 2: `fetch_cn_index_valuation_history` (AkShare-only, full-series)

**Files:**
- Modify: `tests/fundamentals/test_akshare_index_valuation.py`
- Modify: `src/irc/fundamentals/akshare_index_valuation.py`

This reuses the SAME legulegu endpoints (`stock_index_pe_lg`, `stock_index_pb_lg`) and `_INDEX_PE_PB_NAME` map as `fetch_cn_index_valuation`, but keeps the **full series** (not `_extract_latest_value`'s last row). Same degrade-to-`None` contract. R4: NOT a provider method — never imported by `provider.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_akshare_index_valuation.py`:

```python
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory


def test_fetch_history_unknown_index_returns_none_without_calling_ak() -> None:
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        out = fetch_cn_index_valuation_history("not_a_broad_index")
    assert out is None
    mocked.assert_not_called()


def test_fetch_history_extracts_full_series() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake
    ):
        out = fetch_cn_index_valuation_history("csi300")
    assert isinstance(out, IndexValuationHistory)
    assert out.index_key == "csi300"
    # _PE_FRAME / _PB_FRAME each have 3 dated rows aligned on 日期.
    assert len(out.rows) == 3
    assert [r.date_iso for r in out.rows] == ["2026-05-28", "2026-05-29", "2026-05-30"]
    assert out.rows[-1].pe_ttm == 12.1
    assert out.rows[-1].pb == 1.31
    assert out.rows[-1].dividend_yield is None


def test_fetch_history_degrades_to_none_on_adapter_exception() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        side_effect=RuntimeError("network down"),
    ):
        assert fetch_cn_index_valuation_history("csi300") is None


def test_fetch_history_returns_none_on_empty_frames() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_cn_index_valuation_history("csi300") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -k history -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_cn_index_valuation_history'`.

- [ ] **Step 3: Implement the fetcher + pure series helper**

In `src/irc/fundamentals/akshare_index_valuation.py`:

(a) update the import line at the top:

```python
from irc.fundamentals.index_valuation_types import (
    IndexValuation,
    IndexValuationHistory,
    IndexValuationPoint,
)
```

(b) add a pure helper that builds a `date_iso -> value` map from a frame (mirrors `_extract_latest_value`'s column selection, but keeps every row):

```python
def _series_map(df: pd.DataFrame, candidate_cols: tuple[str, ...]) -> dict[str, float | None]:
    """Pure: map each parseable date to the first matching metric column value.

    Unknown/missing column or empty frame → empty map. Non-coercible cells → None
    for that date. Date parsing mirrors `_latest_row`'s `_DATE_COLS` precedence.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    col = next((c for c in candidate_cols if c in df.columns), None)
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    if col is None or date_col is None:
        return {}
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    out: dict[str, float | None] = {}
    for d, raw in zip(parsed, df[col], strict=False):
        if pd.isna(d):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None
        if value is not None and pd.isna(value):
            value = None
        out[d.date().isoformat()] = value
    return out
```

(c) add the fetcher (degrade-to-`None`; full union of PE + PB dates, sorted ascending):

```python
def fetch_cn_index_valuation_history(index_key: str) -> IndexValuationHistory | None:
    """Full PE/PB series for a recognised broad index; None for unknown keys or
    adapter failure. AkShare-only ingest infra (R4) — NOT a provider method."""
    cn_name = _INDEX_PE_PB_NAME.get(index_key)
    if cn_name is None:
        return None
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
    if pe_df is None and pb_df is None:
        return None
    pe_map = _series_map(pe_df if pe_df is not None else pd.DataFrame(), _PE_COLS)
    pb_map = _series_map(pb_df if pb_df is not None else pd.DataFrame(), _PB_COLS)
    div_map = _series_map(pe_df if pe_df is not None else pd.DataFrame(), _DIV_COLS)
    dates = sorted(set(pe_map) | set(pb_map))
    if not dates:
        return None
    rows = tuple(
        IndexValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=pb_map.get(d),
            dividend_yield=div_map.get(d),
        )
        for d in dates
    )
    return IndexValuationHistory(index_key=index_key, rows=rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -v`
Expected: PASS (existing latest-value tests + 4 new history tests).

- [ ] **Step 5: Run the forbidden-indicator acceptance test**

Run: `uv run pytest tests/fundamentals/test_static_profile_invariant.py -v`
Expected: PASS (no `基金概况` introduced).

- [ ] **Step 6: Commit**

```bash
git add tests/fundamentals/test_akshare_index_valuation.py src/irc/fundamentals/akshare_index_valuation.py
git commit -m "feat(001): fetch_cn_index_valuation_history full-series AkShare fetcher"
```

---

## Task 3: `index_valuation_history` DuckDB table

**Files:**
- Test: `tests/data/test_duckdb_helper.py` (modify if present, else create)
- Modify: `src/irc/data/duckdb_helper.py`

Schema (§4.1): `index_valuation_history(index_key TEXT, date DATE, pe_ttm DOUBLE, pb DOUBLE, dividend_yield DOUBLE)`, keyed by `(index_key, date)`, plus the standard `_PROVENANCE_COLS`.

- [ ] **Step 1: Write the failing test**

`tests/data/test_duckdb_helper.py` ALREADY EXISTS (it asserts `EXPECTED_TABLES.issubset(actual)`, so adding a table is safe). APPEND these tests (the `duckdb` / `EXPECTED_TABLES` / `ensure_schema` imports already exist at the top — do not duplicate them):

```python
def test_index_valuation_history_in_expected_tables() -> None:
    assert "index_valuation_history" in EXPECTED_TABLES


def test_ensure_schema_creates_index_valuation_history(tmp_path) -> None:
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    ensure_schema(con)
    cols = {
        r[1]
        for r in con.execute("PRAGMA table_info('index_valuation_history')").fetchall()
    }
    assert {"index_key", "date", "pe_ttm", "pb", "dividend_yield"} <= cols
    # Idempotent: a second call must not raise.
    ensure_schema(con)
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_duckdb_helper.py -v`
Expected: FAIL — `index_valuation_history` not in `EXPECTED_TABLES` / table missing.

- [ ] **Step 3: Register the table**

In `src/irc/data/duckdb_helper.py`, add `"index_valuation_history"` to `EXPECTED_TABLES`:

```python
EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "instruments",
        "prices",
        "nav_history",
        "macro_series",
        "fund_holdings",
        "fund_metrics",
        "events_log",
        "index_valuation_history",
    }
)
```

Add the DDL to the `_DDL_STATEMENTS` tuple (append as the last element, before the closing `)`):

```python
    f"""CREATE TABLE IF NOT EXISTS index_valuation_history (
        index_key      VARCHAR NOT NULL,
        date           DATE    NOT NULL,
        pe_ttm         DOUBLE,
        pb             DOUBLE,
        dividend_yield DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (index_key, date)
    )""",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_duckdb_helper.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/data/test_duckdb_helper.py src/irc/data/duckdb_helper.py
git commit -m "feat(001): register index_valuation_history DuckDB table"
```

---

## Task 4: ingest-stage writer `index_valuation_ingestor`

**Files:**
- Test: `tests/data/test_index_valuation_ingestor.py` (create)
- Create: `src/irc/data/index_valuation_ingestor.py`

Mirrors the `_upsert_*` + `build_ref_id` pattern in `ingest_cmd.py` / `fund_holdings_ingestor.py`: one upsert row per `(index_key, date)`, `INSERT OR REPLACE`, never fatal (a fetch miss / `None` history is skipped, not raised). The fetcher is injected so the ingestor is unit-testable without network.

- [ ] **Step 1: Write the failing tests**

Create `tests/data/test_index_valuation_ingestor.py`:

```python
from __future__ import annotations

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.data.index_valuation_ingestor import ingest_index_valuation_history
from irc.fundamentals.index_valuation_types import (
    IndexValuationHistory,
    IndexValuationPoint,
)


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv.duckdb"))
    ensure_schema(con)
    return con


def test_ingest_writes_one_row_per_date(tmp_path):
    hist = IndexValuationHistory(
        index_key="csi300",
        rows=(
            IndexValuationPoint("2026-05-28", 11.8, 1.28, None),
            IndexValuationPoint("2026-05-30", 12.1, 1.31, None),
        ),
    )
    con = _con(tmp_path)
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: hist, now_iso="2026-05-31T00:00:00+08:00"
    )
    assert written == 2
    rows = con.execute(
        "SELECT index_key, CAST(date AS VARCHAR), pe_ttm, pb FROM "
        "index_valuation_history ORDER BY date"
    ).fetchall()
    assert rows[0] == ("csi300", "2026-05-28", 11.8, 1.28)
    assert rows[1] == ("csi300", "2026-05-30", 12.1, 1.31)
    con.close()


def test_ingest_skips_none_history_without_raising(tmp_path):
    con = _con(tmp_path)
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: None, now_iso="2026-05-31T00:00:00+08:00"
    )
    assert written == 0
    assert con.execute("SELECT COUNT(*) FROM index_valuation_history").fetchone()[0] == 0
    con.close()


def test_ingest_is_idempotent_upsert(tmp_path):
    hist = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-30", 12.1, 1.31, None),),
    )
    con = _con(tmp_path)
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: hist, now_iso="2026-05-31T00:00:00+08:00"
    )
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: hist, now_iso="2026-06-01T00:00:00+08:00"
    )
    assert con.execute("SELECT COUNT(*) FROM index_valuation_history").fetchone()[0] == 1
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py -v`
Expected: FAIL with `ModuleNotFoundError: irc.data.index_valuation_ingestor`.

- [ ] **Step 3: Implement the ingestor**

Create `src/irc/data/index_valuation_ingestor.py`:

```python
"""Ingest-stage writer for `index_valuation_history` (item 001 Phase 1a).

Effect at the edge: fetches each broad index's full PE/PB series via the
AkShare-only `fetch_cn_index_valuation_history` and upserts one row per
(index_key, date). Never fatal — a `None` history (unknown key / adapter
failure / empty frame) is skipped, not raised. This is the ONLY source the
opportunity stage reads for index valuation (no live fetch there — R3).
"""
from __future__ import annotations

from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory

_FetchFn = Callable[[str], IndexValuationHistory | None]


def ingest_index_valuation_history(
    con: duckdb.DuckDBPyConnection,
    index_keys: tuple[str, ...],
    *,
    fetch: _FetchFn = fetch_cn_index_valuation_history,
    now_iso: str,
) -> int:
    """Upsert PE/PB history for each index_key. Returns rows written."""
    params: list[list] = []
    for key in index_keys:
        hist = fetch(key)
        if hist is None:
            continue
        for pt in hist.rows:
            params.append([
                key, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, "akshare",
                build_ref_id("akshare", "index_valuation_history", key, pt.date_iso),
            ])
    if params:
        con.executemany(
            """
            INSERT OR REPLACE INTO index_valuation_history
                (index_key, date, pe_ttm, pb, dividend_yield,
                 _ingested_at, _source, _raw_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
    return len(params)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/data/test_index_valuation_ingestor.py src/irc/data/index_valuation_ingestor.py
git commit -m "feat(001): index_valuation_history ingest-stage writer"
```

---

## Task 5: wire the ingestor into `run_ingest`

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py`
- Test: `tests/commands/test_ingest_index_valuation_wiring.py` (create)

`run_ingest` calls the ingestor once over `_BROAD_INDEX_KEYS`, inside the `try`/`finally` that already holds the open `con`, mirroring the existing macro/holdings calls. Non-fatal (the ingestor never raises); failures are best-effort like fund_holdings.

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_ingest_index_valuation_wiring.py`:

```python
from __future__ import annotations

import inspect

from irc.commands import ingest_cmd


def test_run_ingest_calls_index_valuation_ingestor() -> None:
    """run_ingest must invoke the index-valuation ingestor over the broad-index
    keys so the cached table is refreshed on `irc run --from ingest`."""
    src = inspect.getsource(ingest_cmd.run_ingest)
    assert "ingest_index_valuation_history" in src
    assert "_BROAD_INDEX_KEYS" in src


def test_ingest_cmd_imports_broad_index_keys_and_ingestor() -> None:
    body = inspect.getsource(ingest_cmd)
    assert "from irc.data.index_valuation_ingestor import" in body
    assert "_BROAD_INDEX_KEYS" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_ingest_index_valuation_wiring.py -v`
Expected: FAIL — strings not present in `run_ingest` / module.

- [ ] **Step 3: Add the imports**

In `src/irc/commands/ingest_cmd.py`, add to the import block (near the other `irc.data` imports):

```python
from irc.data.index_valuation_ingestor import ingest_index_valuation_history
from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS
```

- [ ] **Step 4: Add the call inside `run_ingest`**

In `run_ingest`, immediately AFTER the `_MACRO_SERIES` loop (which ends with the `fetch_macro_series` / `_upsert_macro` block) and before the `nav_candidates` block, insert:

```python
        # Item 001 Phase 1a — index PE/PB history (best-effort, non-fatal).
        # Cached source for the opportunity-stage fundamental valuation anchor;
        # the opportunity stage never fetches live (R3). Mirrors fund_holdings:
        # a fetch miss degrades the verdict to NAV-fallback, not a halt.
        try:
            iv_rows = ingest_index_valuation_history(
                con, tuple(sorted(_BROAD_INDEX_KEYS)), now_iso=_now_iso(),
            )
            ak_counts["index_valuation_history"] = iv_rows
        except Exception as exc:  # noqa: BLE001 — best-effort enrichment
            _log.warning("index_valuation_history ingest failed: %s", exc)
            ak_counts["index_valuation_history"] = 0
```

Also add `"index_valuation_history": 0` to the `ak_counts` initialiser dict so the key exists:

```python
        ak_counts: dict[str, int] = {
            "prices": 0, "nav_history": 0, "fund_holdings": 0,
            "index_valuation_history": 0,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_ingest_index_valuation_wiring.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/commands/test_ingest_index_valuation_wiring.py src/irc/commands/ingest_cmd.py
git commit -m "feat(001): wire index_valuation_history ingest into run_ingest"
```

---

## Phase 1a verification checkpoint

- [ ] Run the data-layer + adapter suites:

```bash
uv run pytest tests/fundamentals/test_index_valuation_types.py \
  tests/fundamentals/test_akshare_index_valuation.py \
  tests/data/test_duckdb_helper.py \
  tests/data/test_index_valuation_ingestor.py \
  tests/commands/test_ingest_index_valuation_wiring.py -v
```

Expected: ALL PASS.

- [ ] Forbidden-indicator acceptance grep:

```bash
uv run pytest tests/fundamentals/test_static_profile_invariant.py -v
grep -rn "基金概况" src/irc/fundamentals/akshare_index_valuation.py src/irc/data/index_valuation_ingestor.py
```

Expected: test PASS; grep prints **nothing** (no matches).

- [ ] Provider seam unchanged (R4): confirm `provider.py` was not edited.

```bash
git diff --name-only "$(git merge-base HEAD main)" -- src/irc/fundamentals/provider.py
uv run pytest tests/fundamentals/ -k provider -v
```

Expected: no `provider.py` in the diff list; provider tests PASS untouched.

- [ ] Lint:

```bash
uv run ruff check src tests
```

Expected: no errors in the new/modified files.

**Phase 1a lands inert data** — no verdict changes yet.

---

# PHASE 1b — CLASSIFIER

## Task 6: new `OpportunityInput` fields

**Files:**
- Modify: `src/irc/opportunity/types.py`
- Test: `tests/opportunity/test_inputs_loader.py` (a field-default smoke assertion) or a tiny dataclass test.

Add two `float | None` fields, defaulting to `None` so every existing construction site and cached row stays valid (§4.2).

- [ ] **Step 1: Write the failing test**

Add to `tests/opportunity/test_states.py` (top, after the `_make` helper):

```python
def test_opportunity_input_has_fundamental_percentile_fields_defaulting_none():
    inp = _make()
    assert inp.valuation_percentile_fundamental is None
    assert inp.valuation_percentile_fundamental_pb is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_states.py::test_opportunity_input_has_fundamental_percentile_fields_defaulting_none -v`
Expected: FAIL with `AttributeError: 'OpportunityInput' object has no attribute 'valuation_percentile_fundamental'`.

- [ ] **Step 3: Add the fields**

In `src/irc/opportunity/types.py`, inside the `OpportunityInput` frozen dataclass, add immediately after the `real_yield_10y: float | None = None` line (currently ~line 114):

```python
    # Item 001 Phase 1: index PE-TTM / PB historical percentile (fundamental
    # anchor). Direction matches the price percentile: high = expensive.
    # `valuation_percentile_fundamental` is the PRIMARY equity valuation anchor
    # when present; `..._pb` is corroboration-only (never notches the state).
    # Both None today for any vehicle without a cached index_valuation_history.
    valuation_percentile_fundamental: float | None = None
    valuation_percentile_fundamental_pb: float | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_states.py::test_opportunity_input_has_fundamental_percentile_fields_defaulting_none -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/opportunity/test_states.py src/irc/opportunity/types.py
git commit -m "feat(001): add valuation_percentile_fundamental[_pb] OpportunityInput fields"
```

---

## Task 7: `_band` helper + `valuation_divergence_code` detector (R2)

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

A single pure detector is the one source of truth. It needs a band classifier `_band(pct) -> str` matching the existing thresholds so a band-tier crossing can be compared. (`classify_valuation` keeps inline thresholds today; extract `_band` so both the classifier and the detector share one threshold table — DRY.)

- [ ] **Step 1: Write the failing tests**

Add to `tests/opportunity/test_states.py`:

```python
from irc.opportunity.states import (
    VALUATION_DIVERGENCE_CODE,
    valuation_divergence_code,
)


def _div(**kwargs):
    return _make(asset_class="cn_etf", market="cn_on_exchange", **kwargs)


def test_divergence_none_when_either_percentile_missing():
    assert valuation_divergence_code(_div(valuation_percentile_fundamental=0.1)) is None
    assert valuation_divergence_code(_div(valuation_percentile_self=0.1)) is None
    assert valuation_divergence_code(_div()) is None


def test_divergence_none_when_same_band_and_small_gap():
    # both in `fair` band (0.40..0.70), gap 0.05 < 0.25
    inp = _div(valuation_percentile_fundamental=0.50, valuation_percentile_self=0.55)
    assert valuation_divergence_code(inp) is None


def test_divergence_fires_on_band_tier_crossing():
    # fundamental cheap (<0.20), self fair (0.40..0.70); gap 0.45 also >= 0.25
    inp = _div(valuation_percentile_fundamental=0.10, valuation_percentile_self=0.55)
    assert valuation_divergence_code(inp) == VALUATION_DIVERGENCE_CODE


def test_divergence_fires_on_large_gap_within_same_band():
    # NOTE: choose two values in the SAME band but >= 0.25 apart.
    # fair band spans 0.40..0.70 (width 0.30) → 0.41 and 0.69 are both `fair`,
    # gap 0.28 >= 0.25 → divergence by the gap rule alone.
    inp = _div(valuation_percentile_fundamental=0.41, valuation_percentile_self=0.69)
    assert valuation_divergence_code(inp) == VALUATION_DIVERGENCE_CODE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_states.py -k divergence -v`
Expected: FAIL with `ImportError: cannot import name 'valuation_divergence_code'`.

- [ ] **Step 3: Add `_band`, the constants, and the detector**

In `src/irc/opportunity/states.py`, add near the top of the valuation section (after `_NOTCHABLE_VALUATION_STATES`, before `expected_real_return_positive`):

```python
DIVERGENCE_PCT_GAP: float = 0.25
VALUATION_DIVERGENCE_CODE: str = "valuation_price_fundamental_divergence"

# Shared band thresholds — the single source of truth for the percentile->band
# mapping used by classify_valuation AND valuation_divergence_code (DRY).
_VALUATION_BANDS: tuple[tuple[float, str], ...] = (
    (0.20, "cheap"),
    (0.40, "reasonable_low"),
    (0.70, "fair"),
    (0.90, "expensive"),
)


def _band(pct: float) -> str:
    """Map a percentile to its valuation band tier (matches classify_valuation)."""
    for upper, name in _VALUATION_BANDS:
        if pct < upper:
            return name
    return "very_expensive"


def valuation_divergence_code(inp: OpportunityInput) -> str | None:
    """Return the advisory code when the fundamental and NAV percentiles
    disagree (different band-tier OR |gap| >= DIVERGENCE_PCT_GAP); else None.

    Single source of truth (R2): classify_valuation uses it for the reason note;
    build_opportunity_row folds it into advisory_gaps.
    """
    f, n = inp.valuation_percentile_fundamental, inp.valuation_percentile_self
    if f is None or n is None:
        return None
    if _band(f) != _band(n) or abs(f - n) >= DIVERGENCE_PCT_GAP:
        return VALUATION_DIVERGENCE_CODE
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_states.py -k divergence -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/opportunity/test_states.py src/irc/opportunity/states.py
git commit -m "feat(001): _band helper + valuation_divergence_code detector (R2)"
```

---

## Task 8: `classify_valuation` becomes fundamental-decides + notes

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

The equity path now bands on `valuation_percentile_fundamental` when present; else falls back to `_percentile(inp)` (AC2, byte-for-byte). Add a divergence reason note (step 3, §4.4) and a PB corroboration note (step 4, §4.4) — neither changes state in Phase 1. The existing earnings-yield anchor block and the `valuation_fundamental_signal` notch are preserved.

- [ ] **Step 1: Write the failing tests**

Add to `tests/opportunity/test_states.py`:

```python
def test_fundamental_percentile_decides_each_band():
    # When valuation_percentile_fundamental is present it OVERRIDES the NAV pct.
    cases = {
        0.10: "cheap",
        0.30: "reasonable_low",
        0.55: "fair",
        0.80: "expensive",
        0.95: "very_expensive",
    }
    for fund_pct, expected in cases.items():
        inp = _make(
            valuation_percentile_fundamental=fund_pct,
            valuation_percentile_self=0.50,  # deliberately disagrees
        )
        state, _ = classify_valuation(inp)
        assert state == expected, (fund_pct, state)


def test_fundamental_none_falls_back_to_nav_byte_for_byte():
    # Regression lock (AC2): no fundamental pct → identical to today's NAV path.
    inp = _make(valuation_percentile_fundamental=None, valuation_percentile_self=0.95)
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    # The fallback path must not mention the fundamental percentile.
    assert "PE" not in reason or "PE 百分位" not in reason


def test_classify_valuation_appends_divergence_note_without_signature_change():
    inp = _make(
        valuation_percentile_fundamental=0.10,  # cheap
        valuation_percentile_self=0.85,          # expensive
    )
    out = classify_valuation(inp)
    assert isinstance(out, tuple) and len(out) == 2
    state, reason = out
    assert state == "cheap"  # fundamental decides
    assert "背离" in reason  # divergence caveat present


def test_pb_corroboration_note_appears_without_changing_state():
    # PE-band cheap but PB percentile >= 0.70 → cyclical-earnings caveat, state stays cheap.
    inp = _make(
        valuation_percentile_fundamental=0.10,
        valuation_percentile_fundamental_pb=0.85,
        valuation_percentile_self=0.10,  # agree → no divergence note
    )
    state, reason = classify_valuation(inp)
    assert state == "cheap"
    assert "PB" in reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_states.py -k "fundamental_percentile or divergence_note or pb_corroboration or falls_back" -v`
Expected: FAIL (fundamental percentile ignored; no divergence/PB notes).

- [ ] **Step 3: Rewrite the equity branch of `classify_valuation`**

Replace the body of `classify_valuation` from the `pct = _percentile(inp)` line through the end of the function. Keep the bond dispatch and the docstring. New body:

```python
    if inp.asset_class in _BOND_ASSET_CLASSES:
        return classify_bond_valuation(inp)
    # Phase 1 (item 001): the FUNDAMENTAL index PE-TTM percentile decides the
    # band when present; otherwise fall back to the NAV self-history percentile
    # (AC2 — byte-for-byte unchanged for vehicles with no fundamental data).
    fund_pct = inp.valuation_percentile_fundamental
    if fund_pct is not None:
        pct = fund_pct
        anchor_label = "PE 百分位"
    else:
        pct = _percentile(inp)
        anchor_label = "估值百分位"
    if pct is None:
        return "evidence_insufficient", "估值数据缺失，未能判定。"
    if pct < 0.20:
        state, reason = "cheap", f"{anchor_label} {pct:.0%} 偏低。"
    elif pct < 0.40:
        state, reason = "reasonable_low", f"{anchor_label} {pct:.0%} 偏低但未极低。"
    elif pct < 0.70:
        state, reason = "fair", f"{anchor_label} {pct:.0%} 中性。"
    elif pct < 0.90:
        state, reason = "expensive", f"{anchor_label} {pct:.0%} 偏高。"
    else:
        state, reason = "very_expensive", f"{anchor_label} {pct:.0%} 极高。"
    # Equity sanity anchor (§B3): high price percentile can persist for years
    # (1995-2000); if earnings_yield - real_yield_10y > 0 the equity is still
    # offering a positive expected real return, which a DCA investor should know
    # before treating "very_expensive" as "avoid".
    if (
        state in _EXPENSIVE_VALUATION_STATES
        and inp.asset_class in _EQUITY_ASSET_CLASSES
    ):
        signal = expected_real_return_positive(inp)
        if signal is True:
            reason = (
                f"{reason} 但 earnings_yield - real_yield 为正，"
                f"长期 DCA 视为正期望，估值高位不等于退出信号。"
            )
        elif signal is False:
            reason = (
                f"{reason} 且 earnings_yield - real_yield 非正，"
                f"长期实际回报预期偏弱。"
            )
    if inp.asset_class in _EQUITY_ASSET_CLASSES:
        # Step 3 (§4.4): price/fundamental divergence reason note. The advisory
        # code itself is folded into advisory_gaps by build_opportunity_row (R2);
        # here we only annotate the reason. classify_valuation keeps (state, reason).
        if valuation_divergence_code(inp) is not None:
            reason = (
                f"{reason} 价格与基本面估值百分位背离"
                f"（价格 {_percentile(inp):.0%} vs 基本面 {fund_pct:.0%}），"
                f"以基本面为准。"
            )
        # Step 4 (§4.4, Q5): PB corroboration note — cyclical/earnings-quality
        # caveat when PE says cheap but PB percentile is elevated. NO state change.
        pb_pct = inp.valuation_percentile_fundamental_pb
        if (
            state in _NOTCHABLE_VALUATION_STATES
            and pb_pct is not None
            and pb_pct >= 0.70
        ):
            reason = (
                f"{reason} 但 PB 百分位 {pb_pct:.0%} 偏高，"
                f"或为周期性盈利高估，便宜判断需谨慎。"
            )
        fundamental = valuation_fundamental_signal(inp)
        if fundamental is not None:
            reason = f"{reason} {_fundamental_reason_phrase(fundamental, inp)}"
            # AC3: corroboration-only one-notch move toward cheaper. Never
            # toward more-expensive; never promotes fair/expensive/very_expensive.
            if fundamental == "cheap" and state in _NOTCHABLE_VALUATION_STATES:
                state = "cheap"
    return state, reason
```

NOTE on the divergence-note guard: `valuation_divergence_code` already returns `None` unless BOTH percentiles are present, so `_percentile(inp)` and `fund_pct` are non-`None` inside that branch — the `:.0%` formats are safe.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_states.py -k "fundamental_percentile or divergence_note or pb_corroboration or falls_back" -v`
Expected: PASS.

- [ ] **Step 5: Run the FULL existing valuation suite (AC2 regression lock)**

Run: `uv run pytest tests/opportunity/test_states.py tests/opportunity/test_earnings_yield_anchor.py -v`
Expected: ALL PASS — including every pre-existing NAV-percentile test (they pass `valuation_percentile_self` only, so `fund_pct is None` → identical fallback). The earnings-yield-anchor tests still pass because their `_equity(...)` inputs set only `valuation_percentile_self`.

- [ ] **Step 6: Commit**

```bash
git add tests/opportunity/test_states.py src/irc/opportunity/states.py
git commit -m "feat(001): classify_valuation fundamental-decides + divergence/PB notes"
```

---

## Task 9: `ADVISORY_GAP_CODES` registration

**Files:**
- Modify: `src/irc/opportunity/advisory_gaps.py`
- Test: `tests/opportunity/test_advisory_gaps.py` (modify if present, else create)

- [ ] **Step 1: Write the failing test**

`tests/opportunity/test_advisory_gaps.py` ALREADY EXISTS. APPEND this test (add the `ADVISORY_GAP_CODES` import if not already present at the top):

```python
from irc.opportunity.advisory_gaps import ADVISORY_GAP_CODES


def test_valuation_divergence_code_is_advisory():
    assert "valuation_price_fundamental_divergence" in ADVISORY_GAP_CODES
    # The pre-existing advisory member is preserved.
    assert "top_holdings_broker_thin" in ADVISORY_GAP_CODES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_advisory_gaps.py::test_valuation_divergence_code_is_advisory -v`
Expected: FAIL — code not registered.

- [ ] **Step 3: Register the code**

In `src/irc/opportunity/advisory_gaps.py`, extend `ADVISORY_GAP_CODES`:

```python
ADVISORY_GAP_CODES: Final[frozenset[str]] = frozenset({
    "top_holdings_broker_thin",
    "valuation_price_fundamental_divergence",
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_advisory_gaps.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/opportunity/test_advisory_gaps.py src/irc/opportunity/advisory_gaps.py
git commit -m "feat(001): register valuation_price_fundamental_divergence advisory code"
```

---

## Task 10: thread divergence into `build_opportunity_row` (R2 / H3)

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

`build_opportunity_row` folds the divergence code into `combined_gaps` before `_partition_gaps`, so it routes to `advisory_gaps` (never `evidence_gaps`) and the row stays publishable. H3 partition predicate (`evidence_gaps == ()`) is untouched.

- [ ] **Step 1: Write the failing test**

Add to `tests/opportunity/test_states.py`:

```python
from irc.opportunity.states import build_opportunity_row


def _broad_index_inp(**kwargs):
    base = dict(
        instrument_id="510300",
        asset_class="cn_etf",
        market="cn_on_exchange",
        name_cn="沪深300ETF",
        tracked_index="csi300",
        # enough heat + product signals so the row is otherwise publishable
        ret_1m=0.0, ret_3m=0.0, expense_ratio=0.005, aum_cny=5.0e10,
    )
    base.update(kwargs)
    return OpportunityInput(**base)


def test_build_row_routes_divergence_to_advisory_not_evidence_gaps():
    inp = _broad_index_inp(
        valuation_percentile_fundamental=0.10,  # cheap
        valuation_percentile_self=0.85,          # expensive → divergence
    )
    # theme_thesis provided so classify_thesis has a table; snapshot=None path.
    row = build_opportunity_row(inp, {"宽基": "intact"})
    assert "valuation_price_fundamental_divergence" in row.advisory_gaps
    assert "valuation_price_fundamental_divergence" not in row.evidence_gaps


def test_build_row_no_divergence_code_when_percentiles_agree():
    inp = _broad_index_inp(
        valuation_percentile_fundamental=0.10,
        valuation_percentile_self=0.12,  # agree → no divergence
    )
    row = build_opportunity_row(inp, {"宽基": "intact"})
    assert "valuation_price_fundamental_divergence" not in row.advisory_gaps
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_states.py -k "routes_divergence or no_divergence_code" -v`
Expected: FAIL — code not in `advisory_gaps`.

- [ ] **Step 3: Add `_divergence_gaps` + thread it in**

In `src/irc/opportunity/states.py`, add a small helper near `valuation_divergence_code`:

```python
def _divergence_gaps(inp: OpportunityInput) -> tuple[str, ...]:
    """0/1-tuple wrapping valuation_divergence_code for the gap stream (R2)."""
    code = valuation_divergence_code(inp)
    return (code,) if code is not None else ()
```

In `build_opportunity_row`, change the `combined_gaps` line (currently `combined_gaps = tuple(structural_gaps) + tuple(thesis_gaps)`) to:

```python
    combined_gaps = (
        tuple(structural_gaps) + tuple(thesis_gaps) + _divergence_gaps(inp)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_states.py -k "routes_divergence or no_divergence_code" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/opportunity/test_states.py src/irc/opportunity/states.py
git commit -m "feat(001): thread valuation divergence into advisory_gaps (R2/H3)"
```

---

## Task 11: `populate_inputs` — remove live fetch, read cached history, wire real_yield (R1/R3)

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py`
- Test: `tests/opportunity/test_inputs_loader.py`

R3: delete the `provider.fetch_index_valuation(...)` call. Read the index PE/PB **history** from `index_valuation_history` (a pure `_index_valuation_series` reader mirroring `_price_series`). From a single read: latest row → `pe_ttm`/`pb`/`dividend_yield` + `earnings_yield = 1/pe_ttm`; full PE/PB series → `self_history_percentile` → `valuation_percentile_fundamental[_pb]`. R1: `real_yield_10y = cn_10y_yield/100` (ratio).

- [ ] **Step 1: Write the failing tests**

Add to `tests/opportunity/test_inputs_loader.py`:

```python
def _seed_index_valuation_history(con, index_key, pe_pb_pairs, base_date=date(2025, 1, 1)):
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(base_date.toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_populate_inputs_reads_cached_index_valuation_percentile(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    # 30+ rising PE points so self_history_percentile fires; latest is the max.
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(40)]
    _seed_index_valuation_history(con, "csi300", pairs)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300", name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    # latest PE = 10 + 39*0.1 = 13.9; pb = 1 + 39*0.01 = 1.39
    assert inp.pe_ttm == pytest.approx(13.9)
    assert inp.pb == pytest.approx(1.39)
    assert inp.valuation_percentile_fundamental == pytest.approx(1.0)
    assert inp.valuation_percentile_fundamental_pb == pytest.approx(1.0)
    # earnings_yield = 1/13.9
    assert inp.earnings_yield == pytest.approx(1.0 / 13.9)
    con.close()


def test_populate_inputs_fundamental_percentile_none_under_30_points(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv2.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_index_valuation_history(con, "csi300", [(12.0, 1.3)] * 10)  # < 30 points
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is None
    assert inp.valuation_percentile_fundamental_pb is None
    # latest pe/pb still populated (for reason text + earnings_yield).
    assert inp.pe_ttm == pytest.approx(12.0)
    assert inp.earnings_yield == pytest.approx(1.0 / 12.0)
    con.close()


def test_populate_inputs_real_yield_in_ratio_units(tmp_path):
    # R1 regression: cn_10y_yield = 2.45 (percent) → real_yield_10y ≈ 0.0245 (ratio).
    con = duckdb.connect(str(tmp_path / "iv3.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_cn_10y_yield(con, [2.45, 2.45, 2.45])
    _seed_index_valuation_history(con, "csi300", [(14.0, 1.3)] * 30)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.real_yield_10y == pytest.approx(0.0245)
    # earnings_yield = 1/14 ≈ 0.0714 > 0.0245 → anchor reads POSITIVE.
    assert inp.earnings_yield == pytest.approx(1.0 / 14.0)
    from irc.opportunity.states import expected_real_return_positive
    assert expected_real_return_positive(inp) is True
    con.close()


def test_populate_inputs_no_live_index_fetch(tmp_path):
    # R3: a provider whose fetch_index_valuation raises must NOT be invoked.
    con = duckdb.connect(str(tmp_path / "iv4.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_index_valuation_history(con, "csi300", [(12.0, 1.3)] * 30)
    provider = _StubProvider(raise_on_fetch=True)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    # Must not raise — the index path reads the cached table, never the provider.
    inp = populate_inputs(con, skeleton, holding_entry_date=None, provider=provider)
    assert inp.pe_ttm == pytest.approx(12.0)
    con.close()
```

Also update the two pre-existing index-valuation tests that asserted the provider supplied pe/pb (`test_populate_inputs_fills_pe_pb_for_recognised_broad_index` and `test_populate_inputs_leaves_pe_pb_none_for_unrecognised_index`): they now must seed/omit the cached table instead of the provider stub. Rewrite their bodies:

```python
def test_populate_inputs_fills_pe_pb_for_recognised_broad_index(tmp_path):
    con = duckdb.connect(str(tmp_path / "csi.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_index_valuation_history(con, "csi300", [(12.1, 1.31)])
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300", name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm == pytest.approx(12.1)
    assert inp.pb == pytest.approx(1.31)
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_unrecognised_index(tmp_path):
    con = duckdb.connect(str(tmp_path / "unk.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('159999','159999','cn_on_exchange','某主题ETF',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 1.0e9, NULL, 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:159999')"
    )
    skeleton = OpportunityInput(
        instrument_id="159999", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="some_sector_theme",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None
    assert inp.pb is None
    assert inp.dividend_yield is None
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -k "cached_index or under_30 or real_yield or no_live_index or fills_pe_pb or unrecognised_index" -v`
Expected: FAIL — `_index_valuation_metrics` still live-fetches; cached read + real_yield not implemented.

- [ ] **Step 3: Replace `_index_valuation_metrics` with a cached reader + add real_yield helper**

In `src/irc/opportunity/inputs_loader.py`:

(a) add a constant near `_CN_10Y_YIELD_SERIES_ID`:

```python
_CPI_YOY_SERIES_ID = "cn_cpi_yoy"  # not ingested in Phase 1; nominal-gap fallback used.
```

(b) add a `_cn_10y_yield_latest` reader (latest value, percent units) and `_real_yield_10y_ratio` (R1):

```python
def _cn_10y_yield_latest(con: duckdb.DuckDBPyConnection) -> float | None:
    df = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [_CN_10Y_YIELD_SERIES_ID],
    ).fetchdf()
    if df.empty:
        return None
    return _none_if_na(df.iloc[0]["value"])


def _cpi_yoy_latest(con: duckdb.DuckDBPyConnection) -> float | None:
    df = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [_CPI_YOY_SERIES_ID],
    ).fetchdf()
    if df.empty:
        return None
    return _none_if_na(df.iloc[0]["value"])


def _real_yield_10y_ratio(con: duckdb.DuckDBPyConnection) -> float | None:
    """R1 ratio units. Default = nominal 10Y CGB yield as a ratio (股债利差).
    If a CN CPI-YoY series is present, switch to the true-real gap. Never reuse
    real_yield_10y_tips (US TIPS, percent)."""
    cn_10y = _cn_10y_yield_latest(con)
    if cn_10y is None:
        return None
    cpi = _cpi_yoy_latest(con)
    if cpi is not None:
        return (cn_10y - cpi) / 100.0
    return cn_10y / 100.0
```

(c) replace `_index_valuation_metrics` entirely with a cached-history reader that returns latest pe/pb/div AND the percentiles (R3 — no `provider` param):

```python
def _index_valuation_series(
    con: duckdb.DuckDBPyConnection, index_key: str
) -> pd.DataFrame:
    df = con.execute(
        "SELECT date, pe_ttm, pb, dividend_yield FROM index_valuation_history "
        "WHERE index_key = ? ORDER BY date",
        [index_key],
    ).fetchdf()
    return df


def _index_valuation_metrics(
    con: duckdb.DuckDBPyConnection, tracked_index: str | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Return (pe_ttm, pb, dividend_yield, pe_percentile, pb_percentile) from the
    CACHED index_valuation_history table (R3 — no live fetch). (None,)*5 when the
    index is not a recognised broad index or has no cached rows."""
    key = (tracked_index or "").strip().lower() or None
    if key is None or key not in _BROAD_INDEX_KEYS:
        return None, None, None, None, None
    df = _index_valuation_series(con, key)
    if df.empty:
        return None, None, None, None, None
    latest = df.iloc[-1]
    pe = _none_if_na(latest["pe_ttm"])
    pb = _none_if_na(latest["pb"])
    div = _none_if_na(latest["dividend_yield"])
    pe_series = pd.Series(df["pe_ttm"].to_numpy(), index=pd.to_datetime(df["date"]))
    pb_series = pd.Series(df["pb"].to_numpy(), index=pd.to_datetime(df["date"]))
    pe_pct = self_history_percentile(pe_series)
    pb_pct = self_history_percentile(pb_series)
    return pe, pb, div, pe_pct, pb_pct
```

(d) update `populate_inputs`: remove the `provider`-based index call, compute `earnings_yield` + `real_yield_10y`, and thread the new fields into `replace(...)`. Change the index-metrics call site:

```python
    pe_ttm, pb, dividend_yield, fund_pct, fund_pct_pb = _index_valuation_metrics(
        con, skeleton.tracked_index
    )
    earnings_yield = (
        1.0 / pe_ttm if pe_ttm is not None and pe_ttm > 0 else None
    )
    real_yield = _real_yield_10y_ratio(con)
```

and add to the `return replace(...)` call (after the existing `dividend_yield=dividend_yield,` line):

```python
        valuation_percentile_fundamental=fund_pct,
        valuation_percentile_fundamental_pb=fund_pct_pb,
        earnings_yield=earnings_yield,
        real_yield_10y=real_yield,
```

NOTE: the `provider` parameter on `populate_inputs` is RETAINED (still feeds the broker/consensus path via `consensus_upside_pct`). Only the *index* fetch moves to the cached read. `_StubProvider`'s `fetch_index_valuation` is now never called by the index path — that is exactly what `test_populate_inputs_no_live_index_fetch` proves.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -v`
Expected: ALL PASS (new tests + rewritten pe/pb tests + every pre-existing test).

- [ ] **Step 5: Confirm `import` cleanliness**

`_index_valuation_metrics` no longer needs `provider`; the module still imports `CnFundamentalsProvider`/`default_cn_provider` for the consensus path — keep them. Run:

```bash
uv run ruff check src/irc/opportunity/inputs_loader.py
```

Expected: no unused-import errors.

- [ ] **Step 6: Commit**

```bash
git add tests/opportunity/test_inputs_loader.py src/irc/opportunity/inputs_loader.py
git commit -m "feat(001): populate_inputs cached index read + real_yield ratio (R1/R3)"
```

---

## Task 12: discipline-report divergence legend note (§4.5)

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Test: `tests/opportunity/test_report.py` (modify if present, else create)

`advisory_gaps` already threads `OpportunityRow → ThesisCard/DisciplineRow` (via `cards.py` / `opportunity_cmd.py`). The legend note is a parallel `advisory_suffix` in `_render_section`, mirroring the existing `top_holdings_broker_thin` suffix.

- [ ] **Step 1: Write the failing test**

`tests/opportunity/test_report.py` ALREADY EXISTS and defines a `_row(...)` helper that returns an `OpportunityRow` plus positional `DisciplineRow(...)` construction. Do NOT redefine `_row`. APPEND these tests with a distinctly-named helper (`compose_discipline_markdown` + `DisciplineRow` are already imported at the top of the file):

```python
def _disc_row(**kwargs) -> DisciplineRow:
    base = dict(
        instrument_id="510300", name_cn="沪深300ETF", asset_class="cn_etf",
        theme="宽基", opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="ok",
    )
    base.update(kwargs)
    return DisciplineRow(**base)


def test_discipline_report_surfaces_divergence_advisory():
    row = _disc_row(advisory_gaps=("valuation_price_fundamental_divergence",))
    md = compose_discipline_markdown([row], date="2026-06-03")
    assert "价格与基本面估值背离" in md


def test_discipline_report_no_divergence_suffix_when_absent():
    md = compose_discipline_markdown([_disc_row()], date="2026-06-03")
    assert "价格与基本面估值背离" not in md
```

NOTE: `compose_discipline_markdown`'s `date` is a keyword arg in the existing tests — pass `date="..."` (not positional).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_report.py -k divergence -v`
Expected: FAIL — suffix string absent.

- [ ] **Step 3: Add the divergence suffix in `_render_section`**

In `src/irc/opportunity/report.py`, inside `_render_section`'s `for r in rows:` loop, extend the advisory-suffix logic so multiple advisory notes compose. Replace the current single `advisory_suffix = (...)` block with:

```python
        advisory_notes: list[str] = []
        gaps = getattr(r, "advisory_gaps", ())
        if "top_holdings_broker_thin" in gaps:
            advisory_notes.append("核心持仓券商覆盖不足")
        if "valuation_price_fundamental_divergence" in gaps:
            advisory_notes.append("价格与基本面估值背离")
        advisory_suffix = (
            " ｜ 证据缺口：" + "；".join(advisory_notes) if advisory_notes else ""
        )
```

(The rest of the `lines.append(...)` block is unchanged — it already interpolates `{advisory_suffix}`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_report.py -v`
Expected: PASS (both new tests + any pre-existing report tests, since the broker-thin wording `核心持仓券商覆盖不足` is preserved).

- [ ] **Step 5: Run the existing report/appendix regression suite**

Run: `uv run pytest tests/opportunity/test_report_appendix.py -v` (if present)
Expected: PASS — the appendix-line regex contract is untouched.

- [ ] **Step 6: Commit**

```bash
git add tests/opportunity/test_report.py src/irc/opportunity/report.py
git commit -m "feat(001): discipline-report divergence legend note"
```

---

## Phase 1b verification checkpoint

- [ ] Full opportunity + fundamentals + data suites:

```bash
uv run pytest tests/opportunity tests/fundamentals tests/data -v
```

Expected: ALL PASS.

- [ ] **AC8 invariant — `derive_position_risk_level` untouched.** Confirm `narrative/risk.py` has ZERO edits across the whole feature:

```bash
git diff --stat "$(git merge-base HEAD main)" -- src/irc/narrative/risk.py
uv run pytest tests/narrative/test_risk.py -v
```

Expected: empty diff stat for `risk.py`; risk tests PASS unchanged.

- [ ] **AC7 / R4 — provider stays 3-method.** Confirm no provider edits and `fetch_cn_index_valuation_history` is not referenced in `provider.py`:

```bash
git diff --stat "$(git merge-base HEAD main)" -- src/irc/fundamentals/provider.py
grep -n "fetch_cn_index_valuation_history" src/irc/fundamentals/provider.py
uv run pytest tests/fundamentals -k provider -v
```

Expected: empty diff stat; grep prints nothing; provider tests PASS.

- [ ] **Forbidden `基金概况`** anywhere in new/modified fetch code:

```bash
uv run pytest tests/fundamentals/test_static_profile_invariant.py -v
grep -rn "基金概况" src/irc/ | grep -v "test_static_profile_invariant"
```

Expected: test PASS; grep prints only any pre-existing benign matches (none expected in the files this plan touches).

- [ ] Lint the whole tree:

```bash
uv run ruff check src tests
```

Expected: clean.

---

## Final feature verification

- [ ] Full suite scoped to the affected areas (avoid the ~18-min full run; the e2e research gate is flaky per project baseline):

```bash
uv run pytest tests/opportunity tests/fundamentals tests/data tests/commands tests/narrative -q
```

Expected: PASS. (Note from MEMORY: `main` carries ~8 known pre-existing failures + a flaky e2e research gate — diff-check scope before treating any red as a regression introduced here.)

- [ ] **AC1–AC9 self-check** — tick each against the tasks that prove it:
  - AC1 → Task 8 `test_fundamental_percentile_decides_each_band`.
  - AC2 → Task 8 `test_fundamental_none_falls_back_to_nav_byte_for_byte` + full `test_states.py`.
  - AC3 → Task 8 (state set by band only) + unchanged `compose_opportunity_state` (R5).
  - AC4 → Task 7 (detector) + Task 9 (registration) + Task 10 (routing).
  - AC5 → Task 11 `test_populate_inputs_real_yield_in_ratio_units`.
  - AC6 → Task 11 `test_populate_inputs_no_live_index_fetch`.
  - AC7 → Phase 1b checkpoint (provider diff empty).
  - AC8 → Phase 1b checkpoint (`risk.py` diff empty).
  - AC9 → `self_history_percentile` reused verbatim (Task 11 `..._none_under_30_points`).

---

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks (REQUIRED SUB-SKILL: superpowers:subagent-driven-development).

**2. Inline Execution** — execute tasks in this session with checkpoints (REQUIRED SUB-SKILL: superpowers:executing-plans).
