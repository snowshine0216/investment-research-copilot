# Phase D PR1 — active-fund holdings look-through (shadow compute) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-stock valuation fetch/ingest path, a pure fund-level look-through aggregation core, a dedicated `irc fundamentals stock-valuation` command, a flag-gated `inputs_loader` active-fund branch (flag default OFF so prod is byte-identical), and the gate-#5 diff report — i.e. PR1 shadow-compute only, per spec §3.8/§10.

**Architecture:** Mirror the existing index-valuation path (`fetch → ingest → DuckDB table → inputs_loader reads cached → percentile`) with a **per-stock sibling** (`akshare_stock_valuation`/`tushare_stock_valuation` → `stock_valuation_history` → `stock_valuation_ingestor`) plus **one new pure module** (`opportunity/lookthrough_valuation.py`) that rolls a fund's current top-N A-share basket into a harmonic earnings-yield series and percentiles it. Effects stay at the edges (two fetchers + the command + DuckDB writes); the aggregation core is pure and unit-testable without mocks. The config flag (`active_fund_lookthrough.enabled`, default `false`) gates **slot population** in `inputs_loader`, threaded explicitly through `run_opportunity → _build_rows → _build_input → populate_inputs`.

**Tech Stack:** Python 3.12, `uv`, Click, DuckDB, pandas, AkShare (`stock_value_em`, EastMoney CN-direct), Tushare (`daily_basic`, optional token fallback), pydantic-settings, pytest (with `live_akshare`/`live_tushare` double-gated markers).

---

## Scope guardrails (read before starting — DO NOT EXCEED)

This plan delivers **PR1 only** (spec §3.8, §10; MASTER-PLAN "Hard stops"). The following are **explicitly out of scope** and MUST NOT appear in any task:

- **Do NOT flip the flag to `enabled: true`.** That is PR2, gated on the human gate-#5 floor decision. The config block ships with `enabled: false`.
- **Do NOT execute the live AkShare/Tushare tests.** The live-gated test code is *authored* (Task 12, Task 13) but never *run* in this loop. No verification command in this plan may use `-m live_akshare` or `-m live_tushare`. Column-string confirmation against real EastMoney rows is the human gate #4.
- **Do NOT write an ADR addendum or a CHANGELOG flag-flip record.** Those belong to PR2. A PR1 CHANGELOG `[Unreleased]` entry for the shadow-compute machinery IS in scope (Task 17). Per project memory: **do NOT bump `VERSION`** (currently `0.9.3`).
- **Do NOT change** `derive_position_risk_level`, the index path, `classify_valuation`, or any classifier logic. `valuation_percentile_fundamental[_pb]` are plain numeric inputs (no `ThesisEvidence`, no `[ref:...]`); the dual-coverage gate, SAME-3, H3 partition, citation id, Policy B / `thesis_state` ownership are structurally untouched (spec §7, ADR 0012 Consequences).

## Test-suite baseline caveat (per project memory)

Full `uv run pytest` is ~18 min and is **NOT green on `main`** (8 known pre-existing failures + a flaky e2e research gate). **Every "run tests" step in this plan names the specific new/touched test path(s)** — never assert a blanket whole-suite green bar. When distinguishing a regression from a pre-existing failure, scope to this item's files.

## TDD discipline (every code task)

Red → green → refactor. The failing-test step always precedes the implementation step. Test file mirrors source (`src/irc/foo/bar.py` → `tests/foo/test_bar.py`). The pure aggregation core (Tasks 5–9) gets the richest unit tests, with **no mocks**. Files < 200 lines, functions < 20 lines (extract helpers). Pure functions, frozen dataclasses, `dataclasses.replace`, no argument mutation, no shared mutable module state, secrets in `.env` only.

## File map (created / modified)

| File | Action | Responsibility |
|---|---|---|
| `src/irc/fundamentals/stock_valuation_types.py` | Create | Frozen DTOs `StockValuationPoint`, `StockValuationHistory` (mirror `index_valuation_types.py`). |
| `src/irc/fundamentals/akshare_stock_valuation.py` | Create | EastMoney `stock_value_em(symbol)` thin call + pure column extraction. |
| `src/irc/fundamentals/tushare_stock_valuation.py` | Create | Tushare `daily_basic` per-stock fallback via existing token plumbing. |
| `src/irc/data/duckdb_helper.py` | Modify | Add `stock_valuation_history` DDL + `EXPECTED_TABLES` entry. |
| `src/irc/data/stock_valuation_ingestor.py` | Create | Atomic `INSERT OR REPLACE`, `_source` per row, `is_stock_valuation_stale`, `ingest_one`/`ingest_many` (failure-isolating). |
| `src/irc/opportunity/lookthrough_valuation.py` | Create | **Pure** aggregation core: `fund_valuation_percentile`, `FundValuationResult`, `MetricCoverage`. |
| `src/irc/schemas/valuation.py` | Modify | Add `ActiveFundLookthroughConfig` + `active_fund_lookthrough` field. |
| `config/valuation_buckets.yaml` | Modify | Add the `active_fund_lookthrough` block (default OFF). |
| `src/irc/opportunity/inputs_loader.py` | Modify | Active-fund branch (flag-gated slot population); new `lookthrough_cfg` kwarg on `populate_inputs`. |
| `src/irc/opportunity/inputs_build.py` | Modify | Thread `lookthrough_cfg` through `_build_input → populate_inputs`. |
| `src/irc/commands/opportunity_cmd.py` | Modify | Thread `bundle.valuation_buckets.active_fund_lookthrough` through `run_opportunity → _build_rows → _build_input`. |
| `src/irc/commands/fundamentals_cmd.py` | Modify | `run_stock_valuation_refresh` orchestration. |
| `src/irc/cli.py` | Modify | `@fundamentals.command("stock-valuation")`. |
| `src/irc/opportunity/lookthrough_diff_report.py` | Create | Pure diff-report builder (per-fund flip band, Δpercentile, per-metric coverage/source, floor sensitivity). |
| `src/irc/commands/lookthrough_diff_cmd.py` | Create | `run_lookthrough_diff` — loads cached data, writes the gate-#5 artifact. |
| `CHANGELOG.md` | Modify | `[Unreleased]` shadow-compute entry. |
| Tests mirror each of the above under `tests/`. | Create | See per-task Test paths. |

---

## Task 1: `stock_valuation_history` DuckDB table

**Files:**
- Modify: `src/irc/data/duckdb_helper.py`
- Test: `tests/data/test_duckdb_helper.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/test_duckdb_helper.py`:

```python
def test_stock_valuation_history_in_expected_tables() -> None:
    from irc.data.duckdb_helper import EXPECTED_TABLES
    assert "stock_valuation_history" in EXPECTED_TABLES


def test_ensure_schema_creates_stock_valuation_history(tmp_path) -> None:
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "sv.duckdb")
    ensure_schema(con)
    cols = {
        r[1] for r in con.execute(
            "PRAGMA table_info('stock_valuation_history')"
        ).fetchall()
    }
    assert {
        "stock_code", "date", "pe_ttm", "pb", "dividend_yield",
        "_ingested_at", "_source", "_raw_ref",
    } <= cols
    con.close()


def test_stock_valuation_history_primary_key_is_stock_code_date(tmp_path) -> None:
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "sv.duckdb")
    ensure_schema(con)
    pk = [
        r[1] for r in con.execute(
            "PRAGMA table_info('stock_valuation_history')"
        ).fetchall() if r[5]  # r[5] = pk flag
    ]
    assert pk == ["stock_code", "date"]
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_duckdb_helper.py::test_stock_valuation_history_in_expected_tables tests/data/test_duckdb_helper.py::test_ensure_schema_creates_stock_valuation_history tests/data/test_duckdb_helper.py::test_stock_valuation_history_primary_key_is_stock_code_date -v`
Expected: FAIL — `"stock_valuation_history" not in EXPECTED_TABLES` / no such table.

- [ ] **Step 3: Add the table to `EXPECTED_TABLES`**

In `src/irc/data/duckdb_helper.py`, add `"stock_valuation_history"` to the `EXPECTED_TABLES` frozenset (after `"index_valuation_history"`):

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
        "stock_valuation_history",
    }
)
```

- [ ] **Step 4: Add the DDL beside `index_valuation_history`**

In `_DDL_STATEMENTS`, append after the `index_valuation_history` statement (note: columns mirror the index table exactly — `pe_ttm`/`pb`/`dividend_yield` nullable, PK `(stock_code, date)`, standard provenance cols):

```python
    f"""CREATE TABLE IF NOT EXISTS stock_valuation_history (
        stock_code     VARCHAR NOT NULL,
        date           DATE    NOT NULL,
        pe_ttm         DOUBLE,
        pb             DOUBLE,
        dividend_yield DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (stock_code, date)
    )""",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_duckdb_helper.py -v`
Expected: PASS (all, including the existing provenance-column and idempotence tests which iterate `EXPECTED_TABLES`).

- [ ] **Step 6: Commit**

```bash
git add src/irc/data/duckdb_helper.py tests/data/test_duckdb_helper.py
git commit -m "feat(data): add stock_valuation_history DuckDB table (Phase D PR1)"
```

---

## Task 2: `StockValuationPoint` / `StockValuationHistory` DTOs

**Files:**
- Create: `src/irc/fundamentals/stock_valuation_types.py`
- Test: `tests/fundamentals/test_stock_valuation_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fundamentals/test_stock_valuation_types.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)


def test_point_is_frozen_with_nullable_metrics() -> None:
    pt = StockValuationPoint(date_iso="2026-05-30", pe_ttm=18.2, pb=2.1, dividend_yield=None)
    assert pt.date_iso == "2026-05-30"
    assert pt.dividend_yield is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        pt.pe_ttm = 1.0  # type: ignore[misc]


def test_history_carries_stock_code_and_rows() -> None:
    hist = StockValuationHistory(
        stock_code="600519",
        rows=(StockValuationPoint("2026-05-30", 18.2, 2.1, None),),
    )
    assert hist.stock_code == "600519"
    assert len(hist.rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fundamentals/test_stock_valuation_types.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.fundamentals.stock_valuation_types`.

- [ ] **Step 3: Create the DTO module (mirror `index_valuation_types.py`)**

Create `src/irc/fundamentals/stock_valuation_types.py`:

```python
"""Per-stock valuation snapshot types (Phase D PR1).

Frozen, immutable. All metric fields are `float | None` — every fetch path
degrades to None on failure / missing column, never raises. Mirrors
`index_valuation_types.py` for the per-A-share look-through path.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockValuationPoint:
    """One dated per-stock valuation observation (full history)."""
    date_iso: str
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None


@dataclass(frozen=True)
class StockValuationHistory:
    """Full PE/PB/dividend series for one A-share. Degrades to None at the
    fetch edge (unknown / adapter failure / empty frame), never raises."""
    stock_code: str
    rows: tuple[StockValuationPoint, ...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fundamentals/test_stock_valuation_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/stock_valuation_types.py tests/fundamentals/test_stock_valuation_types.py
git commit -m "feat(fundamentals): StockValuationPoint/History DTOs (Phase D PR1)"
```

---

## Task 3: EastMoney `stock_value_em` fetcher (primary)

**Files:**
- Create: `src/irc/fundamentals/akshare_stock_valuation.py`
- Test: `tests/fundamentals/test_akshare_stock_valuation.py`

EastMoney `stock_value_em(symbol="<6-digit>")` returns the full daily history with columns `数据日期` (date), `PE(TTM)`, `市净率` (PB), plus 总市值/PEG/etc. Extract `(数据日期→date, PE(TTM)→pe_ttm, 市净率→pb)`; `dividend_yield` is always `None` (EastMoney exposes no per-stock dividend yield — mirror the index fetcher's `dividend_yield=None` rationale, spec §6.4). Degrade-to-None on empty/raise. Network I/O confined to `_ak_call`.

- [ ] **Step 1: Write the failing tests (pure column extraction, no network)**

Create `tests/fundamentals/test_akshare_stock_valuation.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals.akshare_stock_valuation import (
    _series_maps,
    fetch_stock_valuation_history,
)
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_FRAME = pd.DataFrame({
    "数据日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "PE(TTM)": [18.0, 18.1, 18.2],
    "市净率": [2.0, 2.05, 2.1],
    "总市值": [1.0e12, 1.0e12, 1.0e12],
})


def test_series_maps_extracts_pe_and_pb_by_date() -> None:
    pe_map, pb_map = _series_maps(_FRAME)
    assert pe_map["2026-05-30"] == 18.2
    assert pb_map["2026-05-28"] == 2.0


def test_series_maps_empty_frame_returns_empty_maps() -> None:
    pe_map, pb_map = _series_maps(pd.DataFrame())
    assert pe_map == {} and pb_map == {}


def test_series_maps_coerces_non_numeric_to_none() -> None:
    frame = pd.DataFrame({"数据日期": ["2026-05-30"], "PE(TTM)": ["-"], "市净率": ["-"]})
    pe_map, pb_map = _series_maps(frame)
    assert pe_map["2026-05-30"] is None and pb_map["2026-05-30"] is None


def test_fetch_returns_history_with_dividend_yield_none() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call", return_value=_FRAME
    ):
        out = fetch_stock_valuation_history("600519")
    assert isinstance(out, StockValuationHistory)
    assert out.stock_code == "600519"
    assert len(out.rows) == 3
    assert out.rows[-1].pe_ttm == 18.2
    assert out.rows[-1].pb == 2.1
    assert all(r.dividend_yield is None for r in out.rows)


def test_fetch_degrades_to_none_on_empty_frame() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_stock_valuation_history("600519") is None


def test_fetch_degrades_to_none_on_raise() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        side_effect=RuntimeError("boom"),
    ):
        assert fetch_stock_valuation_history("600519") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_stock_valuation.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.fundamentals.akshare_stock_valuation`.

- [ ] **Step 3: Create the fetcher (mirror `akshare_index_valuation.py`)**

Create `src/irc/fundamentals/akshare_stock_valuation.py`:

```python
"""Per-stock PE/PB valuation fetcher (Phase D PR1) via EastMoney `stock_value_em`.

`stock_value_em(symbol="<6-digit>")` returns the full daily history with
columns `数据日期` (date), `PE(TTM)`, `市净率` (PB), plus 总市值/PEG/etc. One call
returns ~2000+ trading days — ample for the 120/180 maturity gate. Free, no
token, A-share only, CN-direct (NOT proxied — it is a CN domain).

`dividend_yield` is left None: EastMoney exposes no per-stock dividend yield
(mirrors the index fetcher; the column stays nullable). Degrade-to-None
contract: adapter raise / empty frame / no parseable dates → None, never raises.

EXACT column strings are pinned by the gate-#4 live test
(`tests/fundamentals/test_stock_valuation_live.py`) — authored, not run here.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)

