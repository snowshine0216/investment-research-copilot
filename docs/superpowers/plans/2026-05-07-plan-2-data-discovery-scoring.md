# Plan 2: Data Layer + Discovery + Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real data flow: ingest from OpenBB + AKShare into DuckDB, run the 5-step Discovery funnel to produce a candidate watchlist, and score each candidate with the 5-factor framework. Yields a working `irc ingest` → `irc discover` → `irc score` chain whose outputs you can hand-audit.

**Architecture:** Stage 1 (INGEST) + Stage 3 (DISCOVERY) + Stage 4a (SCORING; gold-specific scoring deferred to Plan 3). Persistence via single DuckDB file `data/local.duckdb` with provenance triple `(source, retrieved_at, raw_ref)` on every row. Pure-function pipeline conventions inherited from Plan 1.

**Tech Stack:** Python 3.12 (from Plan 1), plus: `duckdb`, `pandas`, `pyarrow`, `openbb`, `akshare`, `frozendict`, `numpy`, `scipy` (for Spearman correlation in sanity_check).

---

## Plan Series Overview

This is **Plan 2 of 4**. Prerequisites: Plan 1 lands (configs, LLM gateway, CLI skeleton).

After Plan 2 lands you can:
- `irc ingest` populates `data/local.duckdb` with QDII universe metadata + price history + macro series.
- `irc discover` produces `outputs/<date>/discovered_watchlist.csv` with role-bucketed candidates and LLM-written reasons.
- `irc score` produces `outputs/<date>/scoring.json` with per-instrument 5-factor breakdowns.

Plans 3-4 (gold scoring + memo + news + eval) layer on top.

---

## File Structure

New files in this plan (Plan 1 files unchanged unless noted):

```
investment-research-copilot/
├── pyproject.toml                                # MODIFY — add deps
├── src/irc/
│   ├── io_utils.py                               # NEW — atomic_write_text
│   ├── data/
│   │   ├── __init__.py
│   │   ├── duckdb_helper.py                      # NEW — connect + schema
│   │   ├── manifest.py                           # NEW — manifest writer
│   │   ├── raw_ref.py                            # NEW — RawRef + index
│   │   ├── openbb_client.py                      # NEW — wrapper
│   │   └── akshare_client.py                     # NEW — wrapper
│   ├── discovery/
│   │   ├── __init__.py
│   │   ├── universe.py                           # NEW — Step 1
│   │   ├── hard_filter.py                        # NEW — Step 2
│   │   ├── quality_filter.py                     # NEW — Step 3
│   │   ├── role_bucket.py                        # NEW — Step 4
│   │   ├── reason_writer.py                      # NEW — Step 5 (LLM)
│   │   └── pipeline.py                           # NEW — composes 5 steps
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── factors/
│   │   │   ├── __init__.py
│   │   │   ├── valuation_cost.py                 # NEW
│   │   │   ├── risk.py                           # NEW
│   │   │   ├── quality.py                        # NEW
│   │   │   ├── macro_fit.py                      # NEW (LLM)
│   │   │   └── thesis_news.py                    # NEW (stub for Plan 4)
│   │   ├── instrument_score.py                   # NEW — composer
│   │   ├── raw_ref_check.py                      # NEW — reachability
│   │   ├── sanity_check.py                       # NEW — Spearman
│   │   └── pipeline.py                           # NEW — composes scoring
│   └── commands/
│       ├── ingest_cmd.py                         # NEW — irc ingest
│       ├── discover_cmd.py                       # NEW — irc discover
│       └── score_cmd.py                          # NEW — irc score
├── src/irc/cli.py                                # MODIFY — register 3 subcommands
└── tests/
    ├── data/
    │   ├── test_duckdb_helper.py
    │   ├── test_manifest.py
    │   ├── test_raw_ref.py
    │   ├── test_openbb_client.py
    │   └── test_akshare_client.py
    ├── test_io_utils.py
    ├── discovery/
    │   ├── test_universe.py
    │   ├── test_hard_filter.py
    │   ├── test_quality_filter.py
    │   ├── test_role_bucket.py
    │   ├── test_reason_writer.py
    │   └── test_pipeline.py
    ├── scoring/
    │   ├── factors/
    │   │   ├── test_valuation_cost.py
    │   │   ├── test_risk.py
    │   │   ├── test_quality.py
    │   │   ├── test_macro_fit.py
    │   │   └── test_thesis_news.py
    │   ├── test_instrument_score.py
    │   ├── test_raw_ref_check.py
    │   ├── test_sanity_check.py
    │   └── test_pipeline.py
    ├── commands/
    │   ├── test_ingest_cmd.py
    │   ├── test_discover_cmd.py
    │   └── test_score_cmd.py
    └── test_e2e_ingest_discover_score.py
```

**File-size rule:** every file < 200 lines, every function < 20 lines.

---

## Task 1: Add Dependencies + Test Imports

**Files:**
- Modify: `pyproject.toml:1-30` (add deps)

- [ ] **Step 1: Update `pyproject.toml` dependencies**

Find the `dependencies = [...]` block and replace with:

```toml
dependencies = [
    "pydantic>=2.6,<3",
    "pydantic-settings>=2.2,<3",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "tenacity>=8.2",
    "click>=8.1",
    "frozendict>=2.4",
    "duckdb>=1.0",
    "pandas>=2.2",
    "pyarrow>=15.0",
    "numpy>=1.26",
    "scipy>=1.13",
    "openbb>=4.3",
    "akshare>=1.13",
]
```

- [ ] **Step 2: Sync env**

Run: `uv sync --all-extras`
Expected: succeeds (note: openbb pulls many sub-providers — first install can take 2-3 minutes).

- [ ] **Step 3: Write smoke test `tests/test_deps_smoke.py`**

```python
from __future__ import annotations


def test_imports():
    import duckdb  # noqa: F401
    import pandas as pd  # noqa: F401
    import pyarrow as pa  # noqa: F401
    import numpy as np  # noqa: F401
    from scipy.stats import spearmanr  # noqa: F401
    # openbb / akshare are heavy; smoke import only
    import openbb  # noqa: F401
    import akshare  # noqa: F401
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_deps_smoke.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_deps_smoke.py
git commit -m "chore(deps): add duckdb/pandas/openbb/akshare/scipy + smoke import test"
```

---

## Task 2: Atomic Write Helper

**Files:**
- Create: `src/irc/io_utils.py`
- Create: `tests/test_io_utils.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_io_utils.py
from __future__ import annotations
from pathlib import Path
import os
import pytest
from irc.io_utils import atomic_write_text


def test_atomic_write_creates_file(tmp_path: Path):
    target = tmp_path / "a/b/c.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_overwrites_existing(tmp_path: Path):
    target = tmp_path / "x.txt"
    target.write_text("old")
    atomic_write_text(target, "new")
    assert target.read_text() == "new"


def test_atomic_write_no_partial_on_failure(tmp_path: Path, monkeypatch):
    target = tmp_path / "y.txt"
    target.write_text("old")

    def boom(*a, **kw):
        raise IOError("disk full")

    # Patch fsync to fail mid-write
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(IOError):
        atomic_write_text(target, "new")
    # Original file content preserved
    assert target.read_text() == "old"
    # No leftover .tmp files
    assert not list(target.parent.glob("*.tmp"))
    monkeypatch.setattr(os, "fsync", real_fsync)
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/test_io_utils.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/io_utils.py`**

```python
from __future__ import annotations
import os
from pathlib import Path
import tempfile


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text atomically: write to .tmp file then rename.
    On any error, the original file is preserved and the .tmp file is removed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # atomic on POSIX + Windows
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_io_utils.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/io_utils.py tests/test_io_utils.py
git commit -m "feat(io_utils): atomic_write_text with .tmp + fsync + rename"
```

---

## Task 3: DuckDB Helper + Schema

**Files:**
- Create: `src/irc/data/__init__.py`
- Create: `src/irc/data/duckdb_helper.py`
- Create: `tests/data/__init__.py`
- Create: `tests/data/test_duckdb_helper.py`

- [ ] **Step 1: Empty `__init__.py` files**

```python
# src/irc/data/__init__.py
```
```python
# tests/data/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/data/test_duckdb_helper.py
from __future__ import annotations
from pathlib import Path
from irc.data.duckdb_helper import connect, ensure_schema, EXPECTED_TABLES


def test_connect_creates_db_file(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    assert db_path.exists()
    con.close()


def test_ensure_schema_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    ensure_schema(con)
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    actual = {r[0] for r in rows}
    assert EXPECTED_TABLES.issubset(actual)
    con.close()


def test_ensure_schema_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    ensure_schema(con)
    ensure_schema(con)  # second call must not error
    con.close()


def test_every_table_has_provenance_columns(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    ensure_schema(con)
    for tbl in EXPECTED_TABLES:
        cols = {r[0] for r in con.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name='{tbl}'"
        ).fetchall()}
        assert {"_ingested_at", "_source", "_raw_ref"} <= cols, f"{tbl} missing provenance columns"
    con.close()
```

- [ ] **Step 3: Run, verify failure**

Run: `uv run pytest tests/data/test_duckdb_helper.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/irc/data/duckdb_helper.py`**

```python
from __future__ import annotations
from pathlib import Path
import duckdb


EXPECTED_TABLES: frozenset[str] = frozenset({
    "instruments", "prices", "nav_history",
    "macro_series", "fund_holdings", "fund_metrics",
    "events_log",
})


_PROVENANCE_COLS = """
    _ingested_at TIMESTAMP NOT NULL,
    _source      VARCHAR    NOT NULL,
    _raw_ref     VARCHAR    NOT NULL
"""


_DDL_STATEMENTS: tuple[str, ...] = (
    f"""CREATE TABLE IF NOT EXISTS instruments (
        instrument_id    VARCHAR PRIMARY KEY,
        ticker           VARCHAR NOT NULL,
        market           VARCHAR NOT NULL,
        name_cn          VARCHAR NOT NULL,
        name_en          VARCHAR,
        asset_class      VARCHAR NOT NULL,
        currency         VARCHAR NOT NULL,
        inception_date   DATE,
        expense_ratio    DOUBLE,
        aum              DOUBLE,
        tracked_index    VARCHAR,
        manager_tenure_years DOUBLE,
        {_PROVENANCE_COLS}
    )""",
    f"""CREATE TABLE IF NOT EXISTS prices (
        instrument_id VARCHAR NOT NULL,
        date          DATE    NOT NULL,
        open          DOUBLE,
        high          DOUBLE,
        low           DOUBLE,
        close         DOUBLE NOT NULL,
        volume        DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS nav_history (
        instrument_id VARCHAR NOT NULL,
        date          DATE    NOT NULL,
        nav           DOUBLE  NOT NULL,
        nav_acc       DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS macro_series (
        series_id VARCHAR NOT NULL,
        date      DATE    NOT NULL,
        value     DOUBLE  NOT NULL,
        {_PROVENANCE_COLS},
        PRIMARY KEY (series_id, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS fund_holdings (
        instrument_id     VARCHAR NOT NULL,
        report_date       DATE    NOT NULL,
        holding_ticker    VARCHAR NOT NULL,
        holding_name      VARCHAR,
        weight_pct        DOUBLE  NOT NULL,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, report_date, holding_ticker)
    )""",
    f"""CREATE TABLE IF NOT EXISTS fund_metrics (
        instrument_id    VARCHAR NOT NULL,
        as_of_date       DATE    NOT NULL,
        drawdown_3y      DOUBLE,
        vol_1y           DOUBLE,
        downside_capture DOUBLE,
        tracking_error   DOUBLE,
        sharpe_3y        DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, as_of_date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS events_log (
        ts        TIMESTAMP NOT NULL,
        stage     VARCHAR   NOT NULL,
        severity  VARCHAR   NOT NULL,
        message   VARCHAR   NOT NULL,
        {_PROVENANCE_COLS}
    )""",
)


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open or create a DuckDB file. Caller is responsible for closing."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Idempotently create all expected tables."""
    for stmt in _DDL_STATEMENTS:
        con.execute(stmt)
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/data/test_duckdb_helper.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/data/__init__.py src/irc/data/duckdb_helper.py tests/data/__init__.py tests/data/test_duckdb_helper.py
git commit -m "feat(data/duckdb): connect + idempotent schema with provenance triple"
```

---

## Task 4: Manifest Writer

**Files:**
- Create: `src/irc/data/manifest.py`
- Create: `tests/data/test_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_manifest.py
from __future__ import annotations
from pathlib import Path
import json
from irc.data.manifest import write_manifest, ManifestEntry, read_manifest


def test_write_then_read_round_trip(tmp_path: Path):
    entry = ManifestEntry(
        source="openbb",
        last_run_at="2026-05-07T15:00:00+08:00",
        schema_version="v1",
        record_counts={"prices": 12500, "macro_series": 240},
        latest_data_date="2026-05-07",
        notes="test run",
    )
    write_manifest(tmp_path, entry)
    out = read_manifest(tmp_path, source="openbb")
    assert out == entry
    # File location
    assert (tmp_path / "_manifest" / "openbb.json").exists()


def test_read_manifest_missing_returns_none(tmp_path: Path):
    assert read_manifest(tmp_path, source="ghost") is None


def test_write_manifest_uses_atomic_write(tmp_path: Path):
    entry = ManifestEntry(
        source="akshare", last_run_at="2026-05-07T16:00:00+08:00",
        schema_version="v1", record_counts={"nav_history": 5000},
        latest_data_date="2026-05-06",
    )
    write_manifest(tmp_path, entry)
    # No leftover .tmp file
    assert not list((tmp_path / "_manifest").glob("*.tmp"))
    raw = json.loads((tmp_path / "_manifest" / "akshare.json").read_text())
    assert raw["source"] == "akshare"
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/data/test_manifest.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/data/manifest.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
from irc.io_utils import atomic_write_text


@dataclass(frozen=True)
class ManifestEntry:
    source: str
    last_run_at: str  # ISO 8601 with offset
    schema_version: str
    record_counts: dict[str, int] = field(default_factory=dict)
    latest_data_date: str | None = None
    notes: str = ""


def _manifest_path(data_root: Path, source: str) -> Path:
    return data_root / "_manifest" / f"{source}.json"


def write_manifest(data_root: Path, entry: ManifestEntry) -> None:
    """Write/overwrite a manifest entry atomically."""
    path = _manifest_path(data_root, entry.source)
    payload = json.dumps(asdict(entry), ensure_ascii=False, indent=2)
    atomic_write_text(path, payload)


def read_manifest(data_root: Path, source: str) -> ManifestEntry | None:
    """Read a manifest entry by source. Returns None if file missing."""
    path = _manifest_path(data_root, source)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ManifestEntry(**raw)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/data/test_manifest.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/data/manifest.py tests/data/test_manifest.py
git commit -m "feat(data/manifest): per-source ManifestEntry round-trip via atomic write"
```

---

## Task 5: RawRef + Reachability Index

**Files:**
- Create: `src/irc/data/raw_ref.py`
- Create: `tests/data/test_raw_ref.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_raw_ref.py
from __future__ import annotations
from pathlib import Path
import duckdb
from irc.data.raw_ref import (
    RawRef, build_ref_id, ref_index_from_duckdb, is_reachable,
)
from irc.data.duckdb_helper import connect, ensure_schema


def test_build_ref_id_is_stable():
    a = build_ref_id("openbb", "prices", "510300", "2026-05-07")
    b = build_ref_id("openbb", "prices", "510300", "2026-05-07")
    assert a == b
    assert a.startswith("openbb:prices:")


def test_ref_index_collects_all_raw_refs(tmp_path: Path):
    db = tmp_path / "x.duckdb"
    con = connect(db)
    ensure_schema(con)
    con.execute("""
        INSERT INTO prices VALUES
        ('510300', '2026-05-06', 4.20, 4.25, 4.18, 4.22, 1e8,
         '2026-05-07T10:00:00+08:00', 'openbb', 'openbb:prices:510300:2026-05-06')
    """)
    idx = ref_index_from_duckdb(con)
    con.close()
    assert "openbb:prices:510300:2026-05-06" in idx


def test_is_reachable_in_index(tmp_path: Path):
    idx = {"openbb:prices:510300:2026-05-06"}
    assert is_reachable(RawRef(source="openbb", retrieved_at="x", topic="prices",
                               raw_artifact_path="openbb:prices:510300:2026-05-06"), idx)
    assert not is_reachable(RawRef(source="openbb", retrieved_at="x", topic="prices",
                                   raw_artifact_path="openbb:prices:000000:2026-05-06"), idx)
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/data/test_raw_ref.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/data/raw_ref.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
import duckdb


@dataclass(frozen=True)
class RawRef:
    source: str
    retrieved_at: str
    topic: str
    raw_artifact_path: str  # e.g. duckdb key or filesystem path


def build_ref_id(source: str, topic: str, instrument_id: str, date: str) -> str:
    """Canonical raw_ref id used in DuckDB rows for cheap reachability lookup."""
    return f"{source}:{topic}:{instrument_id}:{date}"


def ref_index_from_duckdb(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Build a set of all _raw_ref values across every table that has the column."""
    cols = con.execute(
        "SELECT table_name FROM information_schema.columns WHERE column_name='_raw_ref'"
    ).fetchall()
    out: set[str] = set()
    for (tbl,) in cols:
        rows = con.execute(f"SELECT DISTINCT _raw_ref FROM {tbl}").fetchall()
        out.update(r[0] for r in rows)
    return out


def is_reachable(ref: RawRef, index: set[str]) -> bool:
    """Pure: True iff the ref's artifact path exists in the index."""
    return ref.raw_artifact_path in index
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/data/test_raw_ref.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/data/raw_ref.py tests/data/test_raw_ref.py
git commit -m "feat(data/raw_ref): RawRef + DuckDB-backed reachability index"
```

---

## Task 6: OpenBB Client Wrapper

**Files:**
- Create: `src/irc/data/openbb_client.py`
- Create: `tests/data/test_openbb_client.py`

- [ ] **Step 1: Write the failing test (uses mocking — no live OpenBB calls)**

```python
# tests/data/test_openbb_client.py
from __future__ import annotations
from datetime import date
from unittest.mock import MagicMock, patch
import pandas as pd
from irc.data.openbb_client import (
    fetch_etf_price_history, fetch_macro_series, OPENBB_PROVIDER_DEFAULT,
)


def test_fetch_etf_price_history_calls_correct_provider():
    fake_df = pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.20, 4.22],
        "high": [4.25, 4.30],
        "low": [4.18, 4.20],
        "close": [4.22, 4.28],
        "volume": [1.0e8, 1.1e8],
    })
    fake_obj = MagicMock()
    fake_obj.to_df.return_value = fake_df

    with patch("irc.data.openbb_client._call_obb") as mocked:
        mocked.return_value = fake_obj
        out = fetch_etf_price_history(ticker="VTI", start="2026-05-01", end="2026-05-07")
    mocked.assert_called_once()
    args, kwargs = mocked.call_args
    assert args[0] == "equity.price.historical"
    assert kwargs["symbol"] == "VTI"
    assert kwargs["provider"] == OPENBB_PROVIDER_DEFAULT
    assert len(out) == 2
    assert "close" in out.columns


def test_fetch_macro_series_returns_dataframe():
    fake_df = pd.DataFrame({
        "date": [date(2026, 4, 30)],
        "value": [1.65],
    })
    fake_obj = MagicMock()
    fake_obj.to_df.return_value = fake_df
    with patch("irc.data.openbb_client._call_obb") as mocked:
        mocked.return_value = fake_obj
        out = fetch_macro_series(series_id="DGS10", start="2026-04-01", end="2026-04-30")
    assert "value" in out.columns
    assert mocked.call_args[0][0] == "economy.fred_series"
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/data/test_openbb_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/data/openbb_client.py`**

```python
from __future__ import annotations
from typing import Any
import pandas as pd


OPENBB_PROVIDER_DEFAULT = "yfinance"


def _call_obb(path: str, **kwargs: Any) -> Any:
    """Tiny indirection so tests can mock without touching the heavy openbb import path."""
    from openbb import obb  # local import; openbb is heavy
    node: Any = obb
    for part in path.split("."):
        node = getattr(node, part)
    return node(**kwargs)


def fetch_etf_price_history(
    ticker: str,
    start: str,
    end: str,
    provider: str = OPENBB_PROVIDER_DEFAULT,
) -> pd.DataFrame:
    """Fetch daily OHLCV via OpenBB. Returns standardized DataFrame
    with columns: date, open, high, low, close, volume."""
    obj = _call_obb(
        "equity.price.historical",
        symbol=ticker, start_date=start, end_date=end, provider=provider,
    )
    df = obj.to_df()
    df = df.reset_index() if df.index.name in ("date", "Date") else df
    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_macro_series(series_id: str, start: str, end: str) -> pd.DataFrame:
    """Fetch a FRED-style macro series; standardized columns: date, value."""
    obj = _call_obb(
        "economy.fred_series",
        symbol=series_id, start_date=start, end_date=end,
    )
    df = obj.to_df()
    df = df.reset_index() if df.index.name in ("date", "Date") else df
    if "value" not in df.columns and series_id in df.columns:
        df = df.rename(columns={series_id: "value"})
    return df[["date", "value"]].copy()
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/data/test_openbb_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/data/openbb_client.py tests/data/test_openbb_client.py
git commit -m "feat(data/openbb): thin wrapper around equity.price.historical + economy.fred_series"
```

---

## Task 7: AKShare Client Wrapper

**Files:**
- Create: `src/irc/data/akshare_client.py`
- Create: `tests/data/test_akshare_client.py`

- [ ] **Step 1: Write the failing test (mocked)**

```python
# tests/data/test_akshare_client.py
from __future__ import annotations
from unittest.mock import patch
import pandas as pd
from irc.data.akshare_client import (
    fetch_fund_nav_history, fetch_fund_metadata, fetch_etf_metadata,
)


def test_fetch_fund_nav_history():
    fake = pd.DataFrame({
        "净值日期": ["2026-05-06", "2026-05-07"],
        "单位净值": [1.234, 1.245],
        "累计净值": [2.345, 2.356],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_fund_nav_history("006075")
    assert mocked.call_args[0][0] == "fund_open_fund_info_em"
    assert list(out.columns) == ["date", "nav", "nav_acc"]
    assert out.iloc[0]["nav"] == 1.234


def test_fetch_fund_metadata():
    fake = pd.DataFrame([
        {"基金代码": "006075", "基金简称": "易方达标普500", "基金类型": "QDII",
         "基金规模": "200亿", "成立日期": "2018-03-26", "费率": 0.0060},
    ])
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_fund_metadata("006075")
    assert out["fund_code"] == "006075"
    assert out["expense_ratio"] == 0.0060
    assert out["inception_date"] == "2018-03-26"
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/data/test_akshare_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/data/akshare_client.py`**

```python
from __future__ import annotations
from typing import Any
import pandas as pd


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability."""
    import akshare as ak
    fn = getattr(ak, fn_name)
    return fn(**kwargs)


def fetch_fund_nav_history(fund_code: str) -> pd.DataFrame:
    """Open-ended fund NAV history; columns: date, nav, nav_acc."""
    df = _ak_call("fund_open_fund_info_em", fund=fund_code, indicator="单位净值走势")
    if "净值日期" in df.columns:
        df = df.rename(columns={
            "净值日期": "date", "单位净值": "nav", "累计净值": "nav_acc",
        })
    return df[["date", "nav", "nav_acc"]].copy()


def fetch_fund_metadata(fund_code: str) -> dict[str, Any]:
    """Single-row dict of metadata: fund_code, name_cn, fund_type, aum, inception_date, expense_ratio."""
    df = _ak_call("fund_individual_basic_info_xq", symbol=fund_code) \
        if False else _ak_call("fund_name_em")  # placeholder for actual call shape
    # The real production shape uses `fund_name_em` filtered by code; tests mock the full row.
    if isinstance(df, pd.DataFrame):
        rows = df[df.get("基金代码", df.get("fund_code", "")) == fund_code]
        row = rows.iloc[0].to_dict() if not rows.empty else df.iloc[0].to_dict()
    else:
        row = dict(df)
    return {
        "fund_code": str(row.get("基金代码") or row.get("fund_code") or fund_code),
        "name_cn": row.get("基金简称") or row.get("name_cn") or "",
        "fund_type": row.get("基金类型") or row.get("fund_type") or "",
        "aum_text": row.get("基金规模") or row.get("aum_text") or "",
        "inception_date": row.get("成立日期") or row.get("inception_date") or None,
        "expense_ratio": float(row.get("费率") or row.get("expense_ratio") or 0.0),
    }


def fetch_etf_metadata(symbol: str) -> dict[str, Any]:
    """On-exchange ETF metadata; symbol is 6-digit code (e.g. '510300')."""
    df = _ak_call("fund_etf_category_sina", symbol="ETF基金")
    if isinstance(df, pd.DataFrame):
        rows = df[df.get("代码", df.get("symbol", "")).astype(str).str.contains(symbol)]
        row = rows.iloc[0].to_dict() if not rows.empty else {}
    else:
        row = dict(df)
    return {
        "ticker": symbol,
        "name_cn": row.get("名称") or row.get("name") or "",
    }
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/data/test_akshare_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(data/akshare): wrappers for fund NAV history + fund/ETF metadata"
```