_PE_COL: str = "PE(TTM)"
_PB_COL: str = "市净率"
_DATE_COL: str = "数据日期"


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import

    return getattr(ak, fn_name)(**kwargs)


def _coerce(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(value) else value


def _series_maps(
    df: pd.DataFrame,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Pure: map each parseable 数据日期 to its PE(TTM) and 市净率 value."""
    if not isinstance(df, pd.DataFrame) or df.empty or _DATE_COL not in df.columns:
        return {}, {}
    parsed = pd.to_datetime(df[_DATE_COL], errors="coerce")
    pe_raw = df[_PE_COL] if _PE_COL in df.columns else [None] * len(df)
    pb_raw = df[_PB_COL] if _PB_COL in df.columns else [None] * len(df)
    pe_map: dict[str, float | None] = {}
    pb_map: dict[str, float | None] = {}
    for d, pe, pb in zip(parsed, pe_raw, pb_raw, strict=True):
        if pd.isna(d):
            continue
        iso = d.date().isoformat()
        pe_map[iso] = _coerce(pe)
        pb_map[iso] = _coerce(pb)
    return pe_map, pb_map


def _fetch_frame(symbol: str) -> pd.DataFrame | None:
    try:
        df = _ak_call("stock_value_em", symbol=symbol)
    except Exception:
        return None
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def fetch_stock_valuation_history(stock_code: str) -> StockValuationHistory | None:
    """Full PE/PB series for an A-share via EastMoney; None on miss/empty/raise.
    AkShare-only ingest infra — NOT a provider method."""
    df = _fetch_frame(stock_code)
    if df is None:
        return None
    pe_map, pb_map = _series_maps(df)
    dates = sorted(set(pe_map) | set(pb_map))
    if not dates:
        return None
    rows = tuple(
        StockValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=pb_map.get(d),
            dividend_yield=None,
        )
        for d in dates
    )
    return StockValuationHistory(stock_code=stock_code, rows=rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_stock_valuation.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_stock_valuation.py tests/fundamentals/test_akshare_stock_valuation.py
git commit -m "feat(fundamentals): EastMoney stock_value_em per-stock fetcher (Phase D PR1)"
```

---

## Task 4: Tushare `daily_basic` fetcher (fallback)

**Files:**
- Create: `src/irc/fundamentals/tushare_stock_valuation.py`
- Test: `tests/fundamentals/test_tushare_stock_valuation.py`

Tushare `daily_basic` per-stock via the existing `_tushare_call` token plumbing (reuses `_to_ts_code`, `_first_col`, `_coerce_float`, `_pct_to_ratio` patterns from `tushare_provider.py`). Map `pe_ttm`/`pb` (and `dv_ratio→dividend_yield` when present); degrade-to-None when no token / empty / raise. Tushare is CN (api.tushare.pro) → called DIRECT, never proxied.

> Note: `daily_basic` columns are `trade_date`, `pe_ttm`, `pb`, `dv_ratio` (ratio convention varies by tier — `dv_ratio` is in **percent** on Tushare, so divide by 100 to land a ratio consistent with the spec's `dv_ratio→dividend_yield` mapping; the look-through core does not consume `dividend_yield`, so this is provenance-only correctness, locked by the live test under gate #4). `pe_ttm`/`pb` are absolute values — pass through via `_coerce_float`.

- [ ] **Step 1: Write the failing tests (pure mapping, no network)**

Create `tests/fundamentals/test_tushare_stock_valuation.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals.stock_valuation_types import StockValuationHistory
from irc.fundamentals.tushare_stock_valuation import (
    _map_daily_basic,
    fetch_stock_valuation_history_tushare,
)

_FRAME = pd.DataFrame({
    "trade_date": ["20260528", "20260530"],
    "pe_ttm": [18.0, 18.2],
    "pb": [2.0, 2.1],
    "dv_ratio": [1.5, 1.6],  # percent units on Tushare
})


def test_map_daily_basic_extracts_pe_pb_and_dividend_ratio() -> None:
    hist = _map_daily_basic("600519", _FRAME)
    assert isinstance(hist, StockValuationHistory)
    assert hist.rows[0].date_iso == "2026-05-28"
    assert hist.rows[-1].pe_ttm == 18.2
    assert hist.rows[-1].pb == 2.1
    # dv_ratio 1.6% → 0.016 ratio
    assert abs(hist.rows[-1].dividend_yield - 0.016) < 1e-9


def test_map_daily_basic_missing_dv_ratio_leaves_dividend_none() -> None:
    frame = pd.DataFrame({"trade_date": ["20260530"], "pe_ttm": [18.2], "pb": [2.1]})
    hist = _map_daily_basic("600519", frame)
    assert hist is not None and hist.rows[0].dividend_yield is None


def test_map_daily_basic_empty_frame_returns_none() -> None:
    assert _map_daily_basic("600519", pd.DataFrame()) is None


def test_fetch_returns_none_without_token() -> None:
    assert fetch_stock_valuation_history_tushare("600519", token="") is None


def test_fetch_degrades_to_none_on_raise() -> None:
    with patch(
        "irc.fundamentals.tushare_stock_valuation._tushare_call",
        side_effect=RuntimeError("boom"),
    ):
        assert fetch_stock_valuation_history_tushare("600519", token="tok") is None


def test_fetch_maps_when_token_present() -> None:
    with patch(
        "irc.fundamentals.tushare_stock_valuation._tushare_call",
        return_value=_FRAME,
    ):
        out = fetch_stock_valuation_history_tushare("600519", token="tok")
    assert isinstance(out, StockValuationHistory)
    assert out.rows[-1].pe_ttm == 18.2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_tushare_stock_valuation.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.fundamentals.tushare_stock_valuation`.

- [ ] **Step 3: Create the fallback fetcher**

Create `src/irc/fundamentals/tushare_stock_valuation.py`:

```python
"""Per-stock PE/PB Tushare fallback (Phase D PR1) via `daily_basic`.

Fired only on a `stock_value_em` miss/empty. Token-gated (reuses the existing
`.env` TUSHARE_TOKEN plumbing); absent token ⇒ None (no hard failure, the
coverage floor catches shrunk coverage). All network I/O confined to
`_tushare_call` (local `import tushare`); CN-direct, never proxied.

`daily_basic` columns: trade_date, pe_ttm, pb, dv_ratio (dv_ratio is percent →
ratio via /100, mirroring tushare_provider._pct_to_ratio). EXACT columns pinned
by the gate-#4 live test — authored, not run here.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)

_log = logging.getLogger(__name__)

_PE_COLS: tuple[str, ...] = ("pe_ttm", "pe")
_PB_COLS: tuple[str, ...] = ("pb",)
_DIV_COLS: tuple[str, ...] = ("dv_ratio", "dv_ttm")


def _tushare_call(token: str, fn_name: str, **kwargs: Any) -> Any:
    """Network edge (mirrors tushare_provider._tushare_call). Direct, no proxy."""
    import tushare as ts  # local import — never at module load

    pro = ts.pro_api(token)
    return getattr(pro, fn_name)(**kwargs)


def _to_ts_code(symbol: str) -> str:
    code = str(symbol).strip()
    if "." in code:
        return code
    head = code[:1]
    if head in ("5", "6"):
        suffix = "SH"
    elif head in ("4", "8"):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{code}.{suffix}"


def _first_col(df: pd.DataFrame, cols: tuple[str, ...]) -> str | None:
    return next((c for c in cols if c in df.columns), None)


def _coerce_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _pct_to_ratio(value: Any) -> float | None:
    f = _coerce_float(value)
    return None if f is None else f / 100.0


def _iso_from_trade_date(raw: Any) -> str | None:
    s = str(raw)
    if len(s) != 8 or not s.isdigit():
        return None
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _map_daily_basic(stock_code: str, df: pd.DataFrame) -> StockValuationHistory | None:
    if not isinstance(df, pd.DataFrame) or df.empty or "trade_date" not in df.columns:
        return None
    pe_col = _first_col(df, _PE_COLS)
    pb_col = _first_col(df, _PB_COLS)
    dv_col = _first_col(df, _DIV_COLS)
    ordered = df.sort_values("trade_date")
    rows: list[StockValuationPoint] = []
    for _, row in ordered.iterrows():
        iso = _iso_from_trade_date(row["trade_date"])
        if iso is None:
            continue
        rows.append(StockValuationPoint(
            date_iso=iso,
            pe_ttm=_coerce_float(row[pe_col]) if pe_col else None,
            pb=_coerce_float(row[pb_col]) if pb_col else None,
            dividend_yield=_pct_to_ratio(row[dv_col]) if dv_col else None,
        ))
    if not rows:
        return None
    return StockValuationHistory(stock_code=stock_code, rows=tuple(rows))


def fetch_stock_valuation_history_tushare(
    stock_code: str, *, token: str
) -> StockValuationHistory | None:
    """Tushare daily_basic fallback; None when no token / empty / raise."""
    if not token:
        return None
    ts_code = _to_ts_code(stock_code)
    try:
        df = _tushare_call(token, "daily_basic", ts_code=ts_code)
    except Exception as exc:
        _log.warning(
            "tushare daily_basic(%r) failed: %s: %s", stock_code, type(exc).__name__, exc
        )
        return None
    return _map_daily_basic(stock_code, df)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_tushare_stock_valuation.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/tushare_stock_valuation.py tests/fundamentals/test_tushare_stock_valuation.py
git commit -m "feat(fundamentals): Tushare daily_basic per-stock fallback (Phase D PR1)"
```

---

## Task 5: aggregation core — `MetricCoverage` / `FundValuationResult` + covered-set selection

**Files:**
- Create: `src/irc/opportunity/lookthrough_valuation.py`
- Test: `tests/opportunity/test_lookthrough_valuation.py`

This is the **pure** aggregation core (spec §6.3). It takes the fund's current top-N holdings and a `series_by_code` mapping (per-stock `StockValuationHistory`-shaped series), and returns a `FundValuationResult` with **per-metric** coverage. PE and PB covered sets are computed **independently** (§6.3): a name can have a usable PE but a missing/non-positive PB, or vice-versa.

Public surface (the whole module is built across Tasks 5–9; this task establishes the dataclasses + the input shape + the per-metric covered-set selector):

```python
fund_valuation_percentile(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, coverage_floor: float, pb_uses_pe_gate: bool,
) -> FundValuationResult
```

Define the input adapter types (so the core stays decoupled from DuckDB / DTO shapes):
- `HoldingWeight(code: str, weight_pct: float)` — `weight_pct` in **percent units 0..100** (matches `fund_holdings.weight_pct`).
- `MetricSeries(code: str, source: str, points: tuple[tuple[str, float | None, float | None], ...])` — `(date_iso, pe_ttm, pb)` per date; `source ∈ {"eastmoney","tushare"}`.

- [ ] **Step 1: Write the failing tests (dataclasses + covered-set selection)**

Create `tests/opportunity/test_lookthrough_valuation.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from irc.opportunity.lookthrough_valuation import (
    HoldingWeight,
    MetricCoverage,
    MetricSeries,
    _covered_codes_for_metric,
    fund_valuation_percentile,
)


def _series(code, source, points):
    return MetricSeries(code=code, source=source, points=tuple(points))


def test_metric_coverage_is_frozen() -> None:
    mc = MetricCoverage(percentile=0.5, coverage_ratio=0.6, covered_codes=("600519",),
                        source_mix=("eastmoney",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        mc.percentile = 0.9  # type: ignore[misc]


def test_covered_codes_excludes_non_positive_and_missing_pe() -> None:
    # 600519 has positive PE; 000001 has a non-positive PE; 600000 has no series.
    holdings = (
        HoldingWeight("600519", 30.0),
        HoldingWeight("000001", 25.0),
        HoldingWeight("600000", 20.0),
    )
    series = {
        "600519": _series("600519", "eastmoney", [("2026-05-30", 18.0, 2.0)]),
        "000001": _series("000001", "eastmoney", [("2026-05-30", -5.0, 1.5)]),
    }
    covered = _covered_codes_for_metric(holdings, series, metric="pe")
    assert covered == ("600519",)


def test_covered_codes_pb_independent_of_pe() -> None:
    # 000001 has a non-positive PE (excluded from PE) but a positive PB (kept for PB).
    holdings = (HoldingWeight("000001", 25.0),)
    series = {"000001": _series("000001", "eastmoney", [("2026-05-30", -5.0, 1.5)])}
    assert _covered_codes_for_metric(holdings, series, metric="pe") == ()
    assert _covered_codes_for_metric(holdings, series, metric="pb") == ("000001",)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.opportunity.lookthrough_valuation`.

- [ ] **Step 3: Create the module skeleton + dataclasses + covered-set selector**

Create `src/irc/opportunity/lookthrough_valuation.py`:

```python
"""Pure look-through valuation aggregation core (Phase D PR1, spec §6.3).

Rolls a fund's CURRENT disclosed top-N A-share basket into a synthetic
earnings-yield (harmonic) PE series and a parallel PB series, then percentiles
the latest value via `self_history_percentile`. PE and PB covered sets are
computed INDEPENDENTLY (a name can have usable PE but missing/non-positive PB).

NO I/O, NO mutation — every function is pure and unit-testable without mocks.
Coverage = Σ weight_pct/100.0 (ratio of NAV); the /100 is load-bearing (§3.2).
Non-positive PE/PB excluded (§3.6). Per-date renormalization (§3.1/§3.4).
PE maturity gate = 120 points AND 180 days (mirrors inputs_loader); PB gated
only by self_history_percentile's <30 floor (§3.3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_Metric = Literal["pe", "pb"]


@dataclass(frozen=True)
class HoldingWeight:
    code: str
    weight_pct: float  # percent units 0..100 (matches fund_holdings.weight_pct)


@dataclass(frozen=True)
class MetricSeries:
    code: str
    source: str  # "eastmoney" | "tushare"
    points: tuple[tuple[str, float | None, float | None], ...]  # (date_iso, pe, pb)


@dataclass(frozen=True)
class MetricCoverage:
    percentile: float | None
    coverage_ratio: float
    covered_codes: tuple[str, ...]
    source_mix: tuple[str, ...]


@dataclass(frozen=True)
class FundValuationResult:
    pe: MetricCoverage
    pb: MetricCoverage


def _metric_index(metric: _Metric) -> int:
    return 1 if metric == "pe" else 2


def _has_positive_metric(series: MetricSeries, metric: _Metric) -> bool:
    """True iff the series has at least one strictly-positive value for metric."""
    idx = _metric_index(metric)
    return any(p[idx] is not None and p[idx] > 0.0 for p in series.points)


def _covered_codes_for_metric(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, metric: _Metric,
) -> tuple[str, ...]:
    """Codes that (a) are in the basket, (b) have a series, (c) have ≥1 positive
    metric value. Order follows the holdings input order (deterministic)."""
    return tuple(
        h.code
        for h in holdings
        if h.code in series_by_code
        and _has_positive_metric(series_by_code[h.code], metric)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -v`
Expected: PASS (4).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough_valuation.py tests/opportunity/test_lookthrough_valuation.py
git commit -m "feat(opportunity): look-through core dataclasses + per-metric covered set (Phase D PR1)"
```

---

## Task 6: coverage ratio + the `/100` floor boundary (P0 regression)

**Files:**
- Modify: `src/irc/opportunity/lookthrough_valuation.py`
- Test: `tests/opportunity/test_lookthrough_valuation.py`

Coverage ratio = `Σ_{covered} weight_pct / 100.0`. The floor compares the **ratio** (NOT the raw percent sum). The P0 regression: a fund whose raw `Σ weight_pct ≈ 55` must produce coverage ratio `0.55` and PASS a `0.50` floor; summing raw `weight_pct` against `0.50` would pass virtually every fund incorrectly (§3.2).

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_lookthrough_valuation.py`:

```python
from irc.opportunity.lookthrough_valuation import _coverage_ratio, _meets_floor


def test_coverage_ratio_divides_percent_by_100() -> None:
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    assert abs(_coverage_ratio(holdings, ("600519", "000001")) - 0.55) < 1e-9


def test_coverage_ratio_only_counts_covered_codes() -> None:
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    assert abs(_coverage_ratio(holdings, ("600519",)) - 0.30) < 1e-9


def test_floor_compares_ratio_not_raw_percent_sum_p0() -> None:
    # P0 regression: raw Σ weight_pct ≈ 55, ratio 0.55. Floor 0.50 must PASS on
    # the RATIO. If the code compared the raw percent sum (55) against 0.50,
    # every fund would pass — this asserts that bug cannot recur.
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    ratio = _coverage_ratio(holdings, ("600519", "000001"))
    assert ratio == 0.55
    assert _meets_floor(ratio, coverage_floor=0.50) is True
    # And a basket whose ratio is below the floor must FAIL.
    low = _coverage_ratio((HoldingWeight("600519", 30.0),), ("600519",))
    assert low == 0.30
    assert _meets_floor(low, coverage_floor=0.50) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "coverage_ratio or floor" -v`
Expected: FAIL — `cannot import name '_coverage_ratio'`.

- [ ] **Step 3: Add the helpers**

Append to `src/irc/opportunity/lookthrough_valuation.py`:

```python
def _coverage_ratio(
    holdings: tuple[HoldingWeight, ...], covered_codes: tuple[str, ...]
) -> float:
    """Ratio of NAV covered: Σ weight_pct / 100.0 over covered codes (§3.2).
    The /100 is load-bearing — weight_pct is stored in percent units 0..100."""
    covered = set(covered_codes)
    return sum(h.weight_pct for h in holdings if h.code in covered) / 100.0


def _meets_floor(coverage_ratio: float, *, coverage_floor: float) -> bool:
    """Floor is compared on the RATIO (§3.2). >= so a fund exactly at the floor
    is accepted (mirrors the FOREIGN_HEAVY_THRESHOLD >= convention)."""
    return coverage_ratio >= coverage_floor
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "coverage_ratio or floor" -v`
Expected: PASS (3).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough_valuation.py tests/opportunity/test_lookthrough_valuation.py
git commit -m "feat(opportunity): coverage ratio + /100 floor boundary (P0 regression) (Phase D PR1)"
```

---

## Task 7: per-date renormalized harmonic aggregation

**Files:**
- Modify: `src/irc/opportunity/lookthrough_valuation.py`
- Test: `tests/opportunity/test_lookthrough_valuation.py`

Build the synthetic `metric_fund(t)` series. On each date `t`, aggregate only over the covered-set holdings that have a **positive** metric value at `t`, renormalizing their weights by the weight present at `t` (per-date renormalization, §3.1/§3.4). Drop dates where the present (covered, positive) weight ratio `< coverage_floor` (so a date covered by one mega-cap doesn't masquerade as the whole basket). Aggregation is harmonic on the metric's yield (`1/metric`):

```
yield_fund(t) = Σ_i w̃_i(t) · (1/metric_i(t))      metric_fund(t) = 1 / yield_fund(t)
```

where `w̃_i(t)` are the covered weights renormalized over the holdings present-and-positive at `t`.

- [ ] **Step 1: Write the failing tests (worked harmonic example + per-date renorm)**

Append to `tests/opportunity/test_lookthrough_valuation.py`:

```python
from irc.opportunity.lookthrough_valuation import _aggregate_metric_series


def test_worked_harmonic_two_stock_equal_weight() -> None:
    # Two equal-weight holdings, PE 10 and PE 30 on a single date.
    # EY = 0.5*(1/10) + 0.5*(1/30) = 0.05 + 0.016666... = 0.066666...
    # PE_fund = 1 / 0.066666... = 15.0 (harmonic mean, NOT arithmetic 20).
    holdings = (HoldingWeight("A", 25.0), HoldingWeight("B", 25.0))
    series = {
        "A": MetricSeries("A", "eastmoney", (("2026-05-30", 10.0, None),)),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.50,
    )
    assert list(out.index.astype(str)) == ["2026-05-30"]
    assert abs(float(out.iloc[-1]) - 15.0) < 1e-9


def test_per_date_renormalization_with_shorter_history() -> None:
    # A has 2 dates, B has only the later date. On the earlier date only A is
    # present, so its renormalized weight is 1.0 → PE_fund = A's PE = 10.0.
    # On the later date both present → harmonic of 10 and 30 at equal weight = 15.
    holdings = (HoldingWeight("A", 25.0), HoldingWeight("B", 25.0))
    series = {
        "A": MetricSeries("A", "eastmoney",
                          (("2026-05-01", 10.0, None), ("2026-05-30", 10.0, None))),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.40,
    )
    vals = {str(d): float(v) for d, v in out.items()}
    assert abs(vals["2026-05-01"] - 10.0) < 1e-9   # only A present
    assert abs(vals["2026-05-30"] - 15.0) < 1e-9   # both present


def test_per_date_drops_dates_below_present_weight_floor() -> None:
    # A (weight 10%) alone on the early date → present ratio 0.10 < floor 0.50
    # → that date is dropped. Both present on the later date → kept.
    holdings = (HoldingWeight("A", 10.0), HoldingWeight("B", 45.0))
    series = {
        "A": MetricSeries("A", "eastmoney",
                          (("2026-05-01", 10.0, None), ("2026-05-30", 10.0, None))),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.50,
    )
    assert list(out.index.astype(str)) == ["2026-05-30"]


def test_non_positive_metric_value_excluded_per_date() -> None:
    # A's value flips negative on the early date → excluded that date; only B's
    # later positive date survives (A positive again contributes there).
    holdings = (HoldingWeight("A", 25.0), HoldingWeight("B", 25.0))
    series = {
        "A": MetricSeries("A", "eastmoney",
                          (("2026-05-01", -5.0, None), ("2026-05-30", 10.0, None))),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.40,
    )
    # Early date: only B present? No — B has no early point; A's is negative.
    # So early date has no positive contributor → dropped. Later date → 15.0.
    assert list(out.index.astype(str)) == ["2026-05-30"]
    assert abs(float(out.iloc[-1]) - 15.0) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "harmonic or renormaliz or below_present or non_positive_metric" -v`
Expected: FAIL — `cannot import name '_aggregate_metric_series'`.

- [ ] **Step 3: Implement the per-date aggregation**

Append to `src/irc/opportunity/lookthrough_valuation.py` (extract a small per-date helper to stay under the 20-line budget):

```python
import pandas as pd


def _present_contributions(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    covered_codes: tuple[str, ...],
    metric: _Metric,
    iso: str,
) -> tuple[dict[str, float], dict[str, float]]:
    """For date `iso`: return (weight_by_code, value_by_code) over covered codes
    whose series has a strictly-positive metric value on that date."""
    idx = _metric_index(metric)
    covered = set(covered_codes)
    weight_by_code: dict[str, float] = {}
    value_by_code: dict[str, float] = {}
    for h in holdings:
        if h.code not in covered:
            continue
        for date_iso, pe, pb in series_by_code[h.code].points:
            if date_iso != iso:
                continue
            value = (pe, pb)[idx - 1]
            if value is not None and value > 0.0:
                weight_by_code[h.code] = h.weight_pct
                value_by_code[h.code] = value
    return weight_by_code, value_by_code


def _all_dates(
    series_by_code: dict[str, MetricSeries], covered_codes: tuple[str, ...]
) -> tuple[str, ...]:
    dates: set[str] = set()
    for code in covered_codes:
        dates.update(p[0] for p in series_by_code[code].points)
    return tuple(sorted(dates))


def _aggregate_metric_series(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    covered_codes: tuple[str, ...],
    *, metric: _Metric, coverage_floor: float,
) -> pd.Series:
    """Per-date renormalized harmonic metric series (§3.1/§3.4). Drops dates
    whose present (covered, positive) weight ratio < coverage_floor."""
    out_idx: list[str] = []
    out_val: list[float] = []
    for iso in _all_dates(series_by_code, covered_codes):
        weight_by_code, value_by_code = _present_contributions(
            holdings, series_by_code, covered_codes, metric, iso
        )
        present_ratio = sum(weight_by_code.values()) / 100.0
        if not weight_by_code or present_ratio < coverage_floor:
            continue
        total_w = sum(weight_by_code.values())
        ey = sum(
            (weight_by_code[c] / total_w) * (1.0 / value_by_code[c])
            for c in weight_by_code
        )
        if ey <= 0.0:
            continue
        out_idx.append(iso)
        out_val.append(1.0 / ey)
    return pd.Series(out_val, index=pd.to_datetime(out_idx))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "harmonic or renormaliz or below_present or non_positive_metric" -v`
Expected: PASS (4).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough_valuation.py tests/opportunity/test_lookthrough_valuation.py
git commit -m "feat(opportunity): per-date renormalized harmonic aggregation (Phase D PR1)"
```

---

## Task 8: maturity gate (PE 120/180 vs PB <30 floor) + percentile

**Files:**
- Modify: `src/irc/opportunity/lookthrough_valuation.py`
- Test: `tests/opportunity/test_lookthrough_valuation.py`

PE percentile requires the fund series to clear the index path's bar — `≥ MIN_PE_POINTS (120)` non-null points AND `≥ MIN_PE_DAYS (180)` calendar-day span. **Reuse the index path's `_pe_series_is_mature` semantics by importing the constants and the function from `inputs_loader`** (single source of truth — do NOT redefine 120/180). PB is gated **only** by `self_history_percentile`'s `<30 → None` floor, NOT the 120/180 gate (§3.3). Both percentiles via `self_history_percentile`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_lookthrough_valuation.py`:

```python
import pandas as pd

from irc.opportunity.lookthrough_valuation import _percentile_for_metric


def _ramp_series(n: int, span_days: int) -> pd.Series:
    dates = pd.date_range("2025-01-01", periods=n, freq=f"{max(span_days // max(n - 1, 1), 1)}D")
    return pd.Series([float(i + 1) for i in range(n)], index=dates)


def test_pe_percentile_none_when_below_120_points() -> None:
    # 100 points over a 365-day span: clears the day-span bar but NOT 120 points.
    s = pd.Series([float(i + 1) for i in range(100)],
                  index=pd.date_range("2025-01-01", periods=100, freq="4D"))
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) is None


def test_pe_percentile_none_when_span_below_180_days() -> None:
    # 130 points but crammed into < 180 days → fails the day-span half of the gate.
    s = pd.Series([float(i + 1) for i in range(130)],
                  index=pd.date_range("2025-01-01", periods=130, freq="1D"))  # 129 days
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) is None


def test_pe_percentile_present_when_gate_cleared() -> None:
    # 200 points over ~398 days → clears both halves. Latest is the max → 1.0.
    s = pd.Series([float(i + 1) for i in range(200)],
                  index=pd.date_range("2025-01-01", periods=200, freq="2D"))
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) == 1.0


def test_pb_percentile_ignores_120_180_gate_uses_only_30_floor() -> None:
    # 40 points, ~40-day span: fails the 120/180 gate but clears the <30 floor.
    # PB (pb_uses_pe_gate=False) returns a percentile; PE on the same series → None.
    s = pd.Series([float(i + 1) for i in range(40)],
                  index=pd.date_range("2025-01-01", periods=40, freq="1D"))
    assert _percentile_for_metric(s, metric="pb", pb_uses_pe_gate=False) == 1.0
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) is None


def test_pb_percentile_none_below_30_floor() -> None:
    s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2025-01-01", periods=3, freq="1D"))
    assert _percentile_for_metric(s, metric="pb", pb_uses_pe_gate=False) is None


def test_pb_with_pe_gate_flag_applies_120_180() -> None:
    # When pb_uses_pe_gate=True, PB inherits the 120/180 gate (flippable call).
    s = pd.Series([float(i + 1) for i in range(40)],
                  index=pd.date_range("2025-01-01", periods=40, freq="1D"))
    assert _percentile_for_metric(s, metric="pb", pb_uses_pe_gate=True) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "percentile" -v`
Expected: FAIL — `cannot import name '_percentile_for_metric'`.

- [ ] **Step 3: Implement the gate + percentile (reuse the index-path gate)**

Append to `src/irc/opportunity/lookthrough_valuation.py`:

```python
from irc.opportunity.inputs_loader import _pe_series_is_mature
from irc.opportunity.returns import self_history_percentile


def _percentile_for_metric(
    series: pd.Series, *, metric: _Metric, pb_uses_pe_gate: bool
) -> float | None:
    """PE: requires the 120/180 maturity gate (reused from the index path) AND
    the <30 floor inside self_history_percentile. PB: only the <30 floor unless
    pb_uses_pe_gate is True (§3.3)."""
    if series.empty:
        return None
    apply_pe_gate = metric == "pe" or pb_uses_pe_gate
    if apply_pe_gate and not _pe_series_is_mature(series):
        return None
    return self_history_percentile(series)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "percentile" -v`
Expected: PASS (6).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/lookthrough_valuation.py tests/opportunity/test_lookthrough_valuation.py
git commit -m "feat(opportunity): PE 120/180 gate vs PB <30 floor + percentile (Phase D PR1)"
```

---

## Task 9: public `fund_valuation_percentile` (assemble per-metric coverage) + degrade-to-None

**Files:**
- Modify: `src/irc/opportunity/lookthrough_valuation.py`
- Test: `tests/opportunity/test_lookthrough_valuation.py`

Assemble the public entry: for each metric independently — pick covered codes, compute coverage ratio, if the floor fails return `MetricCoverage(percentile=None, ...)` (still report the ratio/covered/source so the diff report is honest), else aggregate + gate + percentile. `source_mix` = sorted unique provider set over **that metric's** covered codes. Every gap path degrades to a `None` percentile (no holdings / coverage below floor / series fails maturity / empty inputs).

- [ ] **Step 1: Write the failing tests (assembly + every degrade path)**

Append to `tests/opportunity/test_lookthrough_valuation.py`:

```python
def _wide_series(code, source, pe, pb):
    # 200 points over ~398 days so the PE gate clears.
    pts = []
    for i in range(200):
        d = (pd.Timestamp("2025-01-01") + pd.Timedelta(days=2 * i)).date().isoformat()
        pts.append((d, pe, pb))
    return MetricSeries(code, source, tuple(pts))


def test_fund_valuation_percentile_assembles_per_metric_coverage() -> None:
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    series = {
        "600519": _wide_series("600519", "eastmoney", 18.0, 2.0),
        "000001": _wide_series("000001", "tushare", 18.0, 2.0),
    }
    res = fund_valuation_percentile(
        holdings, series, coverage_floor=0.50, pb_uses_pe_gate=False
    )
    assert res.pe.percentile is not None
    assert abs(res.pe.coverage_ratio - 0.55) < 1e-9
    assert res.pe.covered_codes == ("600519", "000001")
    assert res.pe.source_mix == ("eastmoney", "tushare")
    assert res.pb.percentile is not None  # PB clears <30 floor


def test_below_floor_yields_none_percentile_but_keeps_ratio() -> None:
    holdings = (HoldingWeight("600519", 30.0),)
    series = {"600519": _wide_series("600519", "eastmoney", 18.0, 2.0)}
    res = fund_valuation_percentile(
        holdings, series, coverage_floor=0.50, pb_uses_pe_gate=False
    )
    assert res.pe.percentile is None
    assert abs(res.pe.coverage_ratio - 0.30) < 1e-9
    assert res.pe.covered_codes == ("600519",)


def test_no_holdings_degrades_to_none() -> None:
    res = fund_valuation_percentile((), {}, coverage_floor=0.50, pb_uses_pe_gate=False)
    assert res.pe.percentile is None and res.pe.coverage_ratio == 0.0
    assert res.pb.percentile is None and res.pb.covered_codes == ()


def test_immature_pe_series_degrades_to_none_pe_but_pb_may_survive() -> None:
    # Single-date series clears the floor but fails the PE 120/180 gate; PB also
    # < 30 points → both None, but coverage ratios are still reported.
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    series = {
        "600519": MetricSeries("600519", "eastmoney", (("2026-05-30", 18.0, 2.0),)),
        "000001": MetricSeries("000001", "eastmoney", (("2026-05-30", 18.0, 2.0),)),
    }
    res = fund_valuation_percentile(
        holdings, series, coverage_floor=0.50, pb_uses_pe_gate=False
    )
    assert res.pe.percentile is None
    assert res.pb.percentile is None
    assert abs(res.pe.coverage_ratio - 0.55) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -k "assembles or below_floor or no_holdings or immature" -v`
Expected: FAIL — `fund_valuation_percentile` returns the not-yet-implemented behavior (it raises / is undefined).

- [ ] **Step 3: Implement the public entry + per-metric assembler**

Append to `src/irc/opportunity/lookthrough_valuation.py`:

```python
def _source_mix(
    series_by_code: dict[str, MetricSeries], covered_codes: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(sorted({series_by_code[c].source for c in covered_codes}))


def _metric_coverage(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, metric: _Metric, coverage_floor: float, pb_uses_pe_gate: bool,
) -> MetricCoverage:
    covered = _covered_codes_for_metric(holdings, series_by_code, metric=metric)
    ratio = _coverage_ratio(holdings, covered)
    mix = _source_mix(series_by_code, covered)
    if not _meets_floor(ratio, coverage_floor=coverage_floor):
        return MetricCoverage(None, ratio, covered, mix)
    series = _aggregate_metric_series(
        holdings, series_by_code, covered, metric=metric, coverage_floor=coverage_floor
    )
    pct = _percentile_for_metric(series, metric=metric, pb_uses_pe_gate=pb_uses_pe_gate)
    return MetricCoverage(pct, ratio, covered, mix)


def fund_valuation_percentile(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, coverage_floor: float, pb_uses_pe_gate: bool,
) -> FundValuationResult:
    """Pure public entry (§6.3). PE and PB covered sets are computed
    independently; every gap path degrades to a None percentile."""
    return FundValuationResult(
        pe=_metric_coverage(
            holdings, series_by_code,
            metric="pe", coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
        ),
        pb=_metric_coverage(
            holdings, series_by_code,
            metric="pb", coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_lookthrough_valuation.py -v`
Expected: PASS (entire file — ~20 tests).

- [ ] **Step 5: Confirm the file is < 200 lines**

Run: `wc -l src/irc/opportunity/lookthrough_valuation.py`
Expected: a count well under 200 (extract a helper if it ever exceeds).

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/lookthrough_valuation.py tests/opportunity/test_lookthrough_valuation.py
git commit -m "feat(opportunity): public fund_valuation_percentile per-metric assembly (Phase D PR1)"
```

---

## Task 10: config schema + YAML block (default OFF)

**Files:**
- Modify: `src/irc/schemas/valuation.py`
- Modify: `config/valuation_buckets.yaml`
- Test: `tests/schemas/test_valuation.py` (create if absent) + `tests/commands/test_validate_cmd.py` (smoke)

Extend the **already-registered** `ValuationBucketsConfig` (no new config file — `config_loader._FILENAME_TO_SCHEMA` is a fixed registry). The new block is **default OFF** and provides a disabled-config default so existing call sites stay valid.

- [ ] **Step 1: Write the failing tests**

Create `tests/schemas/test_valuation.py` (if `tests/schemas/__init__.py` is absent, create an empty one first):

```python
from __future__ import annotations

import pytest

from irc.schemas.valuation import ActiveFundLookthroughConfig, ValuationBucketsConfig


def test_active_fund_lookthrough_defaults_disabled() -> None:
    cfg = ActiveFundLookthroughConfig()
    assert cfg.enabled is False
    assert cfg.coverage_floor == 0.50
    assert cfg.pb_uses_pe_gate is False


def test_valuation_buckets_config_has_default_lookthrough_block() -> None:
    cfg = ValuationBucketsConfig(
        buckets=[{"max_percentile": 1.0, "buy_method": "suspend", "granularity": "n/a"}]
    )
    # Default-disabled when YAML omits the block (back-compat for existing tests).
    assert cfg.active_fund_lookthrough.enabled is False


def test_coverage_floor_must_be_a_ratio() -> None:
    with pytest.raises(ValueError):
        ActiveFundLookthroughConfig(coverage_floor=1.5)
    with pytest.raises(ValueError):
        ActiveFundLookthroughConfig(coverage_floor=0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/schemas/test_valuation.py -v`
Expected: FAIL — `cannot import name 'ActiveFundLookthroughConfig'`.

- [ ] **Step 3: Add the schema**

In `src/irc/schemas/valuation.py`, add (above `ValuationBucketsConfig`) and wire a field:

```python
class ActiveFundLookthroughConfig(FrozenModel):
    """Phase D active-fund holdings look-through valuation (spec §6.2).

    Default OFF (shadow mode). PR2 flips `enabled` to true after the gate-#5
    human floor decision. `coverage_floor` is a ratio of NAV (the covered
    A-share weight must meet this). `pb_uses_pe_gate` keeps PB on the bare <30
    floor unless flipped (§3.3)."""
    enabled: bool = False
    coverage_floor: float = Field(default=0.50, gt=0.0, le=1.0)
    pb_uses_pe_gate: bool = False
```

Then add to `ValuationBucketsConfig`:

```python
class ValuationBucketsConfig(FrozenModel):
    buckets: list[Bucket] = Field(min_length=1)
    active_fund_lookthrough: ActiveFundLookthroughConfig = Field(
        default_factory=ActiveFundLookthroughConfig
    )

    @model_validator(mode="after")
    def _ascending(self) -> "ValuationBucketsConfig":
        ...  # unchanged
```

- [ ] **Step 4: Add the YAML block (default OFF)**

In `config/valuation_buckets.yaml`, append:

```yaml
active_fund_lookthrough:
  enabled: false          # shadow mode default; PR2 flips to true
  coverage_floor: 0.50    # ratio of NAV; covered A-share weight must meet this
  pb_uses_pe_gate: false  # PB stays on the <30 floor, not 120/180 (§3.3)
```

- [ ] **Step 5: Run schema tests + config-validate to verify they pass**

Run: `uv run pytest tests/schemas/test_valuation.py -v`
Expected: PASS (3).

Run: `uv run irc config validate`
Expected: output reports `config/valuation_buckets.yaml` valid (no error). Exit code 0.

- [ ] **Step 6: Commit**

```bash
git add src/irc/schemas/valuation.py config/valuation_buckets.yaml tests/schemas/
git commit -m "feat(config): active_fund_lookthrough block (default OFF) (Phase D PR1)"
```

---

## Task 11: thread `lookthrough_cfg` through the build chain (no hidden reads)

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py` (signature only here)
- Modify: `src/irc/opportunity/inputs_build.py`
- Modify: `src/irc/commands/opportunity_cmd.py`
- Test: `tests/opportunity/test_config_threading.py` (create)

Thread the config **explicitly** (spec §6.2): `run_opportunity` → `_build_rows` → `_build_input` → `populate_inputs(..., lookthrough_cfg=...)` as a new keyword-only param **defaulting to a disabled config** so the 3 existing `_build_input` callers (`opportunity_cmd:831`, `fund_eval_cmd:109`, `narrative/analyze.py:150`) and all existing `populate_inputs` tests stay valid. NO module-level/global config reads. This task wires the *signature + passing*; the active-fund branch behavior lands in Task 14.

- [ ] **Step 1: Write the failing focused test**

Create `tests/opportunity/test_config_threading.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from irc.commands.opportunity_cmd import _build_input
from irc.fundamentals.provider import AkShareProvider
from irc.schemas.valuation import ActiveFundLookthroughConfig


def test_lookthrough_cfg_reaches_populate_inputs() -> None:
    """The config value threaded into _build_input must arrive at
    populate_inputs as the lookthrough_cfg kwarg — no global lookup (§6.2)."""
    score_row = {"instrument_id": "012345", "asset_class": "cn_equity_fund", "role": ""}
    con = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = True
    con.execute.return_value.fetchdf.return_value = fake_df
    cfg = ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.42)

    with patch("irc.opportunity.inputs_build.populate_inputs") as mock_pop:
        _build_input(
            score_row, None, None, None, 0.0, set(), con,
            provider=AkShareProvider(), lookthrough_cfg=cfg,
        )
    _, kwargs = mock_pop.call_args
    assert kwargs["lookthrough_cfg"] is cfg


def test_build_input_default_lookthrough_cfg_is_disabled() -> None:
    """Existing callers that omit lookthrough_cfg get a disabled config."""
    score_row = {"instrument_id": "012345", "asset_class": "cn_equity_fund", "role": ""}
    con = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = True
    con.execute.return_value.fetchdf.return_value = fake_df

    with patch("irc.opportunity.inputs_build.populate_inputs") as mock_pop:
        _build_input(
            score_row, None, None, None, 0.0, set(), con, provider=AkShareProvider(),
        )
    _, kwargs = mock_pop.call_args
    assert kwargs["lookthrough_cfg"].enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_config_threading.py -v`
Expected: FAIL — `_build_input() got an unexpected keyword argument 'lookthrough_cfg'`.

- [ ] **Step 3: Add the kwarg to `populate_inputs` (signature + docstring only)**

In `src/irc/opportunity/inputs_loader.py`, add the import and the keyword-only param (behavior added in Task 14):

```python
from irc.schemas.valuation import ActiveFundLookthroughConfig
```

```python
def populate_inputs(
    con: duckdb.DuckDBPyConnection,
    skeleton: OpportunityInput,
    *,
    holding_entry_date: date | None,
    broker_reports: tuple[BrokerReport, ...] = (),
    provider: CnFundamentalsProvider | None = None,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
) -> OpportunityInput:
```

> `ActiveFundLookthroughConfig()` is a frozen pydantic model — a fresh default-disabled instance per call is cheap and immutable, so it is safe as a default arg (no shared-mutable-state hazard).

- [ ] **Step 4: Thread through `_build_input`**

In `src/irc/opportunity/inputs_build.py`:
- Add the import: `from irc.schemas.valuation import ActiveFundLookthroughConfig`
- Add the keyword-only param + forward it:

```python
def _build_input(
    score_row: dict,
    instr: Instrument | None,
    holding: Holding | None,
    target_band: tuple[float, float] | None,
    portfolio_total_cny: float,
    available_venues: set[str],
    con: duckdb.DuckDBPyConnection,
    *,
    provider: CnFundamentalsProvider,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
) -> OpportunityInput:
    ...
    return populate_inputs(
        con, skeleton,
        holding_entry_date=entry_date,
        provider=provider,
        lookthrough_cfg=lookthrough_cfg,
    )
```

- [ ] **Step 5: Thread through `_build_rows` → `_build_input` and `run_opportunity` → `_build_rows`**

In `src/irc/commands/opportunity_cmd.py`:
- Add the import: `from irc.schemas.valuation import ActiveFundLookthroughConfig`
- Add a keyword-only param to `_build_rows` (default disabled):

```python
def _build_rows(
    ...
    *,
    output_date: str,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
    provider: CnFundamentalsProvider,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
) -> tuple[list[OpportunityRow], dict, dict, dict, dict, str, dict]:
```

- Forward it in the `_build_input(...)` call (around line 831):

```python
            inp = _build_input(
                score, instr, holding,
                target_band,
                portfolio_total_cny, available_venues,
                con,
                provider=provider,
                lookthrough_cfg=lookthrough_cfg,
            )
```

- Pass `bundle.valuation_buckets.active_fund_lookthrough` from `run_opportunity` (around line 1490):

```python
        rows, positions, qualities, roles, pending_verdicts, plan_hash, snapshot_cache_by_instrument = _build_rows(
            scores, instr_index, holdings, portfolio_total_cny,
            available_venues, theme_thesis, theme_reports, root,
            bundle.preferences.asset_class_targets,
            con,
            output_date=today,
            limit=limit,
            rebuild_fundamentals=rebuild_fundamentals,
            provider=cn_provider,
            lookthrough_cfg=bundle.valuation_buckets.active_fund_lookthrough,
        )
```

- [ ] **Step 6: Run the threading test + existing build-input/inputs-loader tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_config_threading.py tests/opportunity/test_build_input_fallback.py tests/opportunity/test_inputs_loader.py -v`
Expected: PASS (the threading test + all existing tests still green — defaults keep them valid).

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py src/irc/opportunity/inputs_build.py src/irc/commands/opportunity_cmd.py tests/opportunity/test_config_threading.py
git commit -m "feat(opportunity): thread lookthrough_cfg through build chain (Phase D PR1)"
```

---

## Task 12: live-gated EastMoney column-confirmation test (AUTHORED, NOT RUN — gate #4)

**Files:**
- Create: `tests/fundamentals/test_stock_valuation_live.py`

Authors the gate-#4 live test that confirms `stock_value_em` returns real rows with the `数据日期`/`PE(TTM)`/`市净率` columns and that the `(date, pe_ttm, pb)` extraction holds. Double-gated: `live_akshare` marker AND `IRC_RUN_LIVE_AKSHARE=1`. **This test is authored but MUST NOT be executed in this loop** (gate #4 is a human step).

- [ ] **Step 1: Create the live test (mirror `test_index_valuation_live.py`)**

Create `tests/fundamentals/test_stock_valuation_live.py`:

```python
"""Live verification of EastMoney stock_value_em columns (Phase D PR1, gate #4).

Double-gated: requires BOTH the `live_akshare` marker AND
`IRC_RUN_LIVE_AKSHARE=1`. Default `pytest` skips it. This is the single point
that pins the real `数据日期`/`PE(TTM)`/`市净率` column names; offline tests use
fixtures.

AUTHORED in PR1 but NOT executed by the autodev loop — column-string
confirmation against real EastMoney rows is human gate #4.

Run (human, gate #4)::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare \\
        tests/fundamentals/test_stock_valuation_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.akshare_stock_valuation import fetch_stock_valuation_history
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]


def test_fetch_stock_value_em_kweichow_moutai_live() -> None:
    """600519 (贵州茅台) returns a real history with numeric PE and PB.

    If pe_ttm/pb come back all-None, the EastMoney column labels differ from
    `akshare_stock_valuation._PE_COL` / `_PB_COL` — inspect the live frame and
    correct the constants. This is the designed pin point (spec §3.5 gate #4).
    """
    out = fetch_stock_valuation_history("600519")
    assert isinstance(out, StockValuationHistory)
    assert out.rows, "stock_value_em returned no parseable rows"
    latest = out.rows[-1]
    assert latest.pe_ttm is not None, (
        "EastMoney PE(TTM) column not matched by _PE_COL — inspect the live "
        "frame and correct the constant."
    )
    assert latest.pb is not None, (
        "EastMoney 市净率 column not matched by _PB_COL — inspect the live frame."
    )
    assert latest.pe_ttm > 0 and latest.pb > 0
    assert latest.dividend_yield is None  # EastMoney exposes no per-stock div yield
    print(f"\n  ✓ 600519 live: {len(out.rows)} rows, "
          f"latest pe={latest.pe_ttm} pb={latest.pb}")
```

- [ ] **Step 2: Verify the test is COLLECTABLE but SKIPPED (do NOT run live)**

Run: `uv run pytest tests/fundamentals/test_stock_valuation_live.py -v`
Expected: `1 skipped` (the `IRC_RUN_LIVE_AKSHARE` env var is unset → skipif fires). **DO NOT** set `IRC_RUN_LIVE_AKSHARE=1` — that is gate #4 (human).

- [ ] **Step 3: Verify strict-marker registration (no marker error)**

Run: `uv run pytest tests/fundamentals/test_stock_valuation_live.py --collect-only -q`
Expected: collects 1 item with no `--strict-markers` error (the `live_akshare` marker is already registered in `pyproject.toml`).

- [ ] **Step 4: Commit**

```bash
git add tests/fundamentals/test_stock_valuation_live.py
git commit -m "test(fundamentals): authored live stock_value_em column test (gate #4, not run) (Phase D PR1)"
```

---

## Task 13: live-gated Tushare `daily_basic` test (AUTHORED, NOT RUN — gate #4)

**Files:**
- Create: `tests/fundamentals/test_stock_valuation_tushare_live.py`

Parallel live-gated test for the Tushare fallback when a token is present. Triple-gated (mirror `test_tushare_provider_live.py`): `live_tushare` marker, `IRC_RUN_LIVE_TUSHARE=1`, AND a real `TUSHARE_TOKEN`. Authored, NOT run.

- [ ] **Step 1: Create the live Tushare test**

Create `tests/fundamentals/test_stock_valuation_tushare_live.py`:

```python
"""Live verification of Tushare daily_basic columns (Phase D PR1, gate #4).

TRIPLE-gated: requires the `live_tushare` marker, `IRC_RUN_LIVE_TUSHARE=1`, AND
a real TUSHARE_TOKEN in the environment. Default `pytest` skips it.

AUTHORED in PR1 but NOT executed by the autodev loop (gate #4 is human).

Run (human, gate #4)::

    IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \\
        tests/fundamentals/test_stock_valuation_tushare_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.stock_valuation_types import StockValuationHistory
from irc.fundamentals.tushare_stock_valuation import (
    fetch_stock_valuation_history_tushare,
)

_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
_RUN = os.environ.get("IRC_RUN_LIVE_TUSHARE") == "1"
pytestmark = [
    pytest.mark.live_tushare,
    pytest.mark.skipif(
        not (_RUN and _TOKEN),
        reason="set IRC_RUN_LIVE_TUSHARE=1 and TUSHARE_TOKEN to run live Tushare tests",
    ),
]


def test_fetch_daily_basic_kweichow_moutai_live() -> None:
    """600519 returns a real history; pe_ttm/pb numeric. Pins daily_basic cols."""
    out = fetch_stock_valuation_history_tushare("600519", token=_TOKEN)
    assert isinstance(out, StockValuationHistory)
    assert out.rows, "daily_basic returned no parseable rows"
    latest = out.rows[-1]
    assert latest.pe_ttm is not None and latest.pe_ttm > 0
    assert latest.pb is not None and latest.pb > 0
    print(f"\n  ✓ 600519 tushare live: {len(out.rows)} rows, "
          f"pe={latest.pe_ttm} pb={latest.pb} dv={latest.dividend_yield}")
```

- [ ] **Step 2: Verify SKIPPED (do NOT run live)**

Run: `uv run pytest tests/fundamentals/test_stock_valuation_tushare_live.py -v`
Expected: `1 skipped`. **DO NOT** set the live env vars.

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_stock_valuation_tushare_live.py
git commit -m "test(fundamentals): authored live Tushare daily_basic test (gate #4, not run) (Phase D PR1)"
```

---

## Task 14: `stock_valuation_history` ingestor (atomic upsert, failure-isolating)

**Files:**
- Create: `src/irc/data/stock_valuation_ingestor.py`
- Test: `tests/data/test_stock_valuation_ingestor.py`

Atomic `INSERT OR REPLACE` into `stock_valuation_history`, `_source` per row, BEGIN/COMMIT/ROLLBACK (mirror `index_valuation_ingestor.py`). Plus a per-stock staleness gate (`is_stock_valuation_stale`, mirror `fund_holdings_ingestor.is_stale`) and a failure-isolating `ingest_one`/`ingest_many` (mirror `ingest_many` — never raise). The fetch is hybrid: EastMoney primary, Tushare on miss — injected as a `_FetchFn` for testability (the command wires the real EastMoney→Tushare chain in Task 15).

- [ ] **Step 1: Write the failing tests**

Create `tests/data/test_stock_valuation_ingestor.py`:

```python
from __future__ import annotations

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.data.stock_valuation_ingestor import (
    ingest_stock_valuation_history,
    is_stock_valuation_stale,
)
from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "sv.duckdb"))
    ensure_schema(con)
    return con


def _hist(code, source="eastmoney"):
    return StockValuationHistory(
        stock_code=code,
        rows=(
            StockValuationPoint("2026-05-28", 18.0, 2.0, None),
            StockValuationPoint("2026-05-30", 18.2, 2.1, None),
        ),
    ), source


def test_ingest_writes_one_row_per_date_with_source(tmp_path) -> None:
    con = _con(tmp_path)
    written = ingest_stock_valuation_history(
        con, ("600519",),
        fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    assert written == 2
    rows = con.execute(
        "SELECT stock_code, CAST(date AS VARCHAR), pe_ttm, pb, _source "
        "FROM stock_valuation_history ORDER BY date"
    ).fetchall()
    assert rows[0] == ("600519", "2026-05-28", 18.0, 2.0, "eastmoney")
    assert rows[1][4] == "eastmoney"
    con.close()


def test_ingest_records_per_row_source_from_fetch(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("000001",),
        fetch=lambda code: _hist(code, source="tushare"),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    src = con.execute(
        "SELECT DISTINCT _source FROM stock_valuation_history WHERE stock_code='000001'"
    ).fetchone()[0]
    assert src == "tushare"
    con.close()


def test_ingest_skips_none_history_without_raising(tmp_path) -> None:
    con = _con(tmp_path)
    written = ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: None,
        now_iso="2026-05-31T00:00:00+08:00",
    )
    assert written == 0
    con.close()


def test_ingest_is_idempotent_upsert(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-06-01T00:00:00+08:00",
    )
    n = con.execute(
        "SELECT COUNT(*) FROM stock_valuation_history WHERE stock_code='600519'"
    ).fetchone()[0]
    assert n == 2
    con.close()


def test_is_stale_true_when_no_rows(tmp_path) -> None:
    con = _con(tmp_path)
    assert is_stock_valuation_stale(
        con, "600519", today_iso="2026-05-31", threshold_days=30
    ) is True
    con.close()


def test_is_stale_false_when_fresh(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    # latest date 2026-05-30; today 2026-05-31 → age 1 day < 30 → fresh.
    assert is_stock_valuation_stale(
        con, "600519", today_iso="2026-05-31", threshold_days=30
    ) is False
    con.close()


def test_is_stale_true_when_older_than_threshold(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    # latest 2026-05-30; today 2026-08-30 → age ~92 days > 30 → stale.
    assert is_stock_valuation_stale(
        con, "600519", today_iso="2026-08-30", threshold_days=30
    ) is True
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_stock_valuation_ingestor.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.data.stock_valuation_ingestor`.

- [ ] **Step 3: Create the ingestor (mirror `index_valuation_ingestor.py` + `fund_holdings_ingestor.is_stale`)**

Create `src/irc/data/stock_valuation_ingestor.py`:

```python
"""Ingest-stage writer for `stock_valuation_history` (Phase D PR1).

Effect at the edge: upserts each A-share's full PE/PB series into
`stock_valuation_history`, recording `_source` per row. Never fatal at the
batch boundary — a `None` history (miss / adapter failure / empty frame) is
skipped, not raised. Mirrors `index_valuation_ingestor.py`. This cached table
is the ONLY source the opportunity stage reads for per-stock valuation
(no live fetch there — spec §3.7).
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_FetchFn = Callable[[str], StockValuationHistory | None]

_UPSERT_SQL = """
INSERT OR REPLACE INTO stock_valuation_history
    (stock_code, date, pe_ttm, pb, dividend_yield, _ingested_at, _source, _raw_ref)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def is_stock_valuation_stale(
    con: duckdb.DuckDBPyConnection,
    stock_code: str,
    *, today_iso: str, threshold_days: int = 30,
) -> bool:
    """True iff stock_valuation_history has no rows for stock_code OR the latest
    date is older than (today_iso - threshold_days) days. Mirrors
    fund_holdings_ingestor.is_stale. Pure DuckDB read."""
    result = con.execute(
        "SELECT MAX(date) FROM stock_valuation_history WHERE stock_code = ?",
        [stock_code],
    ).fetchone()
    if result is None or result[0] is None:
        return True
    age = (date.fromisoformat(today_iso) - result[0]).days
    return age > threshold_days


def ingest_stock_valuation_history(
    con: duckdb.DuckDBPyConnection,
    stock_codes: tuple[str, ...],
    *, fetch: _FetchFn, now_iso: str,
) -> int:
    """Upsert PE/PB history for each stock_code, recording the per-row _source.
    `fetch` returns (history, source) where source ∈ {eastmoney, tushare}, or
    None on a miss. Returns rows written. Atomic at the batch boundary."""
    params: list[list] = []
    for code in stock_codes:
        result = fetch(code)
        if result is None:
            continue
        hist, source = result
        for pt in hist.rows:
            params.append([
                code, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, source,
                build_ref_id(source, "stock_valuation_history", code, pt.date_iso),
            ])
    if params:
        con.execute("BEGIN")
        try:
            con.executemany(_UPSERT_SQL, params)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return len(params)
```

> Note: the test `fetch` lambdas return `(hist, source)`; align the `_FetchFn` alias to `Callable[[str], tuple[StockValuationHistory, str] | None]`. Update the type alias and the `for` loop to unpack accordingly (the body above already unpacks `hist, source = result`). Adjust the alias:
>
> ```python
> _FetchFn = Callable[[str], "tuple[StockValuationHistory, str] | None"]
> ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_stock_valuation_ingestor.py -v`
Expected: PASS (7).

- [ ] **Step 5: Commit**

```bash
git add src/irc/data/stock_valuation_ingestor.py tests/data/test_stock_valuation_ingestor.py
git commit -m "feat(data): stock_valuation_history ingestor (atomic upsert + staleness) (Phase D PR1)"
```

---

## Task 15: `irc fundamentals stock-valuation` command

**Files:**
- Modify: `src/irc/commands/fundamentals_cmd.py`
- Modify: `src/irc/cli.py`
- Test: `tests/commands/test_fundamentals_cmd.py`

`run_stock_valuation_refresh(repo_root, *, force=False, threshold_days=30) -> int`. Discovery = `SELECT DISTINCT holding_ticker FROM fund_holdings` filtered to A-share shape `^\d{6}$` (no surrounding whitespace). Per-stock staleness via `is_stock_valuation_stale`; `--force` refetches all. Per-stock failure isolation (mirror `ingest_many` — never raise; return 0 on a completed run even with gaps; non-zero only on structural error e.g. cannot open DuckDB). EastMoney primary, Tushare on miss. Effects confined here + the ingestor. The fetch chain reads the `.env` token via `_read_tushare_token` at the edge.

- [ ] **Step 1: Write the failing tests**

Append to `tests/commands/test_fundamentals_cmd.py`:

```python
import re

import duckdb

from irc.commands.fundamentals_cmd import (
    _discover_ashare_codes,
    run_stock_valuation_refresh,
)
from irc.data.duckdb_helper import ensure_schema


def _seed_holdings(db_path):
    con = duckdb.connect(str(db_path))
    ensure_schema(con)
    rows = [
        ("F1", "2026-03-31", "600519", "贵州茅台", 30.0),
        ("F1", "2026-03-31", "000001", "平安银行", 20.0),
        ("F1", "2026-03-31", "00700", "腾讯", 10.0),     # HK 5-digit → skipped
        ("F1", "2026-03-31", "AAPL", "Apple", 5.0),       # US alpha → skipped
        ("F2", "2026-03-31", "600519", "贵州茅台", 25.0),  # dup A-share
    ]
    con.executemany(
        "INSERT INTO fund_holdings VALUES (?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'r')",
        rows,
    )
    con.close()


def test_discover_ashare_codes_filters_to_six_digit_and_dedupes(tmp_path) -> None:
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)
    con = duckdb.connect(str(db))
    codes = _discover_ashare_codes(con)
    con.close()
    assert codes == ("000001", "600519")  # sorted, A-share only, deduped
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)


def test_run_returns_zero_on_completed_run_even_with_per_stock_misses(
    tmp_path, monkeypatch
) -> None:
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)
    # All fetches miss (None) → run still completes → rc 0, no rows written.
    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd._fetch_stock_valuation",
        lambda code, token: None,
    )
    rc = run_stock_valuation_refresh(str(tmp_path), force=True)
    assert rc == 0


def test_run_writes_rows_for_discovered_ashares(tmp_path, monkeypatch) -> None:
    from irc.fundamentals.stock_valuation_types import (
        StockValuationHistory, StockValuationPoint,
    )
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)

    def _fake(code, token):
        return (
            StockValuationHistory(code, (StockValuationPoint("2026-05-30", 18.0, 2.0, None),)),
            "eastmoney",
        )

    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd._fetch_stock_valuation", _fake
    )
    rc = run_stock_valuation_refresh(str(tmp_path), force=True)
    assert rc == 0
    con = duckdb.connect(str(db))
    codes = {
        r[0] for r in con.execute(
            "SELECT DISTINCT stock_code FROM stock_valuation_history"
        ).fetchall()
    }
    con.close()
    assert codes == {"000001", "600519"}


def test_eastmoney_miss_falls_back_to_tushare(tmp_path, monkeypatch) -> None:
    from irc.fundamentals.stock_valuation_types import (
        StockValuationHistory, StockValuationPoint,
    )
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)

    calls = {"em": 0, "ts": 0}

    def _fake_em(code):
        calls["em"] += 1
        return None  # always miss

    def _fake_ts(code, *, token):
        calls["ts"] += 1
        return StockValuationHistory(code, (StockValuationPoint("2026-05-30", 18.0, 2.0, None),))

    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd.fetch_stock_valuation_history", _fake_em
    )
    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd.fetch_stock_valuation_history_tushare", _fake_ts
    )
    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd._read_tushare_token", lambda: "tok"
    )
    rc = run_stock_valuation_refresh(str(tmp_path), force=True)
    assert rc == 0
    assert calls["em"] >= 1 and calls["ts"] >= 1
    con = duckdb.connect(str(db))
    src = con.execute(
        "SELECT DISTINCT _source FROM stock_valuation_history"
    ).fetchall()
    con.close()
    assert ("tushare",) in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_fundamentals_cmd.py -k "ashare or stock_valuation or eastmoney_miss" -v`
Expected: FAIL — `cannot import name '_discover_ashare_codes'` / `run_stock_valuation_refresh`.

- [ ] **Step 3: Add the command function to `fundamentals_cmd.py`**

Append to `src/irc/commands/fundamentals_cmd.py` (note the `_fetch_stock_valuation` indirection seam — the EastMoney→Tushare chain — which the tests monkeypatch):

```python
import logging
import re
from datetime import datetime, timedelta, timezone

from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.stock_valuation_ingestor import (
    ingest_stock_valuation_history,
    is_stock_valuation_stale,
)
from irc.fundamentals.akshare_stock_valuation import fetch_stock_valuation_history
from irc.fundamentals.provider import _read_tushare_token
from irc.fundamentals.stock_valuation_types import StockValuationHistory
from irc.fundamentals.tushare_stock_valuation import (
    fetch_stock_valuation_history_tushare,
)

_log = logging.getLogger(__name__)
_ASHARE_RE = re.compile(r"^\d{6}$")  # 6-digit, no surrounding whitespace (§6.1)


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _china_today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _discover_ashare_codes(con) -> tuple[str, ...]:
    """DISTINCT holding_ticker from fund_holdings filtered to A-share shape
    `^\\d{6}$` (no surrounding whitespace), sorted + deduped (§6.1)."""
    rows = con.execute(
        "SELECT DISTINCT holding_ticker FROM fund_holdings"
    ).fetchall()
    codes = {
        r[0] for r in rows
        if r[0] is not None and _ASHARE_RE.fullmatch(r[0])
    }
    return tuple(sorted(codes))


def _fetch_stock_valuation(
    code: str, token: str
) -> tuple[StockValuationHistory, str] | None:
    """EastMoney primary; Tushare on miss. Returns (history, source) or None."""
    hist = fetch_stock_valuation_history(code)
    if hist is not None:
        return hist, "eastmoney"
    ts_hist = fetch_stock_valuation_history_tushare(code, token=token)
    if ts_hist is not None:
        return ts_hist, "tushare"
    return None


def run_stock_valuation_refresh(
    repo_root: str, *, force: bool = False, threshold_days: int = 30
) -> int:
    """Refresh per-stock PE/PB history for every distinct A-share in
    fund_holdings. Per-stock failure-isolating: returns 0 on a completed run
    (even with per-stock misses), non-zero only on a structural error.
    Heavy / own cadence — NOT part of `irc run` (spec §3.7)."""
    root = Path(repo_root)
    db_path = root / "data" / "local.duckdb"
    try:
        con = connect(db_path)
        ensure_schema(con)
    except Exception as exc:  # structural error → non-zero
        print(f"ERROR: cannot open DuckDB at {db_path}: {exc}")
        return 1
    try:
        codes = _discover_ashare_codes(con)
        token = _read_tushare_token()
        today = _china_today()
        now = _now_iso()
        targets = tuple(
            c for c in codes
            if force or is_stock_valuation_stale(
                con, c, today_iso=today, threshold_days=threshold_days
            )
        )
        written = 0
        for code in targets:
            try:
                written += ingest_stock_valuation_history(
                    con, (code,),
                    fetch=lambda c, _t=token: _fetch_stock_valuation(c, _t),
                    now_iso=now,
                )
            except Exception as exc:  # per-stock isolation — never abort the run
                _log.warning("stock-valuation refresh failed for %s: %s: %s",
                             code, type(exc).__name__, exc)
        print(
            f"stock-valuation refresh OK: {len(targets)}/{len(codes)} A-shares "
            f"considered, {written} rows written."
        )
        return 0
    finally:
        con.close()
```

- [ ] **Step 4: Register the Click command in `cli.py`**

In `src/irc/cli.py`, add after `fundamentals_snapshot` (around line 243):

```python
@fundamentals.command("stock-valuation", help="Refresh cached per-stock PE/PB history for A-share holdings (heavy; own cadence).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--force", is_flag=True, default=False, help="Refetch every A-share, ignoring staleness.")
@click.option("--threshold-days", type=int, default=30, show_default=True, help="Skip stocks fresh within this many days.")
def fundamentals_stock_valuation(repo_root: str, force: bool, threshold_days: int) -> None:
    from irc.commands.fundamentals_cmd import run_stock_valuation_refresh
    rc = run_stock_valuation_refresh(
        repo_root=repo_root, force=force, threshold_days=threshold_days
    )
    raise SystemExit(rc)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_fundamentals_cmd.py -v`
Expected: PASS (existing snapshot tests + the 5 new ones).

- [ ] **Step 6: Verify the command help (no network)**

Run: `uv run irc fundamentals stock-valuation --help`
Expected: usage text listing `--repo-root`, `--force`, `--threshold-days`. Exit code 0.

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/fundamentals_cmd.py src/irc/cli.py tests/commands/test_fundamentals_cmd.py
git commit -m "feat(fundamentals): irc fundamentals stock-valuation command (Phase D PR1)"
```

---

## Task 16: `inputs_loader` active-fund branch (flag-gated slot population)

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py`
- Test: `tests/opportunity/test_inputs_loader_lookthrough.py` (create)

Add an active-fund branch (`asset_class == "cn_equity_fund"`): load latest-quarter holdings (from `fund_holdings`) + per-code series (from `stock_valuation_history`), build the `HoldingWeight`/`MetricSeries` inputs, call `fund_valuation_percentile`, and **iff `lookthrough_cfg.enabled`** write `valuation_percentile_fundamental` / `_pb`. Flag OFF ⇒ leave `None` (NAV fallback, byte-identical). Index path untouched. No live fetch (R3). All reads are pure DuckDB queries confined to small helpers.

> Key invariant: when the flag is OFF, the branch must NOT even compute differently — it must leave the slots exactly as the index path set them (which for an active fund — no `tracked_index` — is `None`). So: compute the result only when `enabled` (no wasted work AND guaranteed byte-identical).

- [ ] **Step 1: Write the failing tests (flag off vs on; latest-quarter holdings; index path unchanged)**

Create `tests/opportunity/test_inputs_loader_lookthrough.py`:

```python
from __future__ import annotations

from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.valuation import ActiveFundLookthroughConfig


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt.duckdb"))
    ensure_schema(con)
    return con


def _seed_active_fund(con):
    # One active fund "AF1" holding 600519 (60%) — clears a 0.50 floor.
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 60.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    # 600519: 200 PE/PB points over ~398 days → clears the 120/180 gate.
    base = date(2025, 1, 1)
    rows = []
    for i in range(200):
        d = date.fromordinal(base.toordinal() + 2 * i)
        rows.append(("600519", d, 18.0 + i * 0.01, 2.0, None,
                     "2026-05-15 00:00:00", "eastmoney", "r"))
    con.executemany(
        "INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows
    )


def _skeleton():
    return OpportunityInput(
        instrument_id="AF1",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        theme=None,
        tracked_index=None,
        name_cn="主动基金",
        role="",
        is_holding=False,
        portfolio_weight=None,
        target_band_low=None,
        target_band_high=None,
        venue_compatible=True,
    )


def test_flag_off_leaves_fundamental_percentile_none(tmp_path) -> None:
    con = _con(tmp_path)
    _seed_active_fund(con)
    out = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    assert out.valuation_percentile_fundamental is None
    assert out.valuation_percentile_fundamental_pb is None
    con.close()


def test_flag_on_populates_fundamental_percentile(tmp_path) -> None:
    con = _con(tmp_path)
    _seed_active_fund(con)
    out = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.50),
    )
    assert out.valuation_percentile_fundamental is not None
    assert 0.0 <= out.valuation_percentile_fundamental <= 1.0
    # PB clears the <30 floor (200 points) → populated too.
    assert out.valuation_percentile_fundamental_pb is not None
    con.close()


def test_flag_on_below_floor_leaves_none(tmp_path) -> None:
    con = _con(tmp_path)
    # AF1 holds only 30% of 600519 → coverage 0.30 < 0.50 floor → None.
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 30.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    base = date(2025, 1, 1)
    rows = [("600519", date.fromordinal(base.toordinal() + 2 * i), 18.0, 2.0, None,
             "2026-05-15 00:00:00", "eastmoney", "r") for i in range(200)]
    con.executemany("INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows)
    out = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.50),
    )
    assert out.valuation_percentile_fundamental is None
    con.close()


def test_index_fund_path_unchanged_by_lookthrough_branch(tmp_path) -> None:
    # An index-tracking ETF must keep using the index path regardless of the
    # active-fund branch / flag. With no index_valuation_history rows it stays
    # None (the index path's all-None dormancy) — proving the branch did not
    # intercept a non-cn_equity_fund row.
    con = _con(tmp_path)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        theme=None, tracked_index="csi300", name_cn="沪深300ETF", role="",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )
    out = populate_inputs(
        con, skeleton, holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True),
    )
    assert out.valuation_percentile_fundamental is None  # no index rows cached
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_inputs_loader_lookthrough.py -v`
Expected: FAIL — flag-on test fails (slot stays None because the branch isn't wired yet).

- [ ] **Step 3: Add the look-through helpers + branch to `inputs_loader.py`**

In `src/irc/opportunity/inputs_loader.py`, add imports:

```python
from irc.opportunity.lookthrough_valuation import (
    HoldingWeight,
    MetricSeries,
    fund_valuation_percentile,
)
```

Add the pure-read helpers:

```python
def _latest_quarter_holdings(
    con: duckdb.DuckDBPyConnection, instrument_id: str
) -> tuple[HoldingWeight, ...]:
    """Top-N holdings of the latest report_date for an active fund."""
    df = con.execute(
        "SELECT holding_ticker, weight_pct FROM fund_holdings "
        "WHERE instrument_id = ? AND report_date = ("
        "  SELECT MAX(report_date) FROM fund_holdings WHERE instrument_id = ?"
        ")",
        [instrument_id, instrument_id],
    ).fetchdf()
    if df.empty:
        return ()
    return tuple(
        HoldingWeight(code=str(row["holding_ticker"]), weight_pct=float(row["weight_pct"]))
        for _, row in df.iterrows()
    )


def _stock_series_by_code(
    con: duckdb.DuckDBPyConnection, codes: tuple[str, ...]
) -> dict[str, MetricSeries]:
    """Per-code (date_iso, pe_ttm, pb) series + source from
    stock_valuation_history. Codes with no cached rows are absent from the map."""
    out: dict[str, MetricSeries] = {}
    for code in codes:
        df = con.execute(
            "SELECT CAST(date AS VARCHAR) AS d, pe_ttm, pb, _source "
            "FROM stock_valuation_history WHERE stock_code = ? ORDER BY date",
            [code],
        ).fetchdf()
        if df.empty:
            continue
        points = tuple(
            (str(row["d"]), _none_if_na(row["pe_ttm"]), _none_if_na(row["pb"]))
            for _, row in df.iterrows()
        )
        source = str(df.iloc[0]["_source"])
        out[code] = MetricSeries(code=code, source=source, points=points)
    return out


def _active_fund_fundamental_percentiles(
    con: duckdb.DuckDBPyConnection,
    instrument_id: str,
    cfg: ActiveFundLookthroughConfig,
) -> tuple[float | None, float | None]:
    """Flag-gated active-fund look-through (spec §6.5). Returns (pe_pct, pb_pct).
    When cfg.enabled is False, returns (None, None) WITHOUT computing — so the
    flag-off path is byte-identical to today (NAV fallback). No live fetch."""
    if not cfg.enabled:
        return None, None
    holdings = _latest_quarter_holdings(con, instrument_id)
    if not holdings:
        return None, None
    series = _stock_series_by_code(con, tuple(h.code for h in holdings))
    result = fund_valuation_percentile(
        holdings, series,
        coverage_floor=cfg.coverage_floor, pb_uses_pe_gate=cfg.pb_uses_pe_gate,
    )
    return result.pe.percentile, result.pb.percentile
```

Then, in `populate_inputs`, after the existing `_index_valuation_metrics` call (around line 243), add the active-fund override:

```python
    pe_ttm, pb, dividend_yield, fund_pct, fund_pct_pb = _index_valuation_metrics(
        con, skeleton.tracked_index
    )
    # Phase D: active CN equity funds (no tracked_index) get their fundamental
    # percentile from holdings look-through — flag-gated so flag-off is
    # byte-identical (NAV fallback). The index path above is untouched.
    if skeleton.asset_class == "cn_equity_fund":
        af_pe, af_pb = _active_fund_fundamental_percentiles(
            con, skeleton.instrument_id, lookthrough_cfg
        )
        fund_pct = af_pe
        fund_pct_pb = af_pb
```

> Note: an active fund has no `tracked_index`, so `_index_valuation_metrics` already returns `(None, None, None, None, None)` for it; the override only ever replaces `None` with a value (or leaves `None`). `pe_ttm`/`pb`/`dividend_yield` (the bare latest scalars) stay `None` for active funds — the spec scope populates only the percentile slots, mirroring the index path's percentile-not-scalar grounding.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_inputs_loader_lookthrough.py tests/opportunity/test_inputs_loader.py -v`
Expected: PASS (new look-through tests + all existing inputs_loader tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py tests/opportunity/test_inputs_loader_lookthrough.py
git commit -m "feat(opportunity): flag-gated active-fund look-through branch in inputs_loader (Phase D PR1)"
```

---

## Task 17: flag-off byte-identical regression (dormancy lock) + invariants

**Files:**
- Test: `tests/commands/test_opportunity_cmd_lookthrough_dormancy.py` (create)

Prove the flag-off path produces byte-identical active-fund opportunity outputs (the dormancy lock, spec §9 "Flag-off byte-identical regression (P1)") and that the H3 / SAME-3 invariants are unaffected. The cleanest deterministic assertion at the unit level: with the flag OFF, `populate_inputs` on a `cn_equity_fund` skeleton — even with seeded `stock_valuation_history` — yields the **same** `OpportunityInput` as one produced with no look-through data at all. (A full end-to-end fixture run is heavier than needed; the dormancy property is fully captured at the `populate_inputs` boundary, which is the only place the flag changes behavior.)

- [ ] **Step 1: Write the regression test**

Create `tests/commands/test_opportunity_cmd_lookthrough_dormancy.py`:

```python
from __future__ import annotations

import dataclasses
from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.valuation import ActiveFundLookthroughConfig


def _skeleton():
    return OpportunityInput(
        instrument_id="AF1", asset_class="cn_equity_fund", market="cn_off_exchange",
        theme=None, tracked_index=None, name_cn="主动基金", role="",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )


def _con_with_lookthrough_data(tmp_path):
    con = duckdb.connect(str(tmp_path / "dorm.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 60.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    base = date(2025, 1, 1)
    rows = [("600519", date.fromordinal(base.toordinal() + 2 * i), 18.0, 2.0, None,
             "2026-05-15 00:00:00", "eastmoney", "r") for i in range(200)]
    con.executemany("INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows)
    return con


def test_flag_off_output_byte_identical_to_no_lookthrough_data(tmp_path) -> None:
    """Dormancy lock: with the flag OFF, the OpportunityInput is identical whether
    or not stock_valuation_history is populated — i.e. the look-through machinery
    is truly inert in shadow mode."""
    con_with = _con_with_lookthrough_data(tmp_path)
    out_with_data = populate_inputs(
        con_with, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    con_with.close()

    con_empty = duckdb.connect(str(tmp_path / "empty.duckdb"))
    ensure_schema(con_empty)
    out_no_data = populate_inputs(
        con_empty, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    con_empty.close()

    assert dataclasses.asdict(out_with_data) == dataclasses.asdict(out_no_data)
    assert out_with_data.valuation_percentile_fundamental is None


def test_flag_off_matches_default_disabled_config(tmp_path) -> None:
    """Calling populate_inputs WITHOUT lookthrough_cfg (default-disabled) yields
    the same result as the explicit enabled=False config — back-compat lock."""
    con = _con_with_lookthrough_data(tmp_path)
    explicit_off = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    default_arg = populate_inputs(con, _skeleton(), holding_entry_date=None)
    con.close()
    assert dataclasses.asdict(explicit_off) == dataclasses.asdict(default_arg)
```

- [ ] **Step 2: Run tests to verify they pass (the branch from Task 16 already makes this green)**

Run: `uv run pytest tests/commands/test_opportunity_cmd_lookthrough_dormancy.py -v`
Expected: PASS (2). If the flag-off path computed anything different, the byte-identical assertion would fail — this is the guard.

- [ ] **Step 3: Run the H3 + SAME-3 invariant suites to confirm they are unaffected**

Run: `uv run pytest tests/commands/test_opportunity_cmd_h3_invariant.py -v`
Expected: PASS (unchanged — the flag-off default keeps these byte-identical; `valuation_percentile_fundamental[_pb]` carry no `ThesisEvidence` so SAME-3/H3 are structurally untouched per spec §7).

- [ ] **Step 4: Commit**

```bash
git add tests/commands/test_opportunity_cmd_lookthrough_dormancy.py
git commit -m "test(opportunity): flag-off dormancy lock + invariants intact (Phase D PR1)"
```

---

## Task 18: diff report core (pure builder)

**Files:**
- Create: `src/irc/opportunity/lookthrough_diff_report.py`
- Test: `tests/opportunity/test_lookthrough_diff_report.py`

Pure builder (spec §8). Per active fund: would-flip band (NAV-derived `valuation_state` vs PE-derived) + Δpercentile (PE vs NAV); **per-metric** covered-weight ratio + source mix (PE and PB separately); current-basket caveat; coverage-floor sensitivity table at `0.40 / 0.50 / 0.60`. **Computes regardless of `enabled`** (independent of the flag). The band classification reuses the existing `_VALUATION_BANDS` boundaries from `opportunity/states.py` (cheap `<.20`, reasonable_low `<.40`, fair `<.70`, expensive `<.90`, very_expensive `≥.90`) — import a band-label helper rather than re-deriving thresholds.

> Spec §8 says "would-flip band (NAV-derived `valuation_state` vs PE-derived)". The report computes the band label each percentile lands in and flags `would_flip = (nav_band != pe_band)`. The full `classify_valuation` verdict depends on many inputs; for the diff report's flip indicator, the band of the percentile is the load-bearing comparison (matches the divergence detector's `_band(f) != _band(n)` semantics, CONTEXT.md `valuation_divergence_code`).

- [ ] **Step 1: Confirm a reusable band-label helper exists (read first)**

Run: `grep -n "_VALUATION_BANDS\|def _band\b" src/irc/opportunity/states.py`
Expected: shows `_VALUATION_BANDS` and a `_band(...)` (or equivalent) used by `valuation_divergence_code`. If `_band` is private and importable, reuse it; if not, replicate the 5-boundary mapping in a small local `_band_label(pct)` helper inside the diff-report module (cite that it mirrors `_VALUATION_BANDS`). Record the chosen approach in the module docstring.

- [ ] **Step 2: Write the failing tests**

Create `tests/opportunity/test_lookthrough_diff_report.py`:

```python
from __future__ import annotations

from irc.opportunity.lookthrough_diff_report import (
    FundDiffRow,
    build_floor_sensitivity,
    build_fund_diff_row,
    render_diff_report,
)
from irc.opportunity.lookthrough_valuation import FundValuationResult, MetricCoverage


def _result(pe_pct, pb_pct):
    return FundValuationResult(
        pe=MetricCoverage(pe_pct, 0.60, ("600519",), ("eastmoney",)),
        pb=MetricCoverage(pb_pct, 0.55, ("600519",), ("eastmoney", "tushare")),
    )


def test_build_fund_diff_row_flags_band_flip_and_delta() -> None:
    # NAV percentile 0.15 (cheap band) vs PE percentile 0.50 (fair band) → flip.
    row = build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.15, result=_result(0.50, 0.45),
    )
    assert isinstance(row, FundDiffRow)
    assert row.would_flip is True
    assert abs(row.delta_percentile - 0.35) < 1e-9
    assert row.pe_coverage_ratio == 0.60
    assert row.pb_source_mix == ("eastmoney", "tushare")


def test_build_fund_diff_row_no_flip_same_band() -> None:
    row = build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.50, result=_result(0.55, None),
    )
    assert row.would_flip is False


def test_build_fund_diff_row_handles_none_pe_percentile() -> None:
    # PE None (below floor / immature) → no flip, delta None, band reported as "—".
    row = build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.20, result=_result(None, None),
    )
    assert row.would_flip is False
    assert row.delta_percentile is None


def test_floor_sensitivity_counts_grounded_funds_per_floor() -> None:
    # Three funds with coverage ratios 0.42 / 0.55 / 0.65.
    coverage_ratios = [0.42, 0.55, 0.65]
    table = build_floor_sensitivity(coverage_ratios, floors=(0.40, 0.50, 0.60))
    assert table[0.40] == 3  # all meet 0.40
    assert table[0.50] == 2  # 0.55, 0.65
    assert table[0.60] == 1  # 0.65 only


def test_render_diff_report_includes_caveat_and_table() -> None:
    rows = [build_fund_diff_row("AF1", "主动基金", 0.15, _result(0.50, 0.45))]
    text = render_diff_report(rows, build_floor_sensitivity([0.60], floors=(0.40, 0.50, 0.60)))
    assert "current-basket" in text.lower() or "当前持仓" in text
    assert "0.40" in text and "0.50" in text and "0.60" in text
    assert "AF1" in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough_diff_report.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.opportunity.lookthrough_diff_report`.

- [ ] **Step 4: Implement the pure builder**

Create `src/irc/opportunity/lookthrough_diff_report.py`:

```python
"""Pure diff-report builder for the Phase D look-through (spec §8, gate-#5 artifact).

Per active fund: would-flip band (NAV-derived vs PE-derived valuation band),
Δpercentile (PE − NAV), per-metric covered-weight ratio + source mix (PE and PB
SEPARATELY, since their covered sets can differ), the current-basket caveat, and
a coverage-floor sensitivity table at 0.40/0.50/0.60. Computes regardless of the
`enabled` flag. NO I/O — the command (lookthrough_diff_cmd) supplies cached data.

Band boundaries mirror opportunity/states._VALUATION_BANDS (cheap <.20 ·
reasonable_low <.40 · fair <.70 · expensive <.90 · very_expensive ≥.90), matching
the divergence detector's band semantics (CONTEXT.md valuation_divergence_code).
"""
from __future__ import annotations

from dataclasses import dataclass

from irc.opportunity.lookthrough_valuation import FundValuationResult

_CAVEAT_CN = (
    "注意：本估值为「当前持仓 × 历史个股 PE」构造的 current-basket 序列，"
    "并非基金真实历史 PE（不存历史持仓）。"
)

# Mirrors opportunity/states._VALUATION_BANDS (upper-exclusive boundaries).
_BAND_BOUNDS: tuple[tuple[float, str], ...] = (
    (0.20, "cheap"),
    (0.40, "reasonable_low"),
    (0.70, "fair"),
    (0.90, "expensive"),
    (1.01, "very_expensive"),
)


def _band_label(pct: float | None) -> str:
    if pct is None:
        return "—"
    for upper, label in _BAND_BOUNDS:
        if pct < upper:
            return label
    return "very_expensive"


@dataclass(frozen=True)
class FundDiffRow:
    instrument_id: str
    name_cn: str
    nav_band: str
    pe_band: str
    would_flip: bool
    delta_percentile: float | None
    pe_coverage_ratio: float
    pb_coverage_ratio: float
    pe_source_mix: tuple[str, ...]
    pb_source_mix: tuple[str, ...]


def build_fund_diff_row(
    *, instrument_id: str, name_cn: str,
    nav_percentile: float | None, result: FundValuationResult,
) -> FundDiffRow:
    pe_pct = result.pe.percentile
    nav_band = _band_label(nav_percentile)
    pe_band = _band_label(pe_pct)
    delta = (
        pe_pct - nav_percentile
        if pe_pct is not None and nav_percentile is not None
        else None
    )
    return FundDiffRow(
        instrument_id=instrument_id,
        name_cn=name_cn,
        nav_band=nav_band,
        pe_band=pe_band,
        would_flip=(pe_pct is not None and nav_band != pe_band),
        delta_percentile=delta,
        pe_coverage_ratio=result.pe.coverage_ratio,
        pb_coverage_ratio=result.pb.coverage_ratio,
        pe_source_mix=result.pe.source_mix,
        pb_source_mix=result.pb.source_mix,
    )


def build_floor_sensitivity(
    coverage_ratios: list[float], *, floors: tuple[float, ...] = (0.40, 0.50, 0.60),
) -> dict[float, int]:
    """Grounded-fund count at each floor (a fund is grounded iff its PE
    coverage ratio meets the floor)."""
    return {f: sum(1 for r in coverage_ratios if r >= f) for f in floors}


def _format_mix(mix: tuple[str, ...]) -> str:
    return "/".join(mix) if mix else "—"


def render_diff_report(
    rows: list[FundDiffRow], floor_sensitivity: dict[float, int]
) -> str:
    lines = ["# Phase D look-through diff report (gate #5)", "", _CAVEAT_CN, ""]
    lines.append("## Per-fund flip & coverage")
    lines.append(
        "| id | 名称 | NAV band | PE band | flip | Δpct | "
        "PE cov | PE src | PB cov | PB src |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: x.instrument_id):
        delta = "—" if r.delta_percentile is None else f"{r.delta_percentile:+.2f}"
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.nav_band} | {r.pe_band} | "
            f"{'YES' if r.would_flip else 'no'} | {delta} | "
            f"{r.pe_coverage_ratio:.2f} | {_format_mix(r.pe_source_mix)} | "
            f"{r.pb_coverage_ratio:.2f} | {_format_mix(r.pb_source_mix)} |"
        )
    lines += ["", "## Coverage-floor sensitivity (grounded funds)", ""]
    lines.append("| floor | grounded funds |")
    lines.append("|---|---|")
    for floor in sorted(floor_sensitivity):
        lines.append(f"| {floor:.2f} | {floor_sensitivity[floor]} |")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_lookthrough_diff_report.py -v`
Expected: PASS (5).

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/lookthrough_diff_report.py tests/opportunity/test_lookthrough_diff_report.py
git commit -m "feat(opportunity): pure look-through diff-report builder (Phase D PR1)"
```

---

## Task 19: diff-report command (loads cached data, writes the gate-#5 artifact)

**Files:**
- Create: `src/irc/commands/lookthrough_diff_cmd.py`
- Modify: `src/irc/cli.py`
- Test: `tests/commands/test_lookthrough_diff_cmd.py`

`run_lookthrough_diff(repo_root, *, output_dir=None, coverage_floor=0.50, pb_uses_pe_gate=False) -> int`. Loads cached `fund_holdings` (latest quarter per active fund) + `stock_valuation_history` (no live fetch), computes the per-fund result **regardless of `enabled`**, and writes the artifact via the atomic `.tmp.{pid} → os.replace` pattern. Active funds discovered as `instrument_id`s present in `fund_holdings` whose `asset_class == "cn_equity_fund"` — but `fund_holdings` has no asset_class column, so discovery joins against `instruments.asset_class` (read `instruments` table). Returns 0 on a completed run.

> The command reuses the inputs_loader pure readers (`_latest_quarter_holdings`, `_stock_series_by_code`) and the NAV percentile (`_price_series` + `self_history_percentile`) so the diff is computed from the exact same cached primitives the populate path uses. Import them from `inputs_loader`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_lookthrough_diff_cmd.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from irc.commands.lookthrough_diff_cmd import run_lookthrough_diff
from irc.data.duckdb_helper import ensure_schema


def _seed(db_path):
    con = duckdb.connect(str(db_path))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('AF1','AF1','cn_off_exchange','主动基金',NULL,'cn_equity_fund','cny',"
        " DATE '2020-01-01', 0.015, 1.0e9, NULL, 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 60.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    base = date(2025, 1, 1)
    rows = [("600519", date.fromordinal(base.toordinal() + 2 * i), 18.0 + i * 0.01, 2.0, None,
             "2026-05-15 00:00:00", "eastmoney", "r") for i in range(200)]
    con.executemany("INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows)
    con.close()


def test_run_writes_diff_report_artifact(tmp_path) -> None:
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed(db)
    out = tmp_path / "out"
    rc = run_lookthrough_diff(str(tmp_path), output_dir=str(out))
    assert rc == 0
    artifact = out / "lookthrough_diff_report.md"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "AF1" in text
    assert "0.40" in text and "0.50" in text and "0.60" in text


def test_run_computes_regardless_of_flag(tmp_path) -> None:
    # The command never reads active_fund_lookthrough.enabled — it always
    # computes (spec §8). Smoke: it produces a non-empty report with the data.
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed(db)
    out = tmp_path / "out"
    rc = run_lookthrough_diff(str(tmp_path), output_dir=str(out), coverage_floor=0.50)
    assert rc == 0
    assert (out / "lookthrough_diff_report.md").read_text(encoding="utf-8").strip()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_lookthrough_diff_cmd.py -v`
Expected: FAIL — `ModuleNotFoundError: irc.commands.lookthrough_diff_cmd`.

- [ ] **Step 3: Implement the command**

Create `src/irc/commands/lookthrough_diff_cmd.py`:

```python
"""`irc opportunity lookthrough-diff` command (Phase D PR1, gate-#5 artifact).

Loads cached fund_holdings (latest quarter per active fund) + stock_valuation_history
(NO live fetch — spec §3.7/§8) and writes the diff report regardless of the
`active_fund_lookthrough.enabled` flag. Effects (DuckDB read + atomic file write)
are confined here; the report builder is pure.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from irc.data.duckdb_helper import connect, ensure_schema
from irc.opportunity.inputs_loader import (
    _latest_quarter_holdings,
    _price_series,
    _stock_series_by_code,
)
from irc.opportunity.lookthrough_diff_report import (
    build_floor_sensitivity,
    build_fund_diff_row,
    render_diff_report,
)
from irc.opportunity.lookthrough_valuation import fund_valuation_percentile
from irc.opportunity.returns import self_history_percentile


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _active_fund_ids(con) -> tuple[str, ...]:
    rows = con.execute(
        "SELECT DISTINCT h.instrument_id FROM fund_holdings h "
        "JOIN instruments i ON i.instrument_id = h.instrument_id "
        "WHERE i.asset_class = 'cn_equity_fund' ORDER BY h.instrument_id"
    ).fetchall()
    return tuple(r[0] for r in rows)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run_lookthrough_diff(
    repo_root: str, *, output_dir: str | None = None,
    coverage_floor: float = 0.50, pb_uses_pe_gate: bool = False,
) -> int:
    root = Path(repo_root)
    db_path = root / "data" / "local.duckdb"
    try:
        con = connect(db_path)
        ensure_schema(con)
    except Exception as exc:
        print(f"ERROR: cannot open DuckDB at {db_path}: {exc}")
        return 1
    try:
        diff_rows = []
        coverage_ratios = []
        for iid in _active_fund_ids(con):
            holdings = _latest_quarter_holdings(con, iid)
            if not holdings:
                continue
            series = _stock_series_by_code(con, tuple(h.code for h in holdings))
            result = fund_valuation_percentile(
                holdings, series,
                coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
            )
            nav_series = _price_series(con, iid)
            nav_pct = self_history_percentile(nav_series) if not nav_series.empty else None
            name = con.execute(
                "SELECT name_cn FROM instruments WHERE instrument_id = ?", [iid]
            ).fetchone()
            diff_rows.append(build_fund_diff_row(
                instrument_id=iid, name_cn=(name[0] if name else iid),
                nav_percentile=nav_pct, result=result,
            ))
            coverage_ratios.append(result.pe.coverage_ratio)
        text = render_diff_report(
            diff_rows, build_floor_sensitivity(coverage_ratios)
        )
        out = Path(output_dir) if output_dir else (root / "outputs" / _today())
        _atomic_write_text(out / "lookthrough_diff_report.md", text)
        print(f"lookthrough diff report OK: {len(diff_rows)} active funds → "
              f"{out / 'lookthrough_diff_report.md'}")
        return 0
    finally:
        con.close()
```

- [ ] **Step 4: Register the Click command in `cli.py`**

Find the `opportunity` Click command/group in `cli.py`. If `opportunity` is a single `@main.command`, add a sibling command `@main.command("lookthrough-diff")`; if it is a group, add `@opportunity.command("lookthrough-diff")`. Default to a top-level sibling command for minimal coupling:

```python
@main.command("lookthrough-diff", help="Write the Phase D look-through diff report (gate-#5 artifact). Cached-only; computes regardless of the flag.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--output-dir", type=click.Path(file_okay=False), default=None)
@click.option("--coverage-floor", type=float, default=0.50, show_default=True)
@click.option("--pb-uses-pe-gate", is_flag=True, default=False)
def lookthrough_diff(repo_root: str, output_dir: str | None, coverage_floor: float, pb_uses_pe_gate: bool) -> None:
    from irc.commands.lookthrough_diff_cmd import run_lookthrough_diff
    rc = run_lookthrough_diff(
        repo_root=repo_root, output_dir=output_dir,
        coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
    )
    raise SystemExit(rc)
```

> Before writing, run `grep -n "def opportunity\|@main.command(\"opportunity\"\|@main.group" src/irc/cli.py` to confirm whether `opportunity` is a command or a group, and place the new command accordingly. Record the decision in the commit message.

- [ ] **Step 5: Run tests + help to verify they pass**

Run: `uv run pytest tests/commands/test_lookthrough_diff_cmd.py -v`
Expected: PASS (2).

Run: `uv run irc lookthrough-diff --help`
Expected: usage listing `--repo-root`, `--output-dir`, `--coverage-floor`, `--pb-uses-pe-gate`. Exit code 0.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/lookthrough_diff_cmd.py src/irc/cli.py tests/commands/test_lookthrough_diff_cmd.py
git commit -m "feat(opportunity): lookthrough-diff command writes gate-#5 artifact (Phase D PR1)"
```

---

## Task 20: lint, scoped green bar, CHANGELOG, README refresh-order note

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md` (Evidence refresh order)
- (No `VERSION` bump — per project memory.)

- [ ] **Step 1: Lint clean**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (line-length 100, py312). Fix any reported issues in the new files only.

- [ ] **Step 2: Run the full set of NEW + TOUCHED test files (scoped green bar)**

Run:
```bash
uv run pytest \
  tests/data/test_duckdb_helper.py \
  tests/data/test_stock_valuation_ingestor.py \
  tests/fundamentals/test_stock_valuation_types.py \
  tests/fundamentals/test_akshare_stock_valuation.py \
  tests/fundamentals/test_tushare_stock_valuation.py \
  tests/fundamentals/test_stock_valuation_live.py \
  tests/fundamentals/test_stock_valuation_tushare_live.py \
  tests/opportunity/test_lookthrough_valuation.py \
  tests/opportunity/test_inputs_loader.py \
  tests/opportunity/test_inputs_loader_lookthrough.py \
  tests/opportunity/test_config_threading.py \
  tests/opportunity/test_build_input_fallback.py \
  tests/opportunity/test_lookthrough_diff_report.py \
  tests/schemas/test_valuation.py \
  tests/commands/test_fundamentals_cmd.py \
  tests/commands/test_opportunity_cmd_lookthrough_dormancy.py \
  tests/commands/test_lookthrough_diff_cmd.py \
  tests/commands/test_opportunity_cmd_h3_invariant.py \
  -v
```
Expected: ALL PASS, with the two `*_live.py` files reporting `skipped` (NOT run — gate #4). **Do NOT run the whole suite as a green-bar gate** (it is ~18 min and not green on `main` — 8 known pre-existing failures + flaky e2e; per project memory). Scope to these paths.

- [ ] **Step 3: Add the CHANGELOG `[Unreleased]` entry (shadow-compute machinery; NO VERSION bump)**

In `CHANGELOG.md`, under `## [Unreleased]`, add a new subsection (keep `VERSION` at `0.9.3`):

```markdown
### Added — Phase D active-fund look-through valuation (PR1 shadow compute, 2026-06-04)

- Per-stock PE/PB valuation fetch path: `fundamentals/akshare_stock_valuation.py`
  (EastMoney `stock_value_em`, primary) + `fundamentals/tushare_stock_valuation.py`
  (`daily_basic`, token-gated fallback), `data/stock_valuation_history` DuckDB table,
  and `data/stock_valuation_ingestor.py` (atomic upsert, per-row `_source`).
- `irc fundamentals stock-valuation` command: refreshes per-stock history for every
  distinct A-share (`^\d{6}$`) in `fund_holdings`. Heavy, own cadence — NOT part of
  `irc run`. Per-stock failure-isolating.
- Pure aggregation core `opportunity/lookthrough_valuation.py`: rolls a fund's current
  top-N A-share basket into a per-date-renormalized harmonic earnings-yield PE series
  (PB in parallel), with per-metric coverage (PE/PB covered sets computed independently),
  the `/100` coverage-floor ratio, non-positive exclusion, and the PE 120/180 maturity
  gate vs PB `<30` floor.
- `inputs_loader` active-fund branch + `active_fund_lookthrough` config block
  (`config/valuation_buckets.yaml`, default `enabled: false`). **Shadow mode: the flag
  gates slot population, so production is byte-identical to today** (NAV fallback;
  all-`None` dormancy lock). The flag is threaded explicitly through
  `run_opportunity → _build_rows → _build_input → populate_inputs`.
- `irc lookthrough-diff`: gate-#5 diff report (per-fund would-flip band, Δpercentile,
  per-metric coverage + source mix, current-basket caveat, coverage-floor sensitivity at
  0.40/0.50/0.60). Computes regardless of the flag.
- Live-gated EastMoney + Tushare column-confirmation tests authored (double/triple-gated;
  gate #4 — human-run, NOT executed by CI/autodev).
```

- [ ] **Step 4: Add the README evidence-refresh-order note**

In `README.md`, find the "Evidence refresh order" section. Add the Phase D step (spec §5 "Refresh order"):

```markdown
4. `irc run` populates `fund_holdings`, then **`irc fundamentals stock-valuation`** populates
   `stock_valuation_history` (heavy; own cadence — not part of `irc run`), then
   `irc opportunity` reads both cached. The active-fund look-through is shadow-mode
   (`active_fund_lookthrough.enabled: false`) until the gate-#5 floor decision (PR2).
   Inspect the diff with `irc lookthrough-diff`.
```

> Read the existing section first (`grep -n "refresh order\|Evidence refresh" README.md`) and match its numbering/style; do not invent a step number that collides.

- [ ] **Step 5: Lint + scoped tests once more, then commit**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

```bash
git add CHANGELOG.md README.md
git commit -m "docs(opportunity): CHANGELOG + README refresh-order for Phase D PR1 (shadow compute, no VERSION bump)"
```

---

## Final verification checklist (run before handing off — gate #1/#2/#6 readiness)

- [ ] **PR1 scope held:** `config/valuation_buckets.yaml` has `enabled: false`. Confirm:
  `grep -n "enabled" config/valuation_buckets.yaml` → shows `enabled: false`.
- [ ] **Live tests authored but NOT run:** the two `*_live.py` files report `skipped` in Task 20 Step 2. No plan command used `-m live_akshare` / `-m live_tushare` / set `IRC_RUN_LIVE_*=1`.
- [ ] **No PR2 artifacts:** no ADR addendum committed; no `VERSION` change (`cat VERSION` → `0.9.3`); no flag-flip CHANGELOG record.
- [ ] **config validate green:** `uv run irc config validate` exits 0 and accepts the new block.
- [ ] **Command help green:** `uv run irc fundamentals stock-valuation --help` and `uv run irc lookthrough-diff --help` both exit 0.
- [ ] **Lint clean:** `uv run ruff check src tests` → `All checks passed!`
- [ ] **File-size budget:** `wc -l src/irc/opportunity/lookthrough_valuation.py src/irc/commands/fundamentals_cmd.py src/irc/commands/lookthrough_diff_cmd.py src/irc/opportunity/lookthrough_diff_report.py src/irc/fundamentals/akshare_stock_valuation.py src/irc/fundamentals/tushare_stock_valuation.py` → each < 200 lines.

## Remaining manual gates (NOT in this loop — surface in the run report)

- **Gate #4 (human):** run the live tests to confirm EastMoney `stock_value_em` / Tushare `daily_basic` real columns:
  `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_stock_valuation_live.py -v -s`
- **Gate #3 (human/operator):** real ingest + measured grounded-fund count:
  `uv run irc fundamentals stock-valuation` → `uv run irc lookthrough-diff` → read the floor-sensitivity table (do NOT assert 383; report the measured count).
- **Gate #5 (human):** review the diff report, choose the final `coverage_floor`. Then PR2 flips `enabled: true` (separate small plan / direct change — spec §10).