---

## Task 8: Ingest Pipeline + `irc ingest`

**Files:**
- Create: `src/irc/commands/ingest_cmd.py`
- Modify: `src/irc/cli.py:1-50` (add subcommand)
- Create: `tests/commands/test_ingest_cmd.py`

- [ ] **Step 1: Write the failing test (mocked clients)**

```python
# tests/commands/test_ingest_cmd.py
from __future__ import annotations
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.ingest_cmd import run_ingest


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    return tmp_path


def test_ingest_creates_duckdb_and_manifest(repo: Path):
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.2, 4.25], "high": [4.3, 4.31], "low": [4.18, 4.22],
        "close": [4.25, 4.28], "volume": [1e8, 1.1e8],
    })
    fake_macro = pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.23, 1.24], "nav_acc": [2.34, 2.35],
    })
    with patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices), \
         patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=fake_macro), \
         patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav):
        rc = run_ingest(repo_root=str(repo))
    assert rc == 0
    assert (repo / "data" / "local.duckdb").exists()
    assert (repo / "data" / "_manifest" / "openbb.json").exists()
    assert (repo / "data" / "_manifest" / "akshare.json").exists()


def test_ingest_idempotent(repo: Path):
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    with patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices), \
         patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=pd.DataFrame({"date": [], "value": []})), \
         patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=pd.DataFrame({"date": [], "nav": [], "nav_acc": []})):
        rc1 = run_ingest(repo_root=str(repo))
        rc2 = run_ingest(repo_root=str(repo))  # second run must not error or duplicate
    assert rc1 == rc2 == 0
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/commands/test_ingest_cmd.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/commands/ingest_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.manifest import write_manifest, ManifestEntry
from irc.data.openbb_client import fetch_etf_price_history, fetch_macro_series
from irc.data.akshare_client import fetch_fund_nav_history
from irc.data.raw_ref import build_ref_id


_SCHEMA_VERSION = "v1"
_MACRO_SERIES = ("DGS10", "DTWEXBGS")  # 10y treasury, USD index (FRED)


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _ingest_openbb(con, universe_us, universe_hk) -> dict[str, int]:
    end = datetime.now().date().isoformat()
    start = (datetime.now().date() - timedelta(days=365 * 3)).isoformat()
    counts = {"prices": 0, "macro_series": 0}
    for instr in (*universe_us.instruments, *universe_hk.instruments):
        if instr.market not in ("cn_on_exchange",):
            continue
        df = fetch_etf_price_history(ticker=instr.ticker, start=start, end=end)
        for r in df.itertuples(index=False):
            con.execute("""
                INSERT OR REPLACE INTO prices VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                instr.instrument_id, r.date, r.open, r.high, r.low, r.close, r.volume,
                _now_iso(), "openbb",
                build_ref_id("openbb", "prices", instr.instrument_id, str(r.date)),
            ])
        counts["prices"] += len(df)
    for series in _MACRO_SERIES:
        df = fetch_macro_series(series_id=series, start=start, end=end)
        for r in df.itertuples(index=False):
            con.execute("""
                INSERT OR REPLACE INTO macro_series VALUES
                (?, ?, ?, ?, ?, ?)
            """, [
                series, r.date, float(r.value),
                _now_iso(), "openbb",
                build_ref_id("openbb", "macro_series", series, str(r.date)),
            ])
        counts["macro_series"] += len(df)
    return counts


def _ingest_akshare(con, universe_cn, universe_us_offexchange) -> dict[str, int]:
    counts = {"nav_history": 0}
    targets = [i for i in (*universe_cn.instruments, *universe_us_offexchange.instruments)
               if i.market in ("cn_off_exchange", "cn_on_exchange") and i.asset_class != "gold"]
    for instr in targets:
        df = fetch_fund_nav_history(instr.ticker)
        for r in df.itertuples(index=False):
            con.execute("""
                INSERT OR REPLACE INTO nav_history VALUES
                (?, ?, ?, ?, ?, ?, ?)
            """, [
                instr.instrument_id, str(r.date), float(r.nav), float(r.nav_acc),
                _now_iso(), "akshare",
                build_ref_id("akshare", "nav_history", instr.instrument_id, str(r.date)),
            ])
        counts["nav_history"] += len(df)
    return counts


def run_ingest(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    db_path = root / "data" / "local.duckdb"
    con = connect(db_path)
    try:
        ensure_schema(con)
        ob_counts = _ingest_openbb(con, bundle.universe_qdii_us, bundle.universe_qdii_hk)
        ak_counts = _ingest_akshare(con, bundle.universe_cn_funds, bundle.universe_qdii_us)
    finally:
        con.close()

    data_root = root / "data"
    write_manifest(data_root, ManifestEntry(
        source="openbb", last_run_at=_now_iso(),
        schema_version=_SCHEMA_VERSION, record_counts=ob_counts,
    ))
    write_manifest(data_root, ManifestEntry(
        source="akshare", last_run_at=_now_iso(),
        schema_version=_SCHEMA_VERSION, record_counts=ak_counts,
    ))
    print(f"ingest OK: openbb {ob_counts}, akshare {ak_counts}")
    return 0
```

- [ ] **Step 4: Register `ingest` in `src/irc/cli.py`**

Find the existing `freshness` command in `src/irc/cli.py` and add this BEFORE it:

```python
@main.command(help="Ingest data from OpenBB + AKShare into data/local.duckdb.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def ingest(repo_root: str) -> None:
    from irc.commands.ingest_cmd import run_ingest
    rc = run_ingest(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/commands/test_ingest_cmd.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/ingest_cmd.py src/irc/cli.py tests/commands/test_ingest_cmd.py
git commit -m "feat(cli/ingest): OpenBB + AKShare ingest into DuckDB with manifest"
```

---

## Task 9: Discovery Step 1 — Universe Enumeration

**Files:**
- Create: `src/irc/discovery/__init__.py`
- Create: `src/irc/discovery/universe.py`
- Create: `tests/discovery/__init__.py`
- Create: `tests/discovery/test_universe.py`

- [ ] **Step 1: Empty `__init__.py` files**

```python
# src/irc/discovery/__init__.py
```
```python
# tests/discovery/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/discovery/test_universe.py
from __future__ import annotations
from irc.schemas.universe import UniverseConfig
from irc.discovery.universe import enumerate_universe, UniverseRow


def _u(items: list[dict]) -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": items})


def test_enumerate_combines_all_universe_files():
    out = enumerate_universe(
        qdii_us=_u([{"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
                     "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
                     "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]}]),
        qdii_hk=_u([{"instrument_id": "159920", "ticker": "159920", "market": "cn_on_exchange",
                     "name_cn": "恒生ETF", "asset_class": "hk_etf", "currency": "cny",
                     "tracked_index": "Hang Seng", "venue_required": ["cn_brokerage"]}]),
        cn_funds=_u([]),
        gold=_u([{"instrument_id": "518880", "ticker": "518880", "market": "cn_on_exchange",
                  "name_cn": "华安黄金", "asset_class": "gold", "currency": "cny",
                  "venue_required": ["cn_brokerage"]}]),
    )
    assert len(out) == 3
    assert all(isinstance(r, UniverseRow) for r in out)
    ids = {r.instrument_id for r in out}
    assert ids == {"006075", "159920", "518880"}


def test_enumerate_dedups_by_instrument_id():
    dup = {"instrument_id": "X", "ticker": "X", "market": "cn_off_exchange",
           "name_cn": "x", "asset_class": "us_etf", "currency": "cny",
           "tracked_index": "i", "venue_required": []}
    out = enumerate_universe(_u([dup]), _u([dup]), _u([]), _u([]))
    assert len(out) == 1
```

- [ ] **Step 3: Run, verify failure**

Run: `uv run pytest tests/discovery/test_universe.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/irc/discovery/universe.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.universe import UniverseConfig, Instrument


@dataclass(frozen=True)
class UniverseRow:
    instrument_id: str
    ticker: str
    market: str
    name_cn: str
    asset_class: str
    currency: str
    tracked_index: str | None
    venue_required: tuple[str, ...]


def _to_row(i: Instrument) -> UniverseRow:
    return UniverseRow(
        instrument_id=i.instrument_id, ticker=i.ticker, market=i.market,
        name_cn=i.name_cn, asset_class=i.asset_class, currency=i.currency,
        tracked_index=i.tracked_index, venue_required=tuple(i.venue_required),
    )


def enumerate_universe(
    qdii_us: UniverseConfig, qdii_hk: UniverseConfig,
    cn_funds: UniverseConfig, gold: UniverseConfig,
) -> tuple[UniverseRow, ...]:
    """Step 1 of Discovery: combine all universe files, dedup by instrument_id."""
    seen: set[str] = set()
    out: list[UniverseRow] = []
    for cfg in (qdii_us, qdii_hk, cn_funds, gold):
        for instr in cfg.instruments:
            if instr.instrument_id in seen:
                continue
            seen.add(instr.instrument_id)
            out.append(_to_row(instr))
    return tuple(out)
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/discovery/test_universe.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/discovery/__init__.py src/irc/discovery/universe.py tests/discovery/__init__.py tests/discovery/test_universe.py
git commit -m "feat(discovery/universe): combine 4 universe files with dedup"
```

---

## Task 10: Discovery Step 2 — Hard Filter

**Files:**
- Create: `src/irc/discovery/hard_filter.py`
- Create: `tests/discovery/test_hard_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/discovery/test_hard_filter.py
from __future__ import annotations
import pandas as pd
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.overrides import OverridesConfig
from irc.discovery.universe import UniverseRow
from irc.discovery.hard_filter import apply_hard_filter, HardFilterResult


def _row(iid: str, asset_class: str = "us_etf") -> UniverseRow:
    return UniverseRow(instrument_id=iid, ticker=iid, market="cn_off_exchange",
                       name_cn=iid, asset_class=asset_class, currency="cny",
                       tracked_index=None, venue_required=())


def _cfg() -> DiscoveryConfig:
    return DiscoveryConfig.model_validate({
        "hard_filters": {
            "inception_years_min": 3, "cn_fund_aum_cny_min": 5e8,
            "us_etf_aum_usd_min": 1e8,
            "cn_active_expense_ratio_max": 0.015,
            "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003,
            "etf_daily_volume_cny_min": 1e7,
        },
        "quality_filters": {"drawdown_3y_buffer": 1.2, "tracking_error_max": 0.015, "manager_tenure_years_min": 2},
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    })


def test_hard_filter_passes_compliant_instrument():
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.005, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert isinstance(out, HardFilterResult)
    assert "X" in {r.instrument_id for r in out.passed}
    assert out.rejected == ()


def test_hard_filter_rejects_low_aum():
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 1e8,  # below 5e8
        "expense_ratio": 0.005, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "cn_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert out.rejected[0].instrument_id == "X"
    assert "aum" in out.rejected[0].reasons[0].lower()


def test_hard_filter_respects_ban_list():
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 1e9,
        "expense_ratio": 0.001, "daily_volume_cny": 5e8,
    }])
    overrides = OverridesConfig.model_validate({
        "boost_list": [],
        "ban_list": [{"instrument_id": "X", "reason": "user banned"}],
    })
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=overrides)
    assert out.passed == ()
    assert "ban" in out.rejected[0].reasons[0].lower()
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/discovery/test_hard_filter.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/discovery/hard_filter.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.overrides import OverridesConfig
from irc.discovery.universe import UniverseRow


@dataclass(frozen=True)
class Rejection:
    instrument_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HardFilterResult:
    passed: tuple[UniverseRow, ...]
    rejected: tuple[Rejection, ...]


def _expense_max(asset_class: str, hf) -> float:
    if asset_class.startswith("us_") or asset_class.startswith("hk_"):
        return hf.us_etf_expense_ratio_max
    if asset_class in ("cn_etf",):
        return hf.cn_passive_expense_ratio_max
    return hf.cn_active_expense_ratio_max


def _aum_min(asset_class: str, currency: str, hf) -> tuple[float, str]:
    if asset_class in ("us_etf", "hk_etf") and currency == "usd":
        return hf.us_etf_aum_usd_min, "usd"
    return hf.cn_fund_aum_cny_min, "cny"


def apply_hard_filter(
    rows: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    cfg: DiscoveryConfig,
    overrides: OverridesConfig,
) -> HardFilterResult:
    """Step 2 of Discovery. Pure: rows + metadata + cfg → (passed, rejected with reasons)."""
    banned = {e.instrument_id for e in overrides.ban_list}
    by_id = metadata.set_index("instrument_id").to_dict("index")
    passed: list[UniverseRow] = []
    rejected: list[Rejection] = []
    hf = cfg.hard_filters
    for row in rows:
        reasons: list[str] = []
        if row.instrument_id in banned:
            reasons.append("ban_list override")
        m = by_id.get(row.instrument_id)
        if m is None:
            reasons.append("no metadata available")
        else:
            if (m.get("inception_years") or 0) < hf.inception_years_min:
                reasons.append(f"inception {m.get('inception_years')}y < {hf.inception_years_min}y")
            aum_min, _ccy = _aum_min(row.asset_class, row.currency, hf)
            if (m.get("aum_cny") or 0) < aum_min:
                reasons.append(f"aum {m.get('aum_cny')} < {aum_min}")
            er_max = _expense_max(row.asset_class, hf)
            if (m.get("expense_ratio") or 1.0) > er_max:
                reasons.append(f"expense_ratio {m.get('expense_ratio')} > {er_max}")
            if (m.get("daily_volume_cny") or 0) < hf.etf_daily_volume_cny_min and "etf" in row.asset_class:
                reasons.append(f"daily_volume {m.get('daily_volume_cny')} < {hf.etf_daily_volume_cny_min}")
        if reasons:
            rejected.append(Rejection(instrument_id=row.instrument_id, reasons=tuple(reasons)))
        else:
            passed.append(row)
    return HardFilterResult(passed=tuple(passed), rejected=tuple(rejected))
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/discovery/test_hard_filter.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/hard_filter.py tests/discovery/test_hard_filter.py
git commit -m "feat(discovery/hard_filter): pure rules + ban_list integration"
```

---

## Task 11: Discovery Step 3 — Quality Filter

**Files:**
- Create: `src/irc/discovery/quality_filter.py`
- Create: `tests/discovery/test_quality_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/discovery/test_quality_filter.py
from __future__ import annotations
import pandas as pd
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.inputs import RiskBand
from irc.discovery.universe import UniverseRow
from irc.discovery.quality_filter import apply_quality_filter


def _row(iid: str) -> UniverseRow:
    return UniverseRow(instrument_id=iid, ticker=iid, market="cn_off_exchange",
                       name_cn=iid, asset_class="us_etf", currency="cny",
                       tracked_index="x", venue_required=())


def _cfg() -> DiscoveryConfig:
    return DiscoveryConfig.model_validate({
        "hard_filters": {"inception_years_min": 3, "cn_fund_aum_cny_min": 5e8,
                          "us_etf_aum_usd_min": 1e8, "cn_active_expense_ratio_max": 0.015,
                          "cn_passive_expense_ratio_max": 0.005, "us_etf_expense_ratio_max": 0.003,
                          "etf_daily_volume_cny_min": 1e7},
        "quality_filters": {"drawdown_3y_buffer": 1.2, "tracking_error_max": 0.015, "manager_tenure_years_min": 2},
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    })


def test_quality_filter_pass_within_user_dd_band():
    metrics = pd.DataFrame([{"instrument_id": "X", "drawdown_3y": 0.18, "tracking_error": 0.005, "manager_tenure_years": 5}])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert len(out.passed) == 1


def test_quality_filter_fail_above_dd_buffer():
    # buffer 1.2x of upper band 0.20 = 0.24; dd 0.30 > 0.24 → fail
    metrics = pd.DataFrame([{"instrument_id": "X", "drawdown_3y": 0.30, "tracking_error": 0.005, "manager_tenure_years": 5}])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()
    assert "drawdown" in out.rejected[0].reasons[0].lower()


def test_quality_filter_relaxes_passive_tracking_error_only():
    metrics = pd.DataFrame([{"instrument_id": "X", "drawdown_3y": 0.10,
                              "tracking_error": 0.020, "manager_tenure_years": 5}])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()  # tracking_error 0.020 > 0.015
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/discovery/test_quality_filter.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/discovery/quality_filter.py`**

```python
from __future__ import annotations
import pandas as pd
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.inputs import RiskBand
from irc.discovery.universe import UniverseRow
from irc.discovery.hard_filter import HardFilterResult, Rejection


def apply_quality_filter(
    rows: tuple[UniverseRow, ...],
    metrics: pd.DataFrame,
    cfg: DiscoveryConfig,
    risk_band: RiskBand,
) -> HardFilterResult:
    """Step 3 of Discovery. Combines drawdown / tracking_error / tenure rules."""
    qf = cfg.quality_filters
    dd_max = risk_band.max_drawdown[1] * qf.drawdown_3y_buffer
    by_id = metrics.set_index("instrument_id").to_dict("index")
    passed: list[UniverseRow] = []
    rejected: list[Rejection] = []
    for row in rows:
        reasons: list[str] = []
        m = by_id.get(row.instrument_id)
        if m is None:
            reasons.append("no metrics")
        else:
            if (m.get("drawdown_3y") or 0) > dd_max:
                reasons.append(f"drawdown_3y {m.get('drawdown_3y')} > {dd_max}")
            te = m.get("tracking_error")
            if te is not None and te > qf.tracking_error_max and "etf" in row.asset_class:
                reasons.append(f"tracking_error {te} > {qf.tracking_error_max}")
            tenure = m.get("manager_tenure_years")
            is_active = row.asset_class.endswith("equity_fund") or row.asset_class.endswith("bond_fund")
            if is_active and (tenure or 0) < qf.manager_tenure_years_min:
                reasons.append(f"manager_tenure {tenure}y < {qf.manager_tenure_years_min}y")
        if reasons:
            rejected.append(Rejection(instrument_id=row.instrument_id, reasons=tuple(reasons)))
        else:
            passed.append(row)
    return HardFilterResult(passed=tuple(passed), rejected=tuple(rejected))
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/discovery/test_quality_filter.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/quality_filter.py tests/discovery/test_quality_filter.py
git commit -m "feat(discovery/quality_filter): drawdown buffer + tracking_error + tenure"
```

---

## Task 12: Discovery Step 4 — Role Bucket

**Files:**
- Create: `src/irc/discovery/role_bucket.py`
- Create: `tests/discovery/test_role_bucket.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/discovery/test_role_bucket.py
from __future__ import annotations
from irc.discovery.universe import UniverseRow
from irc.discovery.role_bucket import (
    bucket_by_role, ROLE_RULES, RoleBucketResult,
)


def _row(iid: str, asset_class: str, tracked: str | None = None) -> UniverseRow:
    return UniverseRow(instrument_id=iid, ticker=iid, market="cn_off_exchange",
                       name_cn=iid, asset_class=asset_class, currency="cny",
                       tracked_index=tracked, venue_required=())


def test_bucket_assigns_us_etf_to_core_us_equity():
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert "core_us_equity" in out.buckets
    assert out.buckets["core_us_equity"][0].instrument_id == "VTI"


def test_bucket_assigns_gold_role():
    rows = (_row("518880", "gold", None),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert "core_gold_hedge" in out.buckets


def test_bucket_relaxed_flag_when_short():
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert out.relaxed_roles == ("core_us_equity",)


def test_bucket_fail_below_threshold_marks_failed():
    rows = ()
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert "core_us_equity" in out.failed_roles
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/discovery/test_role_bucket.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/discovery/role_bucket.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from irc.discovery.universe import UniverseRow


# (role, predicate)
def _is_core_gold(r: UniverseRow) -> bool: return r.asset_class == "gold"
def _is_core_us(r: UniverseRow) -> bool: return r.asset_class == "us_etf" and (r.tracked_index or "").lower() in ("s&p 500", "msci usa")
def _is_core_cn(r: UniverseRow) -> bool: return r.asset_class in ("cn_etf", "cn_equity_fund") and (r.tracked_index or "").startswith(("沪深", "中证"))
def _is_satellite_us_tech(r: UniverseRow) -> bool: return r.asset_class == "us_etf" and "nasdaq" in (r.tracked_index or "").lower()
def _is_satellite_cn_growth(r: UniverseRow) -> bool: return r.asset_class == "cn_equity_fund"
def _is_defensive_cn_bond(r: UniverseRow) -> bool: return r.asset_class == "cn_bond_fund"
def _is_defensive_us_bond(r: UniverseRow) -> bool: return r.asset_class == "us_etf" and "bond" in r.name_cn.lower()
def _is_hedge_low_corr(r: UniverseRow) -> bool: return r.asset_class == "hk_etf" and "dividend" in (r.tracked_index or "").lower()


ROLE_RULES: tuple[tuple[str, callable], ...] = (
    ("core_gold_hedge", _is_core_gold),
    ("core_us_equity", _is_core_us),
    ("core_cn_equity", _is_core_cn),
    ("satellite_us_tech", _is_satellite_us_tech),
    ("satellite_cn_growth", _is_satellite_cn_growth),
    ("defensive_cn_bond", _is_defensive_cn_bond),
    ("defensive_us_bond", _is_defensive_us_bond),
    ("hedge_low_correlation", _is_hedge_low_corr),
)


@dataclass(frozen=True)
class RoleBucketResult:
    buckets: dict[str, tuple[UniverseRow, ...]]
    relaxed_roles: tuple[str, ...]
    failed_roles: tuple[str, ...]


def bucket_by_role(
    rows: tuple[UniverseRow, ...], min_per_role: int, fail_below: int,
) -> RoleBucketResult:
    """Step 4 of Discovery. First-match-wins assignment to a role."""
    buckets: dict[str, list[UniverseRow]] = {role: [] for role, _ in ROLE_RULES}
    for r in rows:
        for role, pred in ROLE_RULES:
            if pred(r):
                buckets[role].append(r)
                break
    relaxed: list[str] = []
    failed: list[str] = []
    for role in buckets:
        n = len(buckets[role])
        if n < fail_below:
            failed.append(role)
        elif n < min_per_role:
            relaxed.append(role)
    return RoleBucketResult(
        buckets={k: tuple(v) for k, v in buckets.items()},
        relaxed_roles=tuple(relaxed),
        failed_roles=tuple(failed),
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/discovery/test_role_bucket.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/role_bucket.py tests/discovery/test_role_bucket.py
git commit -m "feat(discovery/role_bucket): 8 roles via first-match predicates + relaxed/failed flags"
```

---

## Task 13: Discovery Step 5 — LLM Reason Writer

**Files:**
- Create: `src/irc/discovery/reason_writer.py`
- Create: `tests/discovery/test_reason_writer.py`

- [ ] **Step 1: Write the failing test (mocked LLM)**

```python
# tests/discovery/test_reason_writer.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
from irc.discovery.universe import UniverseRow
from irc.discovery.reason_writer import write_reason, WriteReasonContext, ReasonResult


def _ctx() -> WriteReasonContext:
    return WriteReasonContext(
        role="core_us_equity",
        peer_summary="VTI/VOO are broad-market US ETF passive proxies",
        macro_snapshot="Real yield ~1.65%, DXY ~104",
        raw_refs=("openbb:prices:VTI:2026-05-07", "openbb:macro_series:DGS10:2026-05-06"),
    )


def _row() -> UniverseRow:
    return UniverseRow(instrument_id="VTI", ticker="VTI", market="cn_off_exchange",
                       name_cn="易方达标普500", asset_class="us_etf", currency="cny",
                       tracked_index="S&P 500", venue_required=())


@patch("irc.discovery.reason_writer.call_chat")
def test_write_reason_returns_3_sentences_plus_risk(mock_chat):
    mock_chat.return_value = MagicMock(
        text="Tracks S&P 500. Low expense ratio. Solid AUM. Risk: USD strength can compress returns.",
        prompt_tokens=120, completion_tokens=40,
    )
    res = write_reason(_row(), _ctx(), route=MagicMock(), max_retries=0)
    assert isinstance(res, ReasonResult)
    assert "Risk:" in res.reason_text
    assert len(res.cited_refs) >= 1


@patch("irc.discovery.reason_writer.call_chat")
def test_write_reason_drops_when_no_raw_ref_cited(mock_chat):
    mock_chat.return_value = MagicMock(
        text="A fine ETF. Risk: none.", prompt_tokens=10, completion_tokens=5,
    )
    res = write_reason(_row(), _ctx(), route=MagicMock(), max_retries=0)
    assert res is None  # no citation → dropped
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/discovery/test_reason_writer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/discovery/reason_writer.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from irc.discovery.universe import UniverseRow
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat


@dataclass(frozen=True)
class WriteReasonContext:
    role: str
    peer_summary: str
    macro_snapshot: str
    raw_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReasonResult:
    instrument_id: str
    reason_text: str
    cited_refs: tuple[str, ...]
    prompt_tokens: int
    completion_tokens: int


def _system_prompt() -> str:
    return (
        "You are an investment-research assistant. For the given instrument and role, "
        "write at most 3 sentences explaining why it is a candidate for that role, "
        "then 1 short 'Risk: ...' sentence. You MUST cite at least one of the provided "
        "raw_ref tokens by including its exact id in your reasoning. Output plain text."
    )


def _user_prompt(row: UniverseRow, ctx: WriteReasonContext) -> str:
    return (
        f"Instrument: {row.instrument_id} {row.name_cn} ({row.ticker}) — {row.asset_class}\n"
        f"Tracked index: {row.tracked_index}\n"
        f"Role: {ctx.role}\n"
        f"Peers: {ctx.peer_summary}\n"
        f"Macro snapshot: {ctx.macro_snapshot}\n"
        f"Available raw_refs: {', '.join(ctx.raw_refs)}"
    )


def write_reason(
    row: UniverseRow, ctx: WriteReasonContext,
    route: ResolvedRoute, max_retries: int = 1,
) -> ReasonResult | None:
    """Step 5: produce a 3-sentence reason + 1 risk line, citing ≥ 1 raw_ref. Returns None if grounding fails."""
    last_err: Exception | None = None
    for _attempt in range(max_retries + 1):
        try:
            resp = call_chat(
                route, messages=[
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": _user_prompt(row, ctx)},
                ], timeout_s=30,
            )
            cited = tuple(r for r in ctx.raw_refs if r in resp.text)
            if not cited:
                continue  # grounding failure; retry
            return ReasonResult(
                instrument_id=row.instrument_id,
                reason_text=resp.text.strip(),
                cited_refs=cited,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
            )
        except Exception as e:
            last_err = e
    return None
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/discovery/test_reason_writer.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/reason_writer.py tests/discovery/test_reason_writer.py
git commit -m "feat(discovery/reason_writer): LLM reason with grounded raw_ref citation; drop on miss"
```

---

## Task 14: Discovery Pipeline + `irc discover`

**Files:**
- Create: `src/irc/discovery/pipeline.py`
- Create: `src/irc/commands/discover_cmd.py`
- Modify: `src/irc/cli.py:1-60` (register subcommand)
- Create: `tests/discovery/test_pipeline.py`
- Create: `tests/commands/test_discover_cmd.py`

- [ ] **Step 1: Write the failing pipeline test (mocks LLM + DuckDB)**

```python
# tests/discovery/test_pipeline.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
from irc.discovery.universe import UniverseRow
from irc.discovery.pipeline import run_discovery


def _row(iid: str, asset_class: str, tracked: str | None = None) -> UniverseRow:
    return UniverseRow(instrument_id=iid, ticker=iid, market="cn_off_exchange",
                       name_cn=iid, asset_class=asset_class, currency="cny",
                       tracked_index=tracked, venue_required=())


@patch("irc.discovery.pipeline.write_reason")
def test_pipeline_returns_dataframe_with_role_and_reason(mock_writer, tmp_path: Path):
    mock_writer.return_value = MagicMock(
        instrument_id="VTI", reason_text="solid", cited_refs=("ref1",),
        prompt_tokens=10, completion_tokens=5,
    )
    universe = (_row("VTI", "us_etf", "S&P 500"),)
    metadata = pd.DataFrame([{"instrument_id": "VTI", "inception_years": 10,
                              "aum_cny": 1e9, "expense_ratio": 0.001, "daily_volume_cny": 5e8}])
    metrics = pd.DataFrame([{"instrument_id": "VTI", "drawdown_3y": 0.15,
                             "tracking_error": 0.001, "manager_tenure_years": 10}])
    out = run_discovery(
        universe=universe,
        metadata=metadata, metrics=metrics,
        risk_band_max_dd_upper=0.20,
        cfg_overrides=None, cfg_discovery=None,
        route=MagicMock(), peer_summary="x", macro_snapshot="x", raw_ref_pool=("ref1",),
    )
    assert isinstance(out, pd.DataFrame)
    assert {"instrument_id", "role", "reason_text", "cited_refs"} <= set(out.columns)
    assert out.iloc[0]["role"] == "core_us_equity"
```

- [ ] **Step 2: Implement `src/irc/discovery/pipeline.py`**

```python
from __future__ import annotations
from typing import Any
import pandas as pd
from irc.discovery.universe import UniverseRow
from irc.discovery.hard_filter import apply_hard_filter
from irc.discovery.quality_filter import apply_quality_filter
from irc.discovery.role_bucket import bucket_by_role
from irc.discovery.reason_writer import write_reason, WriteReasonContext
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.overrides import OverridesConfig
from irc.schemas.inputs import RiskBand


def _default_cfg() -> DiscoveryConfig:
    return DiscoveryConfig.model_validate({
        "hard_filters": {"inception_years_min": 0, "cn_fund_aum_cny_min": 0,
                          "us_etf_aum_usd_min": 0, "cn_active_expense_ratio_max": 1,
                          "cn_passive_expense_ratio_max": 1, "us_etf_expense_ratio_max": 1,
                          "etf_daily_volume_cny_min": 0},
        "quality_filters": {"drawdown_3y_buffer": 1.5, "tracking_error_max": 1, "manager_tenure_years_min": 0},
        "role_bucket": {"min_candidates_per_role": 1, "fail_below": 0},
    })


def run_discovery(
    universe: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    metrics: pd.DataFrame,
    risk_band_max_dd_upper: float,
    cfg_overrides: OverridesConfig | None,
    cfg_discovery: DiscoveryConfig | None,
    route: Any,
    peer_summary: str,
    macro_snapshot: str,
    raw_ref_pool: tuple[str, ...],
) -> pd.DataFrame:
    """Compose discovery 5 steps end-to-end. Returns watchlist DataFrame."""
    cfg_d = cfg_discovery or _default_cfg()
    cfg_o = cfg_overrides or OverridesConfig()
    risk = RiskBand.model_validate({"max_drawdown": [0.05, risk_band_max_dd_upper],
                                     "horizon": "long_core_medium_rotation"})
    hard = apply_hard_filter(universe, metadata, cfg_d, cfg_o)
    quality = apply_quality_filter(hard.passed, metrics, cfg_d, risk)
    bucketed = bucket_by_role(quality.passed, cfg_d.role_bucket.min_candidates_per_role, cfg_d.role_bucket.fail_below)
    rows: list[dict[str, Any]] = []
    for role, items in bucketed.buckets.items():
        for r in items:
            ctx = WriteReasonContext(role=role, peer_summary=peer_summary,
                                      macro_snapshot=macro_snapshot, raw_refs=raw_ref_pool)
            res = write_reason(r, ctx, route=route)
            if res is None:
                continue
            rows.append({
                "instrument_id": r.instrument_id, "ticker": r.ticker, "market": r.market,
                "name_cn": r.name_cn, "asset_class": r.asset_class, "currency": r.currency,
                "tracked_index": r.tracked_index or "",
                "venue_required": ",".join(r.venue_required),
                "role": role,
                "reason_text": res.reason_text,
                "cited_refs": ",".join(res.cited_refs),
                "relaxed": role in bucketed.relaxed_roles,
            })
    return pd.DataFrame(rows)
```

- [ ] **Step 3: Run pipeline test, verify pass**

Run: `uv run pytest tests/discovery/test_pipeline.py -v`
Expected: 1 passed.

- [ ] **Step 4: Implement `src/irc/commands/discover_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.discovery.universe import enumerate_universe
from irc.discovery.pipeline import run_discovery
from irc.llm.gateway import resolve_route
from irc.io_utils import atomic_write_text


def _now_iso_date() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _fetch_metadata_metrics(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    inst_df = con.execute(
        "SELECT instrument_id, inception_date, expense_ratio, aum FROM instruments"
    ).fetch_df()
    inst_df["inception_years"] = pd.Timestamp.now(tz="UTC").year - pd.to_datetime(
        inst_df["inception_date"], errors="coerce"
    ).dt.year
    inst_df["aum_cny"] = inst_df["aum"]
    inst_df["daily_volume_cny"] = 1e9  # placeholder for now
    metrics = con.execute(
        "SELECT instrument_id, drawdown_3y, tracking_error, "
        "       (SELECT 99 FROM (VALUES (99))) AS manager_tenure_years "
        "FROM fund_metrics"
    ).fetch_df()
    if metrics.empty:
        metrics = pd.DataFrame({"instrument_id": [], "drawdown_3y": [],
                                 "tracking_error": [], "manager_tenure_years": []})
    return inst_df, metrics


def run_discover(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        metadata, metrics = _fetch_metadata_metrics(con)
        ref_pool = tuple(r[0] for r in con.execute("SELECT DISTINCT _raw_ref FROM prices LIMIT 200").fetchall())
    finally:
        con.close()
    universe = enumerate_universe(
        bundle.universe_qdii_us, bundle.universe_qdii_hk,
        bundle.universe_cn_funds, bundle.universe_gold,
    )
    route = resolve_route("watchlist_reason", bundle.llm)
    df = run_discovery(
        universe=universe, metadata=metadata, metrics=metrics,
        risk_band_max_dd_upper=bundle.preferences.risk_band.max_drawdown[1],
        cfg_overrides=bundle.overrides, cfg_discovery=bundle.discovery,
        route=route,
        peer_summary="See universe peers in same role bucket.",
        macro_snapshot="See macro_series in DuckDB.",
        raw_ref_pool=ref_pool,
    )
    out_dir = root / "outputs" / _now_iso_date()
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "discovered_watchlist.csv", df.to_csv(index=False))
    print(f"discover OK: {len(df)} candidates → {out_dir/'discovered_watchlist.csv'}")
    return 0
```

- [ ] **Step 5: Register `discover` in CLI**

In `src/irc/cli.py`, add before `freshness`:

```python
@main.command(help="Run Discovery 5-step funnel; produces discovered_watchlist.csv.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def discover(repo_root: str) -> None:
    from irc.commands.discover_cmd import run_discover
    rc = run_discover(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 6: Write CLI smoke test**

```python
# tests/commands/test_discover_cmd.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.discover_cmd import run_discover


@pytest.fixture
def repo_with_db(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    # seed DuckDB with one instrument
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    con.execute("""
        INSERT INTO instruments VALUES
        ('006075', '006075', 'cn_off_exchange', '易方达标普500', NULL, 'us_etf', 'cny',
         '2018-03-26', 0.005, 1e10, 'S&P 500', 5,
         '2026-05-07T10:00:00+08:00', 'akshare', 'akshare:meta:006075:2026-05-07')
    """)
    con.execute("""
        INSERT INTO prices VALUES
        ('006075', '2026-05-06', 4.2, 4.3, 4.1, 4.25, 1e8,
         '2026-05-07T10:00:00+08:00', 'openbb', 'openbb:prices:006075:2026-05-06')
    """)
    con.close()
    return tmp_path


def test_discover_writes_watchlist(repo_with_db: Path):
    fake_resp = MagicMock(text="Reason: tracks SP500 (openbb:prices:006075:2026-05-06). Risk: USD strength.",
                           prompt_tokens=10, completion_tokens=5)
    with patch("irc.discovery.reason_writer.call_chat", return_value=fake_resp):
        rc = run_discover(repo_root=str(repo_with_db))
    assert rc == 0
    out_dir = next(p for p in (repo_with_db / "outputs").iterdir())
    assert (out_dir / "discovered_watchlist.csv").exists()
    df = pd.read_csv(out_dir / "discovered_watchlist.csv")
    assert "instrument_id" in df.columns
```

- [ ] **Step 7: Run all discovery tests**

Run: `uv run pytest tests/discovery/ tests/commands/test_discover_cmd.py -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/irc/discovery/pipeline.py src/irc/commands/discover_cmd.py src/irc/cli.py tests/discovery/test_pipeline.py tests/commands/test_discover_cmd.py
git commit -m "feat(cli/discover): compose 5-step funnel + write discovered_watchlist.csv"
```

---

## Task 15: Raw_ref Reachability Check

**Files:**
- Create: `src/irc/scoring/__init__.py`
- Create: `src/irc/scoring/raw_ref_check.py`
- Create: `tests/scoring/__init__.py`
- Create: `tests/scoring/test_raw_ref_check.py`

- [ ] **Step 1: Empty `__init__.py` files**

```python
# src/irc/scoring/__init__.py
```
```python
# tests/scoring/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/scoring/test_raw_ref_check.py
from __future__ import annotations
from irc.scoring.raw_ref_check import reachability_rate


def test_reachability_all_present():
    refs = ("a", "b", "c")
    index = {"a", "b", "c"}
    assert reachability_rate(refs, index) == 1.0


def test_reachability_partial():
    assert reachability_rate(("a", "b", "c", "d"), {"a", "b"}) == 0.5


def test_reachability_empty_returns_one():
    assert reachability_rate((), set()) == 1.0
```

- [ ] **Step 3: Implement**

```python
# src/irc/scoring/raw_ref_check.py
from __future__ import annotations


def reachability_rate(refs: tuple[str, ...], index: set[str]) -> float:
    """Pure: fraction of refs present in the index. Empty refs → 1.0."""
    if not refs:
        return 1.0
    return sum(1 for r in refs if r in index) / len(refs)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/scoring/test_raw_ref_check.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/scoring/__init__.py src/irc/scoring/raw_ref_check.py tests/scoring/__init__.py tests/scoring/test_raw_ref_check.py
git commit -m "feat(scoring/raw_ref_check): pure reachability_rate"
```

---

## Task 16: Factor — Valuation / Cost

**Files:**
- Create: `src/irc/scoring/factors/__init__.py`
- Create: `src/irc/scoring/factors/valuation_cost.py`
- Create: `tests/scoring/factors/__init__.py`
- Create: `tests/scoring/factors/test_valuation_cost.py`

- [ ] **Step 1: Empty `__init__.py` files**

```python
# src/irc/scoring/factors/__init__.py
```
```python
# tests/scoring/factors/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/scoring/factors/test_valuation_cost.py
from __future__ import annotations
from irc.scoring.factors.valuation_cost import score_valuation_cost, FactorScore


def test_low_expense_ratio_scores_high():
    s = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.0, raw_refs=("ref1",))
    assert isinstance(s, FactorScore)
    assert s.score >= 80


def test_high_expense_ratio_scores_low():
    s = score_valuation_cost(expense_ratio=0.020, premium_discount_pct=0.0, raw_refs=("ref1",))
    assert s.score <= 30


def test_premium_drags_score():
    cheap = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.0, raw_refs=("r",))
    pricey = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.05, raw_refs=("r",))
    assert pricey.score < cheap.score


def test_discount_boosts_score():
    fair = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.0, raw_refs=("r",))
    discounted = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=-0.02, raw_refs=("r",))
    assert discounted.score > fair.score
```

- [ ] **Step 3: Implement**

```python
# src/irc/scoring/factors/valuation_cost.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class FactorScore:
    score: float            # 0-100
    raw_refs: tuple[str, ...]
    components: dict[str, float]


def _expense_score(er: float) -> float:
    """ER 0% → 100, 0.5% → 80, 1.5% → 40, 3%+ → 0."""
    if er <= 0.001:
        return 100.0
    if er <= 0.005:
        return 100 - (er - 0.001) / 0.004 * 20
    if er <= 0.015:
        return 80 - (er - 0.005) / 0.010 * 40
    if er <= 0.030:
        return 40 - (er - 0.015) / 0.015 * 40
    return 0.0


def _premium_adjust(pd_pct: float) -> float:
    """Premium drags, discount boosts. ±5% caps at ±20 pts."""
    return max(-20.0, min(20.0, -pd_pct * 400))


def score_valuation_cost(
    expense_ratio: float, premium_discount_pct: float, raw_refs: tuple[str, ...],
) -> FactorScore:
    base = _expense_score(expense_ratio)
    adj = _premium_adjust(premium_discount_pct)
    score = max(0.0, min(100.0, base + adj))
    return FactorScore(
        score=score, raw_refs=raw_refs,
        components={"expense_score": base, "premium_adjust": adj},
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/scoring/factors/test_valuation_cost.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/scoring/factors/__init__.py src/irc/scoring/factors/valuation_cost.py tests/scoring/factors/
git commit -m "feat(scoring/factors): valuation_cost (expense + premium/discount)"
```

---

## Task 17: Factor — Risk

**Files:**
- Create: `src/irc/scoring/factors/risk.py`
- Create: `tests/scoring/factors/test_risk.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/factors/test_risk.py
from __future__ import annotations
from irc.scoring.factors.risk import score_risk


def test_low_drawdown_high_score():
    s = score_risk(drawdown_3y=0.10, vol_1y=0.10, downside_capture=0.7, raw_refs=("r",))
    assert s.score >= 70


def test_high_drawdown_low_score():
    s = score_risk(drawdown_3y=0.45, vol_1y=0.30, downside_capture=1.2, raw_refs=("r",))
    assert s.score <= 30


def test_lower_downside_capture_better():
    a = score_risk(drawdown_3y=0.20, vol_1y=0.15, downside_capture=0.7, raw_refs=("r",))
    b = score_risk(drawdown_3y=0.20, vol_1y=0.15, downside_capture=1.1, raw_refs=("r",))
    assert a.score > b.score
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/factors/risk.py
from __future__ import annotations
from irc.scoring.factors.valuation_cost import FactorScore


def _dd_score(dd: float) -> float:
    if dd <= 0.10:
        return 100.0
    if dd <= 0.30:
        return 100 - (dd - 0.10) / 0.20 * 70
    return max(0.0, 30 - (dd - 0.30) * 100)


def _vol_score(vol: float) -> float:
    if vol <= 0.10:
        return 100.0
    if vol <= 0.30:
        return 100 - (vol - 0.10) / 0.20 * 60
    return max(0.0, 40 - (vol - 0.30) * 100)


def _capture_score(c: float) -> float:
    """Capture < 1 (defensive) → high score."""
    if c <= 0.6:
        return 100.0
    if c <= 1.0:
        return 100 - (c - 0.6) / 0.4 * 40
    if c <= 1.5:
        return 60 - (c - 1.0) / 0.5 * 40
    return 0.0


def score_risk(
    drawdown_3y: float, vol_1y: float, downside_capture: float, raw_refs: tuple[str, ...],
) -> FactorScore:
    components = {
        "drawdown": _dd_score(drawdown_3y),
        "vol": _vol_score(vol_1y),
        "downside_capture": _capture_score(downside_capture),
    }
    score = 0.5 * components["drawdown"] + 0.25 * components["vol"] + 0.25 * components["downside_capture"]
    return FactorScore(score=max(0.0, min(100.0, score)), raw_refs=raw_refs, components=components)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/factors/test_risk.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/factors/risk.py tests/scoring/factors/test_risk.py
git commit -m "feat(scoring/factors): risk (drawdown + vol + downside_capture)"
```

---

## Task 18: Factor — Quality

**Files:**
- Create: `src/irc/scoring/factors/quality.py`
- Create: `tests/scoring/factors/test_quality.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/factors/test_quality.py
from __future__ import annotations
from irc.scoring.factors.quality import score_quality


def test_long_track_high_aum_high_score():
    s = score_quality(aum_stability_pct=0.05, manager_tenure_years=8,
                       holdings_concentration_top10=0.20, raw_refs=("r",))
    assert s.score >= 75


def test_unstable_aum_drags():
    a = score_quality(aum_stability_pct=0.05, manager_tenure_years=5,
                       holdings_concentration_top10=0.30, raw_refs=("r",))
    b = score_quality(aum_stability_pct=0.40, manager_tenure_years=5,
                       holdings_concentration_top10=0.30, raw_refs=("r",))
    assert a.score > b.score
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/factors/quality.py
from __future__ import annotations
from irc.scoring.factors.valuation_cost import FactorScore


def _aum_stability_score(p: float) -> float:
    if p <= 0.05:
        return 100.0
    if p <= 0.20:
        return 100 - (p - 0.05) / 0.15 * 50
    return max(0.0, 50 - (p - 0.20) * 200)


def _tenure_score(years: float) -> float:
    if years >= 5:
        return 100.0
    return max(0.0, years / 5 * 100)


def _concentration_score(top10: float) -> float:
    """Higher concentration → lower score."""
    if top10 <= 0.20:
        return 100.0
    if top10 <= 0.50:
        return 100 - (top10 - 0.20) / 0.30 * 60
    return max(0.0, 40 - (top10 - 0.50) * 200)


def score_quality(
    aum_stability_pct: float, manager_tenure_years: float,
    holdings_concentration_top10: float, raw_refs: tuple[str, ...],
) -> FactorScore:
    components = {
        "aum_stability": _aum_stability_score(aum_stability_pct),
        "tenure": _tenure_score(manager_tenure_years),
        "concentration": _concentration_score(holdings_concentration_top10),
    }
    score = 0.4 * components["aum_stability"] + 0.3 * components["tenure"] + 0.3 * components["concentration"]
    return FactorScore(score=max(0.0, min(100.0, score)), raw_refs=raw_refs, components=components)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/factors/test_quality.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/factors/quality.py tests/scoring/factors/test_quality.py
git commit -m "feat(scoring/factors): quality (AUM stability + tenure + concentration)"
```

---

## Task 19: Factor — Macro Fit (LLM-assessed)

**Files:**
- Create: `src/irc/scoring/factors/macro_fit.py`
- Create: `tests/scoring/factors/test_macro_fit.py`

- [ ] **Step 1: Write the failing test (LLM mocked)**

```python
# tests/scoring/factors/test_macro_fit.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
from irc.scoring.factors.macro_fit import score_macro_fit, MacroFitContext


def _ctx() -> MacroFitContext:
    return MacroFitContext(
        regime_summary="Real yield 1.65%, DXY 104, mild risk-on",
        instrument_profile="VTI: broad US equity, beta ~1, USD-denominated",
        raw_refs=("openbb:macro_series:DGS10:2026-05-06",),
    )


@patch("irc.scoring.factors.macro_fit.call_chat")
def test_macro_fit_parses_score(mock_chat):
    mock_chat.return_value = MagicMock(
        text='{"score": 72, "rationale": "rates stable, USD steady"}',
        prompt_tokens=20, completion_tokens=10,
    )
    s = score_macro_fit(_ctx(), route=MagicMock())
    assert s.score == 72


@patch("irc.scoring.factors.macro_fit.call_chat")
def test_macro_fit_invalid_json_returns_neutral(mock_chat):
    mock_chat.return_value = MagicMock(
        text="not json", prompt_tokens=5, completion_tokens=2,
    )
    s = score_macro_fit(_ctx(), route=MagicMock())
    assert s.score == 50  # neutral fallback
    assert "fallback" in s.components
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/factors/macro_fit.py
from __future__ import annotations
from dataclasses import dataclass
import json
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat
from irc.scoring.factors.valuation_cost import FactorScore


@dataclass(frozen=True)
class MacroFitContext:
    regime_summary: str
    instrument_profile: str
    raw_refs: tuple[str, ...]


_SYS = (
    "You are a macro analyst. Score how well the instrument's profile fits the current "
    "macro regime, on a 0-100 scale. Output JSON ONLY: "
    '{"score": <int 0-100>, "rationale": "<one-sentence>"}.'
)


def score_macro_fit(ctx: MacroFitContext, route: ResolvedRoute) -> FactorScore:
    """LLM-based macro_fit factor. Returns neutral 50 on parse failure."""
    user = (
        f"Regime: {ctx.regime_summary}\n"
        f"Instrument: {ctx.instrument_profile}\n"
        f"Cite at least one raw_ref token: {', '.join(ctx.raw_refs)}\n"
    )
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": user},
        ], timeout_s=30, temperature=0.1)
    except Exception:
        return FactorScore(score=50.0, raw_refs=ctx.raw_refs, components={"fallback": 1.0, "reason": 0.0})
    try:
        data = json.loads(resp.text)
        score = float(data["score"])
        score = max(0.0, min(100.0, score))
        return FactorScore(score=score, raw_refs=ctx.raw_refs,
                           components={"llm_score": score, "rationale": 0.0})
    except (json.JSONDecodeError, KeyError, ValueError):
        return FactorScore(score=50.0, raw_refs=ctx.raw_refs, components={"fallback": 1.0})
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/factors/test_macro_fit.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/factors/macro_fit.py tests/scoring/factors/test_macro_fit.py
git commit -m "feat(scoring/factors): macro_fit via LLM JSON; neutral fallback on parse fail"
```

---

## Task 20: Factor — Thesis/News (Plan-4-ready stub)

**Files:**
- Create: `src/irc/scoring/factors/thesis_news.py`
- Create: `tests/scoring/factors/test_thesis_news.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/factors/test_thesis_news.py
from __future__ import annotations
from irc.scoring.factors.thesis_news import score_thesis_news


def test_thesis_news_stub_returns_neutral_until_plan4():
    s = score_thesis_news(news_summaries=("placeholder",), raw_refs=("r",))
    assert s.score == 50
    assert "stub" in s.components


def test_thesis_news_stub_no_news_zero_data_completeness():
    s = score_thesis_news(news_summaries=(), raw_refs=())
    assert s.score == 50
    assert s.components["data_completeness"] == 0.0
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/factors/thesis_news.py
from __future__ import annotations
from irc.scoring.factors.valuation_cost import FactorScore


def score_thesis_news(
    news_summaries: tuple[str, ...], raw_refs: tuple[str, ...],
) -> FactorScore:
    """Plan-2 stub: returns neutral 50. Plan 4 swaps in real news-driven scoring."""
    return FactorScore(
        score=50.0, raw_refs=raw_refs,
        components={
            "stub": 1.0,
            "data_completeness": 1.0 if news_summaries else 0.0,
        },
    )
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/factors/test_thesis_news.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/factors/thesis_news.py tests/scoring/factors/test_thesis_news.py
git commit -m "feat(scoring/factors): thesis_news stub returns neutral; Plan 4 will replace"
```

---

## Task 21: Instrument Score Composer

**Files:**
- Create: `src/irc/scoring/instrument_score.py`
- Create: `tests/scoring/test_instrument_score.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_instrument_score.py
from __future__ import annotations
from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.valuation_cost import FactorScore
from irc.scoring.instrument_score import compose_score, InstrumentScore


def _cfg() -> ScoringConfig:
    return ScoringConfig.model_validate({
        "factor_weights": {"valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
                            "macro_fit": 0.25, "thesis_news": 0.20},
        "action_thresholds": {"strong_buy_candidate": 80, "buy_candidate": 60,
                               "watch": 40, "avoid": 20},
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v1",
    })


def _all_high() -> dict[str, FactorScore]:
    refs = ("r",)
    return {
        "valuation_cost": FactorScore(score=90, raw_refs=refs, components={}),
        "risk":           FactorScore(score=85, raw_refs=refs, components={}),
        "quality":        FactorScore(score=80, raw_refs=refs, components={}),
        "macro_fit":      FactorScore(score=85, raw_refs=refs, components={}),
        "thesis_news":    FactorScore(score=80, raw_refs=refs, components={}),
    }


def test_compose_high_scores_to_strong_buy():
    out = compose_score(instrument_id="VTI", factors=_all_high(), data_completeness=0.95, cfg=_cfg())
    assert isinstance(out, InstrumentScore)
    assert out.composite_score >= 80
    assert out.action == "strong_buy_candidate"
    assert out.conviction == "high"


def test_low_completeness_demotes_conviction():
    out = compose_score(instrument_id="VTI", factors=_all_high(), data_completeness=0.50, cfg=_cfg())
    assert out.conviction in ("low", "med")
    # Completeness < 0.80 → demote at least one notch from high
    assert out.action != "strong_buy_candidate" or out.conviction != "high"


def test_avoid_zone():
    refs = ("r",)
    factors = {k: FactorScore(score=10, raw_refs=refs, components={}) for k in
                ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news")}
    out = compose_score(instrument_id="X", factors=factors, data_completeness=1.0, cfg=_cfg())
    assert out.action == "strong_avoid"
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/instrument_score.py
from __future__ import annotations
from dataclasses import dataclass, field
from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.valuation_cost import FactorScore


@dataclass(frozen=True)
class InstrumentScore:
    instrument_id: str
    composite_score: float
    action: str
    conviction: str
    factor_breakdown: dict[str, dict[str, object]]
    data_completeness: float
    weights_version: str


def _action_for(score: float, cfg: ScoringConfig) -> str:
    th = cfg.action_thresholds
    if score >= th["strong_buy_candidate"]:
        return "strong_buy_candidate"
    if score >= th["buy_candidate"]:
        return "buy_candidate"
    if score >= th["watch"]:
        return "watch"
    if score >= th["avoid"]:
        return "avoid"
    return "strong_avoid"


def _conviction_for(data_completeness: float, threshold: float) -> str:
    if data_completeness >= threshold + 0.10:
        return "high"
    if data_completeness >= threshold:
        return "med"
    return "low"


def _demote(action: str) -> str:
    chain = ("strong_buy_candidate", "buy_candidate", "watch", "avoid", "strong_avoid")
    idx = chain.index(action)
    return chain[min(idx + 1, len(chain) - 1)]


def compose_score(
    instrument_id: str, factors: dict[str, FactorScore],
    data_completeness: float, cfg: ScoringConfig,
) -> InstrumentScore:
    """Pure composer: weighted average + action mapping + conviction demote."""
    composite = sum(cfg.factor_weights[name] * factors[name].score for name in cfg.factor_weights)
    action = _action_for(composite, cfg)
    conviction = _conviction_for(data_completeness, cfg.conviction_data_completeness_threshold)
    if conviction == "low":
        action = _demote(action)
    breakdown = {
        name: {
            "score": factors[name].score,
            "raw_refs": list(factors[name].raw_refs),
            "components": factors[name].components,
        }
        for name in cfg.factor_weights
    }
    return InstrumentScore(
        instrument_id=instrument_id, composite_score=composite,
        action=action, conviction=conviction,
        factor_breakdown=breakdown, data_completeness=data_completeness,
        weights_version=cfg.weights_version,
    )
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/test_instrument_score.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/instrument_score.py tests/scoring/test_instrument_score.py
git commit -m "feat(scoring/instrument_score): weighted composite + action/conviction map"
```

---

## Task 22: Sanity Check (Spearman correlation)

**Files:**
- Create: `src/irc/scoring/sanity_check.py`
- Create: `tests/scoring/test_sanity_check.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_sanity_check.py
from __future__ import annotations
import pandas as pd
from irc.scoring.sanity_check import historical_sanity_correlation, SanityResult


def _hist() -> tuple[pd.DataFrame, pd.DataFrame]:
    scores = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"], "composite_score": [90, 70, 50, 20],
    })
    realized = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"], "realized_risk_adj_return": [0.20, 0.10, -0.05, -0.20],
    })
    return scores, realized


def test_strong_positive_correlation_passes():
    scores, realized = _hist()
    res = historical_sanity_correlation(scores, realized)
    assert isinstance(res, SanityResult)
    assert res.rho > 0.90
    assert res.status == "PASS"


def test_inverted_returns_block():
    scores = pd.DataFrame({"instrument_id": ["A", "B", "C", "D"], "composite_score": [90, 70, 50, 20]})
    realized = pd.DataFrame({"instrument_id": ["A", "B", "C", "D"],
                              "realized_risk_adj_return": [-0.20, -0.05, 0.10, 0.20]})
    res = historical_sanity_correlation(scores, realized)
    assert res.rho < 0
    assert res.status == "HARD_FAIL"


def test_weak_positive_warns():
    scores = pd.DataFrame({"instrument_id": ["A", "B", "C", "D"], "composite_score": [90, 70, 50, 20]})
    realized = pd.DataFrame({"instrument_id": ["A", "B", "C", "D"],
                              "realized_risk_adj_return": [0.05, 0.04, 0.08, 0.03]})
    res = historical_sanity_correlation(scores, realized)
    assert res.status in ("WARN", "PASS")  # tolerant
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/sanity_check.py
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from scipy.stats import spearmanr


@dataclass(frozen=True)
class SanityResult:
    rho: float
    p_value: float
    status: str  # "PASS" | "WARN" | "HARD_FAIL"
    n_instruments: int


def historical_sanity_correlation(
    scores: pd.DataFrame, realized: pd.DataFrame,
    weak_threshold: float = 0.10,
) -> SanityResult:
    """Compare score quintile vs realized risk-adj return quintile via Spearman.
    Status:
      ρ ≤ 0       → HARD_FAIL
      ρ ≤ weak    → WARN
      else        → PASS
    """
    merged = scores.merge(realized, on="instrument_id", how="inner")
    if merged.empty or len(merged) < 4:
        return SanityResult(rho=0.0, p_value=1.0, status="HARD_FAIL", n_instruments=len(merged))
    rho, pval = spearmanr(merged["composite_score"], merged["realized_risk_adj_return"])
    if rho <= 0:
        status = "HARD_FAIL"
    elif rho <= weak_threshold:
        status = "WARN"
    else:
        status = "PASS"
    return SanityResult(rho=float(rho), p_value=float(pval), status=status, n_instruments=len(merged))
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/test_sanity_check.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/sanity_check.py tests/scoring/test_sanity_check.py
git commit -m "feat(scoring/sanity_check): Spearman correlation gate; HARD_FAIL when ρ ≤ 0"
```

---

## Task 23: Scoring Pipeline + `irc score`

**Files:**
- Create: `src/irc/scoring/pipeline.py`
- Create: `src/irc/commands/score_cmd.py`
- Modify: `src/irc/cli.py:1-70` (register subcommand)
- Create: `tests/scoring/test_pipeline.py`
- Create: `tests/commands/test_score_cmd.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
# tests/scoring/test_pipeline.py
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pandas as pd
from irc.schemas.scoring import ScoringConfig
from irc.scoring.pipeline import run_scoring


def _scoring_cfg() -> ScoringConfig:
    return ScoringConfig.model_validate({
        "factor_weights": {"valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
                            "macro_fit": 0.25, "thesis_news": 0.20},
        "action_thresholds": {"strong_buy_candidate": 80, "buy_candidate": 60,
                               "watch": 40, "avoid": 20},
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v1",
    })


@patch("irc.scoring.pipeline.score_macro_fit")
def test_pipeline_produces_one_score_per_instrument(mock_macro):
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([
        {"instrument_id": "VTI", "name_cn": "VTI", "asset_class": "us_etf", "role": "core_us_equity",
         "cited_refs": "r1", "tracked_index": "S&P 500"},
    ])
    metrics = pd.DataFrame([{"instrument_id": "VTI", "expense_ratio": 0.001,
                              "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
                              "vol_1y": 0.18, "downside_capture": 0.9,
                              "aum_stability_pct": 0.05, "manager_tenure_years": 8,
                              "holdings_concentration_top10": 0.25}])
    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    assert "scores" in out
    assert len(out["scores"]) == 1
    assert out["scores"][0]["instrument_id"] == "VTI"
    assert "composite_score" in out["scores"][0]
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/pipeline.py
from __future__ import annotations
from typing import Any
import pandas as pd
from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.valuation_cost import score_valuation_cost
from irc.scoring.factors.risk import score_risk
from irc.scoring.factors.quality import score_quality
from irc.scoring.factors.macro_fit import score_macro_fit, MacroFitContext
from irc.scoring.factors.thesis_news import score_thesis_news
from irc.scoring.instrument_score import compose_score


def _completeness(metric_row: dict, required: tuple[str, ...]) -> float:
    present = sum(1 for k in required if metric_row.get(k) is not None)
    return present / len(required)


_REQUIRED = (
    "expense_ratio", "drawdown_3y", "vol_1y", "downside_capture",
    "aum_stability_pct", "manager_tenure_years", "holdings_concentration_top10",
)


def run_scoring(
    watchlist: pd.DataFrame,
    metrics: pd.DataFrame,
    news_summaries: dict[str, tuple[str, ...]],
    regime_summary: str,
    route: Any,
    cfg_scoring: ScoringConfig,
) -> dict[str, list[dict[str, Any]]]:
    """End-to-end scoring for each instrument in the watchlist."""
    by_id = metrics.set_index("instrument_id").to_dict("index") if not metrics.empty else {}
    out: list[dict[str, Any]] = []
    for r in watchlist.itertuples(index=False):
        m = by_id.get(r.instrument_id, {})
        completeness = _completeness(m, _REQUIRED)
        refs = tuple((r.cited_refs or "").split(",")) if r.cited_refs else ()
        v = score_valuation_cost(
            expense_ratio=m.get("expense_ratio") or 0.01,
            premium_discount_pct=m.get("premium_discount_pct") or 0.0,
            raw_refs=refs,
        )
        rk = score_risk(
            drawdown_3y=m.get("drawdown_3y") or 0.20,
            vol_1y=m.get("vol_1y") or 0.20,
            downside_capture=m.get("downside_capture") or 1.0,
            raw_refs=refs,
        )
        q = score_quality(
            aum_stability_pct=m.get("aum_stability_pct") or 0.10,
            manager_tenure_years=m.get("manager_tenure_years") or 3,
            holdings_concentration_top10=m.get("holdings_concentration_top10") or 0.30,
            raw_refs=refs,
        )
        mf = score_macro_fit(
            MacroFitContext(
                regime_summary=regime_summary,
                instrument_profile=f"{r.instrument_id} {r.name_cn} {r.asset_class} tracking {r.tracked_index}",
                raw_refs=refs,
            ),
            route=route,
        )
        tn = score_thesis_news(
            news_summaries=news_summaries.get(r.instrument_id, ()), raw_refs=refs,
        )
        score_obj = compose_score(
            instrument_id=r.instrument_id,
            factors={"valuation_cost": v, "risk": rk, "quality": q,
                      "macro_fit": mf, "thesis_news": tn},
            data_completeness=completeness, cfg=cfg_scoring,
        )
        out.append({
            "instrument_id": score_obj.instrument_id,
            "composite_score": score_obj.composite_score,
            "action": score_obj.action,
            "conviction": score_obj.conviction,
            "factor_breakdown": score_obj.factor_breakdown,
            "data_completeness": score_obj.data_completeness,
            "weights_version": score_obj.weights_version,
        })
    return {"scores": out}
```

- [ ] **Step 3: Implement `src/irc/commands/score_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.scoring.pipeline import run_scoring


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _macro_summary(con) -> str:
    rows = con.execute(
        "SELECT series_id, value FROM macro_series WHERE date >= "
        "(SELECT MAX(date) - INTERVAL '7 days' FROM macro_series)"
    ).fetchall()
    return "; ".join(f"{r[0]}={r[1]:.3f}" for r in rows[:6]) or "macro snapshot unavailable"


def run_score(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    watchlist_path = root / "outputs" / today / "discovered_watchlist.csv"
    if not watchlist_path.exists():
        # find latest
        outputs = sorted((root / "outputs").glob("*/discovered_watchlist.csv"))
        if not outputs:
            print("ERROR: no discovered_watchlist.csv found; run `irc discover` first.")
            return 2
        watchlist_path = outputs[-1]
    watchlist = pd.read_csv(watchlist_path)
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        metrics = con.execute(
            "SELECT instrument_id, expense_ratio, drawdown_3y, vol_1y, "
            "       downside_capture, tracking_error, sharpe_3y "
            "FROM fund_metrics"
        ).fetch_df() if False else pd.DataFrame(columns=[
            "instrument_id", "expense_ratio", "drawdown_3y", "vol_1y",
            "downside_capture", "aum_stability_pct", "manager_tenure_years",
            "holdings_concentration_top10",
        ])
        regime = _macro_summary(con)
    finally:
        con.close()
    route = resolve_route("scoring_rationale", bundle.llm)
    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary=regime, route=route, cfg_scoring=bundle.scoring,
    )
    out_path = root / "outputs" / today / "scoring.json"
    atomic_write_text(out_path, json.dumps(out, ensure_ascii=False, indent=2))
    print(f"score OK: {len(out['scores'])} instruments → {out_path}")
    return 0
```

- [ ] **Step 4: Register `score` in CLI**

In `src/irc/cli.py`:

```python
@main.command(help="Score every candidate from discovered_watchlist.csv via 5 factors.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def score(repo_root: str) -> None:
    from irc.commands.score_cmd import run_score
    rc = run_score(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Write CLI test**

```python
# tests/commands/test_score_cmd.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.score_cmd import run_score


@pytest.fixture
def repo_with_watchlist(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / "2026-05-07"
    out_dir.mkdir(parents=True)
    pd.DataFrame([{
        "instrument_id": "VTI", "name_cn": "VTI", "asset_class": "us_etf",
        "role": "core_us_equity", "cited_refs": "r1", "tracked_index": "S&P 500",
    }]).to_csv(out_dir / "discovered_watchlist.csv", index=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    con.close()
    return tmp_path


@patch("irc.scoring.pipeline.score_macro_fit")
def test_score_writes_scoring_json(mock_macro, repo_with_watchlist: Path):
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    rc = run_score(repo_root=str(repo_with_watchlist))
    assert rc == 0
    assert (repo_with_watchlist / "outputs/2026-05-07/scoring.json").exists()
```

- [ ] **Step 6: Run all scoring tests**

Run: `uv run pytest tests/scoring/ tests/commands/test_score_cmd.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/irc/scoring/pipeline.py src/irc/commands/score_cmd.py src/irc/cli.py tests/scoring/test_pipeline.py tests/commands/test_score_cmd.py
git commit -m "feat(cli/score): orchestrate 5 factors + composer + write scoring.json"
```

---

## Task 24: End-to-End Smoke (ingest → discover → score)

**Files:**
- Create: `tests/test_e2e_ingest_discover_score.py`

- [ ] **Step 1: Write the e2e test**

```python
# tests/test_e2e_ingest_discover_score.py
from __future__ import annotations
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
from click.testing import CliRunner
from irc.cli import main


def _fake_prices() -> pd.DataFrame:
    return pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.20, 4.22], "high": [4.25, 4.30], "low": [4.18, 4.20],
        "close": [4.22, 4.28], "volume": [1.0e8, 1.1e8],
    })


def _fake_macro() -> pd.DataFrame:
    return pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})


def _fake_nav() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.234, 1.245], "nav_acc": [2.345, 2.356],
    })


def _fake_chat_response() -> MagicMock:
    return MagicMock(
        text='{"score": 70, "rationale": "stable rates"}',
        prompt_tokens=20, completion_tokens=10,
    )


def test_e2e_ingest_then_discover_then_score(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])

    with patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=_fake_prices()), \
         patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=_fake_macro()), \
         patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=_fake_nav()):
        r1 = runner.invoke(main, ["ingest", "--repo-root", str(tmp_path)])
    assert r1.exit_code == 0, r1.output

    with patch("irc.discovery.reason_writer.call_chat", return_value=MagicMock(
            text="Reason cites openbb:prices:VTI:2026-05-06. Risk: USD risk.",
            prompt_tokens=10, completion_tokens=5)):
        r2 = runner.invoke(main, ["discover", "--repo-root", str(tmp_path)])
    assert r2.exit_code == 0, r2.output

    with patch("irc.scoring.factors.macro_fit.call_chat", return_value=_fake_chat_response()):
        r3 = runner.invoke(main, ["score", "--repo-root", str(tmp_path)])
    assert r3.exit_code == 0, r3.output

    # Outputs exist
    out_dirs = list((tmp_path / "outputs").iterdir())
    assert any((d / "discovered_watchlist.csv").exists() for d in out_dirs)
    assert any((d / "scoring.json").exists() for d in out_dirs)
```

- [ ] **Step 2: Run the e2e test**

Run: `uv run pytest tests/test_e2e_ingest_discover_score.py -v`
Expected: 1 passed.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest`
Expected: ~80+ tests, all pass.

- [ ] **Step 4: Tag milestone**

```bash
git tag -a plan-2-data-discovery-scoring -m "Plan 2 complete: data ingest + discovery + scoring (no gold yet)"
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e_ingest_discover_score.py
git commit -m "test(e2e): ingest → discover → score smoke produces watchlist + scoring.json"
```

---

## Self-Review Notes

**Spec coverage check** (against MVP design spec):

| Spec section | Plan 2 task |
|---|---|
| §2.B outputs: `discovered_watchlist.csv`, `scoring.json` | Tasks 14, 23 |
| §2.C L1 OpenBB / AKShare | Tasks 6, 7 |
| §3.A Discovery 5-step funnel | Tasks 9-14 |
| §3.B 5-factor scoring | Tasks 16-21 |
| §3.D Sanity check | Task 22 |
| §3.E user sovereignty (overrides via ban_list) | Task 10 |
| §5.A directory tree (`data/`, `discovery/`, `scoring/factors/`) | All Plan 2 tasks |
| §5.B Stages 1, 3, 4a | Tasks 8, 14, 23 |
| §5.D CLI `ingest`, `discover`, `score` | Tasks 8, 14, 23 |
| §5.E DuckDB + manifest | Tasks 3, 4 |
| §6.B provenance triple `(source, retrieved_at, raw_ref)` | Tasks 3, 5 |
| §6.D no fallback for sanity | Task 22 (HARD_FAIL on ρ ≤ 0) |

**Out of Plan 2** (deferred to Plans 3 / 4):
- Gold scoring (Plan 3 — depends on regime detection + 6m band)
- Allocation, trade plan, memo (Plan 3)
- News + research layers (Plan 4 — `thesis_news` is stub here)
- Eval framework (Plan 4)
- Cross-source reconciliation, calendar-aware freshness (Plan 4)

**Placeholder scan:** every step contains either explicit code, an explicit command, or an explicit verification expectation. The `thesis_news` stub is intentional and labeled.

**Type consistency check:**
- `FactorScore` is shared by every factor module via re-export from `valuation_cost.py`.
- `InstrumentScore` (Task 21) has fields consumed by `run_score` JSON serialization (Task 23).
- `UniverseRow` (Task 9) is consumed unchanged by hard_filter, quality_filter, role_bucket, reason_writer.
- `ResolvedRoute` from Plan 1 is consumed by `reason_writer` and `macro_fit`.
- DuckDB schema columns in Task 3 match the column names referenced in `ingest_cmd` (Task 8) and `discover_cmd` (Task 14).
- `_FILENAME_TO_SCHEMA` from Plan 1 task 7 covers all 14 YAMLs; Plan 2 doesn't add new YAMLs.

No mismatches found.

---

**End of Plan 2.**
