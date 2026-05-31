# Item 001 — Consensus upside + pe/pb wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a pure consensus-upside metric (`median(target_price)/latest_close − 1`) and index-level PE/PB/dividend-yield population into `OpportunityInput`, using only data the pipeline can obtain, with the metric honestly degrading to `None` today (ADR 0009).

**Architecture:** Three new pure/thin modules — a pure `consensus_upside_pct` helper, a thin `fetch_cn_index_valuation` AkShare wrapper (legulegu `stock_index_pe_lg`/`stock_index_pb_lg`) with a separate pure frame-extraction helper, and a `IndexValuation` frozen dataclass. `populate_inputs` is extended (via `dataclasses.replace`) to fill `pe_ttm`/`pb`/`dividend_yield` only when `tracked_index` is a recognised broad index, and `consensus_upside_pct` from any broker reports passed in (none carry target prices today → `None`). No classifier changes; population is provably inert.

**Tech Stack:** Python 3.12, frozen dataclasses, pandas, DuckDB, AkShare via `_ak_call` indirection, pytest (offline mocks + one double-gated live test).

---

## Source-of-truth references (read before starting)

- Spec: `docs/2026-05-31-funding-analysis/items/001-spec.md` (REFINED — honour corrected line refs, not struck-through ones).
- Binding decision: `docs/adr/0009-consensus-upside-degrade-to-none.md` (`target_price` stays `None`; metric wired but degrades).
- Resolved decisions: `docs/2026-05-31-funding-analysis/items/001-grill.md` (ratio units; index-level pe/pb; inert population).

## Verified anchors (pinned by reading the real code)

- `src/irc/fundamentals/types.py:178-185` — `BrokerReport` (`target_price: float | None` at :182).
- `src/irc/fundamentals/akshare_filing.py:27-30` — `_ak_call` indirection (reuse this exact pattern).
- `src/irc/fundamentals/akshare_filing.py:83` — `target_price=None,` site (add comment here; do NOT change behaviour).
- `src/irc/opportunity/types.py:69-114` — `OpportunityInput`; `pe_ttm`/`pb`/`dividend_yield` already declared at :92-94.
- `src/irc/opportunity/inputs_loader.py:93-137` — `populate_inputs`; `_price_series` at :43-56; final `replace(...)` at :124-137.
- `src/irc/commands/opportunity_cmd.py:532-579` — `_build_input`; skeleton built at :559, `populate_inputs` called at :579.
- `src/irc/opportunity/lookthrough.py:6-16` — `_BROAD_INDEX_DISPLAY` (9 keys); `_BROAD_INDEX_KEYS` frozenset at :61.
- `src/irc/opportunity/states.py:188-233` — `classify_valuation`; reads only `_percentile` (`valuation_percentile_self`/`_vs_benchmark`) + `earnings_yield`/`real_yield_10y` (:129-133, :218-222). Confirms pe/pb/dividend/upside are inert.
- Live-test gate template: `tests/fundamentals/test_fund_announcement_em_live.py:43-50` (`pytest.mark.live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`).
- Existing `target_price is None` assertion: `tests/fundamentals/test_akshare_fundamentals.py:372`.

## Judgment calls (made by the planner — cite the spec section)

1. **Where `populate_inputs` gets broker reports (spec AC4).** AC4 says `consensus_upside_pct` is "computed from cached broker reports for the instrument (where available)." But there is **no broker-report DuckDB table** (verified: `src/irc/data/duckdb_helper.py` defines only instruments/prices/nav_history/macro_series/fund_holdings/fund_metrics/events_log). Broker reports live only in disk-cached `ConstituentSnapshot` JSON keyed by lookthrough target — not reachable from `populate_inputs(con, ...)`. **Decision:** add an optional parameter `broker_reports: tuple[BrokerReport, ...] = ()` to `populate_inputs`; the metric is wired end-to-end and computed from whatever reports the caller passes. Today the only caller (`_build_input`) passes nothing → `()` → metric `None`. This satisfies ADR 0009 ("wired but degrades to None"), keeps the function pure-at-edges, and avoids inventing a non-existent table. A later item (003 Tushare) supplies reports with non-None `target_price` and the metric lights up with zero further wiring.

2. **Latest close for the metric (spec §Open Q2 / AC4).** Use `series.iloc[-1]` from the already-loaded `_price_series` (spec AC4 explicitly: "`series.iloc[-1]` (the latest close already loaded by `_price_series`)"). When `series` is empty → `None`.

3. **`dividend_yield` source (spec AC3).** `stock_index_pe_lg`/`stock_index_pb_lg` (legulegu) carry PE and PB but **not** dividend yield reliably. Spec AC3 lists `dividend_yield` on `IndexValuation` and AC4 wires it, but the named PE/PB endpoints do not guarantee a dividend column. **Decision:** the extraction helper probes for a dividend-yield column and returns `None` when absent (the common case for these two endpoints). `IndexValuation.dividend_yield` is therefore `None` in practice today — consistent with the degrade-to-None contract and AC4's "stay `None`" path. No third endpoint (`stock_zh_index_value_csindex`) is added; that is out of scope (spec §Non-goals keeps scope to the two named endpoints).

3. **Live-test marker (spec AC7).** Reuse the existing `pytest.mark.live_akshare` marker + `IRC_RUN_LIVE_AKSHARE=1` gate (spec AC7 explicitly permits reuse). No new marker is registered.

---

## File structure

| File | Responsibility | Create/Modify |
| --- | --- | --- |
| `src/irc/fundamentals/consensus.py` | Pure `consensus_upside_pct` helper (no I/O). | Create |
| `tests/fundamentals/test_consensus.py` | Unit tests for the pure helper. | Create |
| `src/irc/fundamentals/index_valuation_types.py` | `IndexValuation` frozen dataclass. | Create |
| `src/irc/fundamentals/akshare_index_valuation.py` | Thin `fetch_cn_index_valuation` wrapper + pure extraction helper + name map. | Create |
| `tests/fundamentals/test_akshare_index_valuation.py` | Offline unit tests (mocked `_ak_call`, fixture frames). | Create |
| `tests/fundamentals/test_index_valuation_live.py` | Single double-gated live test. | Create |
| `src/irc/opportunity/types.py` | Add `consensus_upside_pct` field to `OpportunityInput`. | Modify (`:114`) |
| `tests/opportunity/test_opportunity_input_fields.py` | Field-existence/default test. | Create |
| `src/irc/opportunity/inputs_loader.py` | Wire pe/pb/dividend + consensus upside via `replace`. | Modify (`:93-137`) |
| `tests/opportunity/test_inputs_loader.py` | Population + inertness-lock tests. | Modify (append) |
| `src/irc/fundamentals/akshare_filing.py` | Add explanatory comment at `target_price=None` (no behaviour change). | Modify (`:83`) |

---

## Task 1: Pure consensus-upside helper

**Files:**
- Create: `src/irc/fundamentals/consensus.py`
- Test: `tests/fundamentals/test_consensus.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/fundamentals/test_consensus.py`:

```python
from __future__ import annotations

import pytest

from irc.fundamentals.consensus import consensus_upside_pct
from irc.fundamentals.types import BrokerReport


def _report(target: float | None) -> BrokerReport:
    return BrokerReport(
        symbol="600519.SH",
        broker="中信证券",
        rating="买入",
        target_price=target,
        published_iso="2026-05-08",
        title="t",
    )


def test_no_reports_returns_none() -> None:
    assert consensus_upside_pct((), 100.0) is None


def test_all_targets_none_returns_none() -> None:
    reports = (_report(None), _report(None))
    assert consensus_upside_pct(reports, 100.0) is None


def test_single_target_positive_close() -> None:
    # median([120]) / 100 - 1 = 0.20 (ratio units)
    reports = (_report(120.0),)
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.20)


def test_odd_target_count_uses_middle() -> None:
    # median([90, 120, 150]) = 120 ; 120/100 - 1 = 0.20
    reports = (_report(90.0), _report(120.0), _report(150.0))
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.20)


def test_even_target_count_uses_two_middle_mean() -> None:
    # median([100, 110, 130, 160]) = (110+130)/2 = 120 ; 120/100 - 1 = 0.20
    reports = (_report(100.0), _report(110.0), _report(130.0), _report(160.0))
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.20)


def test_mixed_none_targets_ignored() -> None:
    # non-None targets [120, 80] -> median 100 ; 100/100 - 1 = 0.0
    reports = (_report(120.0), _report(None), _report(80.0))
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.0)


def test_latest_close_none_returns_none() -> None:
    assert consensus_upside_pct((_report(120.0),), None) is None


def test_latest_close_zero_returns_none() -> None:
    assert consensus_upside_pct((_report(120.0),), 0.0) is None


def test_latest_close_negative_returns_none() -> None:
    assert consensus_upside_pct((_report(120.0),), -5.0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_consensus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.fundamentals.consensus'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/fundamentals/consensus.py`:

```python
"""Pure consensus-upside metric. No I/O.

`consensus_upside_pct = median(non-None target_price) / latest_close - 1`,
in RATIO units (e.g. 0.12 = +12%), matching the `qdii_premium_pct` convention.
Returns None when no broker report carries a target price, or when
`latest_close` is missing / non-positive. See ADR 0009: this metric is wired
end-to-end but degrades to None today because the only wired broker feed
(EastMoney) drops its 目标价 column upstream — do NOT fabricate a target.
"""
from __future__ import annotations

from statistics import median

from irc.fundamentals.types import BrokerReport


def consensus_upside_pct(
    reports: tuple[BrokerReport, ...],
    latest_close: float | None,
) -> float | None:
    """Return median target / latest_close − 1, or None when undecidable."""
    if latest_close is None or latest_close <= 0:
        return None
    targets = tuple(r.target_price for r in reports if r.target_price is not None)
    if not targets:
        return None
    return median(targets) / latest_close - 1.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_consensus.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/consensus.py tests/fundamentals/test_consensus.py
git commit -m "feat(consensus): pure consensus_upside_pct helper (ratio units, degrade-to-None)"
```

---

## Task 2: `IndexValuation` frozen dataclass

**Files:**
- Create: `src/irc/fundamentals/index_valuation_types.py`
- Test: covered by Task 3's tests (the type is exercised there; no standalone test needed — YAGNI).

- [ ] **Step 1: Write the implementation**

Create `src/irc/fundamentals/index_valuation_types.py`:

```python
"""Index-level valuation snapshot type (item 001).

Frozen, immutable. All metric fields are `float | None` — every fetch path
degrades to None on failure / missing column, never raises.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexValuation:
    index_key: str
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    as_of_iso: str
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "from irc.fundamentals.index_valuation_types import IndexValuation; print(IndexValuation('csi300', 12.0, 1.3, None, '2026-05-30'))"`
Expected: prints `IndexValuation(index_key='csi300', pe_ttm=12.0, pb=1.3, dividend_yield=None, as_of_iso='2026-05-30')`.

- [ ] **Step 3: Commit**

```bash
git add src/irc/fundamentals/index_valuation_types.py
git commit -m "feat(index-valuation): IndexValuation frozen dataclass"
```

---

## Task 3: Thin index-valuation fetcher + pure extraction helper

**Files:**
- Create: `src/irc/fundamentals/akshare_index_valuation.py`
- Test: `tests/fundamentals/test_akshare_index_valuation.py`

The module has three parts: (a) a name map `_INDEX_PE_PB_NAME` (subset of `_BROAD_INDEX_DISPLAY` that legulegu resolves — start with all 9 keys; the live test in Task 4 will confirm which actually resolve, but unknown names degrade to None so over-claiming is safe); (b) a **pure** extraction helper `_extract_latest_value(df, candidate_cols)` unit-tested against fixture frames; (c) the thin `fetch_cn_index_valuation` wrapper using `_ak_call`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fundamentals/test_akshare_index_valuation.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals.akshare_index_valuation import (
    _extract_latest_value,
    fetch_cn_index_valuation,
)
from irc.fundamentals.index_valuation_types import IndexValuation


# ---------- pure extraction helper ----------

_PE_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "平均市盈率": [11.8, 11.9, 12.1],
})

_PB_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "市净率": [1.28, 1.29, 1.31],
})


def test_extract_latest_value_picks_latest_date_row() -> None:
    val = _extract_latest_value(_PE_FRAME, ("平均市盈率", "市盈率", "pe"))
    assert val == 12.1


def test_extract_latest_value_returns_none_when_no_candidate_column() -> None:
    val = _extract_latest_value(_PE_FRAME, ("市净率", "pb"))
    assert val is None


def test_extract_latest_value_returns_none_on_empty_frame() -> None:
    assert _extract_latest_value(pd.DataFrame(), ("平均市盈率",)) is None


def test_extract_latest_value_coerces_non_float_to_none() -> None:
    frame = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": ["-"]})
    assert _extract_latest_value(frame, ("平均市盈率",)) is None


# ---------- fetcher ----------

def test_fetch_unknown_index_key_returns_none_without_calling_ak() -> None:
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        out = fetch_cn_index_valuation("not_a_broad_index")
    assert out is None
    mocked.assert_not_called()


def test_fetch_recognised_index_returns_pe_and_pb() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake
    ), patch(
        "irc.fundamentals.akshare_index_valuation._today_iso",
        return_value="2026-05-31",
    ):
        out = fetch_cn_index_valuation("csi300")
    assert isinstance(out, IndexValuation)
    assert out.index_key == "csi300"
    assert out.pe_ttm == 12.1
    assert out.pb == 1.31
    assert out.dividend_yield is None  # legulegu PE/PB endpoints carry no div col
    assert out.as_of_iso == "2026-05-31"


def test_fetch_passes_chinese_name_to_ak_call() -> None:
    calls: list[dict] = []

    def _fake(fn_name, **kwargs):
        calls.append({"fn": fn_name, **kwargs})
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch("irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake):
        fetch_cn_index_valuation("csi300")
    # csi300 -> 沪深300 (from _BROAD_INDEX_DISPLAY)
    assert any(c.get("symbol") == "沪深300" for c in calls)


def test_fetch_degrades_to_none_on_adapter_exception() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        side_effect=RuntimeError("network down"),
    ):
        out = fetch_cn_index_valuation("csi300")
    assert out is None


def test_fetch_returns_valuation_with_none_metrics_on_empty_frames() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=pd.DataFrame(),
    ), patch(
        "irc.fundamentals.akshare_index_valuation._today_iso",
        return_value="2026-05-31",
    ):
        out = fetch_cn_index_valuation("csi300")
    assert isinstance(out, IndexValuation)
    assert out.pe_ttm is None
    assert out.pb is None
    assert out.dividend_yield is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.fundamentals.akshare_index_valuation'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/fundamentals/akshare_index_valuation.py`:

```python
"""Index-level PE/PB valuation fetcher (item 001) via legulegu AkShare endpoints.

`stock_index_pe_lg` (PE) and `stock_index_pb_lg` (PB) are addressed by Chinese
broad-index name (e.g. 沪深300). The instrument-level pe/pb/dividend population
this feeds is INERT today (no classifier reads it — see item 002). Network I/O
is confined to the `_ak_call` indirection; extraction is a pure helper.

Degrade-to-None contract: unknown index_key → None; any adapter failure or
empty frame → metrics None (never raises). Matches `fetch_cn_filing_digest`.

NOTE: legulegu PE/PB endpoints carry no dividend-yield column, so
`dividend_yield` is None in practice (spec §Judgment call 3). `基金概况` is
NEVER used (forbidden indicator).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.opportunity.lookthrough import _BROAD_INDEX_DISPLAY

# Subset of broad-index keys we map to a Chinese name for the legulegu endpoint.
# Unknown names degrade to None inside the helper, so reusing the full map is safe.
_INDEX_PE_PB_NAME: dict[str, str] = dict(_BROAD_INDEX_DISPLAY)

_PE_COLS: tuple[str, ...] = ("平均市盈率", "市盈率", "静态市盈率", "pe", "pe_ttm")
_PB_COLS: tuple[str, ...] = ("市净率", "平均市净率", "pb")
_DIV_COLS: tuple[str, ...] = ("股息率", "股息率%", "dividend_yield")
_DATE_COLS: tuple[str, ...] = ("日期", "date", "trade_date")


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import
    return getattr(ak, fn_name)(**kwargs)


def _today_iso() -> str:
    return date.today().isoformat()


def _latest_row(df: pd.DataFrame) -> pd.Series | None:
    """Return the row with the latest date, or the last row if no date column."""
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    if date_col is None:
        return df.iloc[-1]
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    ordered = df.assign(_d=parsed).dropna(subset=["_d"]).sort_values("_d")
    if ordered.empty:
        return None
    return ordered.iloc[-1]


def _extract_latest_value(
    df: pd.DataFrame, candidate_cols: tuple[str, ...]
) -> float | None:
    """Pure: pick the latest-date row, read the first matching column, coerce."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    col = next((c for c in candidate_cols if c in df.columns), None)
    if col is None:
        return None
    row = _latest_row(df)
    if row is None:
        return None
    try:
        value = float(row[col])
    except (TypeError, ValueError):
        return None
    return None if pd.isna(value) else value


def _fetch_frame(fn_name: str, cn_name: str) -> pd.DataFrame:
    try:
        df = _ak_call(fn_name, symbol=cn_name)
    except Exception:
        return pd.DataFrame()
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def fetch_cn_index_valuation(index_key: str) -> IndexValuation | None:
    """PE/PB for a recognised broad index; None for unknown keys."""
    cn_name = _INDEX_PE_PB_NAME.get(index_key)
    if cn_name is None:
        return None
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
    return IndexValuation(
        index_key=index_key,
        pe_ttm=_extract_latest_value(pe_df, _PE_COLS),
        pb=_extract_latest_value(pb_df, _PB_COLS),
        dividend_yield=_extract_latest_value(pe_df, _DIV_COLS),
        as_of_iso=_today_iso(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Verify no circular import**

Run: `uv run python -c "import irc.fundamentals.akshare_index_valuation; import irc.opportunity.inputs_loader; print('ok')"`
Expected: prints `ok`. (`akshare_index_valuation` imports `lookthrough`, which imports only `opportunity.types`; no cycle through `inputs_loader`.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/akshare_index_valuation.py tests/fundamentals/test_akshare_index_valuation.py
git commit -m "feat(index-valuation): fetch_cn_index_valuation + pure extraction helper"
```

---

## Task 4: Double-gated live fetcher test

**Files:**
- Create: `tests/fundamentals/test_index_valuation_live.py`

This is the single live test that pins the real legulegu column names. It is skipped under bare `pytest` (both `pytest.mark.live_akshare` marker AND `IRC_RUN_LIVE_AKSHARE=1` required).

- [ ] **Step 1: Write the live test**

Create `tests/fundamentals/test_index_valuation_live.py`:

```python
"""Live verification of legulegu index PE/PB endpoints (item 001).

Double-gated: requires BOTH the `live_akshare` marker AND
`IRC_RUN_LIVE_AKSHARE=1`. Default `pytest` skips it. This is the single point
that pins the real `stock_index_pe_lg` / `stock_index_pb_lg` column names; the
offline tests use fixtures.

Run::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare \\
        tests/fundamentals/test_index_valuation_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.index_valuation_types import IndexValuation

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]


def test_fetch_cn_index_valuation_csi300_live() -> None:
    """csi300 (沪深300) returns a real IndexValuation with a numeric PE and PB.

    If this fails with pe_ttm/pb None, the legulegu column labels differ from
    the candidate sets in akshare_index_valuation._PE_COLS / _PB_COLS — widen
    them and re-run. This is the designed pin point (spec §Open Q4).
    """
    out = fetch_cn_index_valuation("csi300")
    assert isinstance(out, IndexValuation)
    assert out.pe_ttm is not None, (
        "legulegu stock_index_pe_lg PE column not matched by _PE_COLS — "
        "inspect the live frame and widen the candidate set."
    )
    assert out.pb is not None, (
        "legulegu stock_index_pb_lg PB column not matched by _PB_COLS — "
        "inspect the live frame and widen the candidate set."
    )
    assert out.pe_ttm > 0 and out.pb > 0
    print(f"\n  ✓ csi300 live: pe={out.pe_ttm} pb={out.pb} div={out.dividend_yield}")
```

- [ ] **Step 2: Verify it is skipped under bare pytest**

Run: `uv run pytest tests/fundamentals/test_index_valuation_live.py -v`
Expected: 1 skipped (reason "set IRC_RUN_LIVE_AKSHARE=1 …").

- [ ] **Step 3: Verify the marker is registered (no unknown-marker warning)**

Run: `uv run pytest tests/fundamentals/test_index_valuation_live.py -v -W error::pytest.PytestUnknownMarkWarning`
Expected: 1 skipped, NO `PytestUnknownMarkWarning`. (The `live_akshare` marker is already registered in `pyproject.toml`/`pytest.ini` — confirm with `grep -rn "live_akshare" pyproject.toml pytest.ini setup.cfg tox.ini 2>/dev/null`. If absent, register it under `[tool.pytest.ini_options] markers` — but it is used by existing live tests so it should already exist.)

- [ ] **Step 4: Commit**

```bash
git add tests/fundamentals/test_index_valuation_live.py
git commit -m "test(index-valuation): double-gated live test for legulegu PE/PB"
```

---

## Task 5: Add `OpportunityInput.consensus_upside_pct` field

**Files:**
- Modify: `src/irc/opportunity/types.py` (append after `real_yield_10y` at `:114`)
- Test: `tests/opportunity/test_opportunity_input_fields.py`

- [ ] **Step 1: Write the failing test**

Create `tests/opportunity/test_opportunity_input_fields.py`:

```python
from __future__ import annotations

import dataclasses

from irc.opportunity.types import OpportunityInput


def test_consensus_upside_pct_field_exists_and_defaults_none() -> None:
    inp = OpportunityInput(
        instrument_id="600519",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
    )
    assert inp.consensus_upside_pct is None


def test_consensus_upside_pct_is_float_or_none_field() -> None:
    fields = {f.name: f for f in dataclasses.fields(OpportunityInput)}
    assert "consensus_upside_pct" in fields
    # Ratio units (median/close - 1) per ADR 0009 / CONTEXT.md "Valuation inputs".
    assert "float" in str(fields["consensus_upside_pct"].type)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_opportunity_input_fields.py -v`
Expected: FAIL — `AttributeError: 'OpportunityInput' object has no attribute 'consensus_upside_pct'`.

- [ ] **Step 3: Add the field**

In `src/irc/opportunity/types.py`, change the end of `OpportunityInput` (currently lines 113-114):

```python
    earnings_yield: float | None = None
    real_yield_10y: float | None = None
```

to:

```python
    earnings_yield: float | None = None
    real_yield_10y: float | None = None
    # Item 001: median(non-None broker target_price) / latest_close − 1, in
    # RATIO units (0.12 = +12%), matching qdii_premium_pct. None today because
    # no wired broker feed carries target prices (ADR 0009). NOT ThesisEvidence;
    # no classifier reads it (inert until item 002). See CONTEXT.md
    # "Valuation inputs".
    consensus_upside_pct: float | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_opportunity_input_fields.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify no existing constructor broke**

Run: `uv run pytest tests/opportunity -v`
Expected: PASS (the new field has a default, so every existing `OpportunityInput(...)` call stays valid).

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/types.py tests/opportunity/test_opportunity_input_fields.py
git commit -m "feat(opportunity): add OpportunityInput.consensus_upside_pct (ratio units)"
```

---

## Task 6: Wire pe/pb/dividend + consensus upside into `populate_inputs`

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py` (`:93-137`)
- Test: `tests/opportunity/test_inputs_loader.py` (append)

Wiring rules (spec AC4):
- `pe_ttm`/`pb`/`dividend_yield` ← `fetch_cn_index_valuation(skeleton.tracked_index)` **only when** `tracked_index` is a recognised broad-index key (`_BROAD_INDEX_KEYS`); else all three stay `None`.
- `consensus_upside_pct` ← `consensus_upside_pct(broker_reports, latest_close)` where `latest_close = series.iloc[-1]` if `series` non-empty else `None`. `broker_reports` is a new optional parameter (default `()`) — see Judgment call 1. Today the caller passes nothing → metric `None`.

To stay within the file/function size budget, extract a small pure-ish helper `_index_valuation_metrics(tracked_index, fetch)` that returns `(pe, pb, div)`, with `fetch` defaulted to `fetch_cn_index_valuation` so tests can stub it without patching.

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_inputs_loader.py` (imports at top — add `from irc.fundamentals.index_valuation_types import IndexValuation`, `from irc.opportunity import inputs_loader`, `from irc.fundamentals.types import BrokerReport`, `from irc.opportunity.states import classify_valuation`):

```python
def _seed_csi300_instrument_with_prices(con) -> None:
    con.execute(
        "INSERT INTO instruments VALUES "
        "('510300','510300','cn_on_exchange','沪深300ETF',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 5.0e10, NULL, 6.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:510300')"
    )
    base = date(2025, 1, 1)
    rows = [
        ("510300", date.fromordinal(base.toordinal() + i), 100.0, 100.0, 100.0, 100.0, 1.0)
        for i in range(300)
    ]
    con.executemany(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:510300')",
        rows,
    )


def _stub_index_valuation(index_key, *, fetch=None):  # noqa: ARG001
    return IndexValuation(
        index_key="csi300", pe_ttm=12.1, pb=1.31, dividend_yield=None,
        as_of_iso="2026-05-31",
    )


def test_populate_inputs_fills_pe_pb_for_recognised_broad_index(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "csi.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    skeleton = OpportunityInput(
        instrument_id="510300",
        asset_class="cn_etf",
        market="cn_on_exchange",
        tracked_index="csi300",
        name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm == 12.1
    assert inp.pb == 1.31
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_unrecognised_index(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "unk.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('159999','159999','cn_on_exchange','某主题ETF',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 1.0e9, NULL, 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:159999')"
    )

    def _boom(index_key, *, fetch=None):  # noqa: ARG001
        raise AssertionError("fetch must NOT be called for an unrecognised index")

    monkeypatch.setattr(inputs_loader, "fetch_cn_index_valuation", _boom)
    skeleton = OpportunityInput(
        instrument_id="159999",
        asset_class="cn_etf",
        market="cn_on_exchange",
        tracked_index="some_sector_theme",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None
    assert inp.pb is None
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_gold_and_bond(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "gold.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('518880','518880','cn_on_exchange','黄金ETF',NULL,'gold','cny',"
        " DATE '2020-01-01', 0.005, 5.0e10, NULL, 6.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:518880')"
    )
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetch for gold")),
    )
    skeleton = OpportunityInput(
        instrument_id="518880",
        asset_class="gold",
        market="cn_on_exchange",
        tracked_index=None,
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None and inp.pb is None and inp.dividend_yield is None
    con.close()


def test_populate_inputs_consensus_upside_none_with_no_broker_reports(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "noupside.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.consensus_upside_pct is None  # no reports passed → None (ADR 0009)
    con.close()


def test_populate_inputs_consensus_upside_computed_when_reports_carry_targets(
    tmp_path, monkeypatch
):
    con = duckdb.connect(str(tmp_path / "upside.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)  # latest close == 100.0
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    reports = (
        BrokerReport("510300", "中信", "买入", 120.0, "2026-05-08", "t"),
        BrokerReport("510300", "中金", "增持", 100.0, "2026-05-07", "t"),
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    inp = populate_inputs(
        con, skeleton, holding_entry_date=None, broker_reports=reports
    )
    # median([120, 100]) = 110 ; 110/100 - 1 = 0.10
    assert inp.consensus_upside_pct == pytest.approx(0.10)
    con.close()


def test_population_is_inert_classify_valuation_byte_identical(tmp_path, monkeypatch):
    """AC4 inertness lock: classify_valuation output is byte-identical whether
    or not pe/pb/dividend/consensus_upside are populated — proving population
    changes no state until item 002 wires these fields."""
    con = duckdb.connect(str(tmp_path / "inert.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    reports = (BrokerReport("510300", "中信", "买入", 120.0, "2026-05-08", "t"),)

    populated = populate_inputs(
        con, skeleton, holding_entry_date=None, broker_reports=reports
    )
    # Same row with pe/pb/dividend/consensus_upside forced back to None.
    import dataclasses
    bare = dataclasses.replace(
        populated, pe_ttm=None, pb=None, dividend_yield=None,
        consensus_upside_pct=None,
    )
    assert populated.pe_ttm is not None  # guard: population actually happened
    assert classify_valuation(populated) == classify_valuation(bare)
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -v -k "pe_pb or consensus or inert"`
Expected: FAIL — `populate_inputs` has no `broker_reports` kwarg / `inputs_loader` has no `fetch_cn_index_valuation` attribute / pe_ttm is None.

- [ ] **Step 3: Wire the implementation**

In `src/irc/opportunity/inputs_loader.py`:

(a) Add imports near the top (after the existing `from irc.opportunity.types import OpportunityInput` at :14):

```python
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.consensus import consensus_upside_pct
from irc.fundamentals.types import BrokerReport
from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS
```

(b) Add a helper above `populate_inputs` (after `_cn_bond_yield_percentile`, before `:93`):

```python
def _index_valuation_metrics(
    tracked_index: str | None,
) -> tuple[float | None, float | None, float | None]:
    """Return (pe_ttm, pb, dividend_yield) for a recognised broad index, else
    (None, None, None). Index valuation is INERT today (item 002 consumes it)."""
    key = (tracked_index or "").strip().lower() or None
    if key is None or key not in _BROAD_INDEX_KEYS:
        return None, None, None
    valuation = fetch_cn_index_valuation(key)
    if valuation is None:
        return None, None, None
    return valuation.pe_ttm, valuation.pb, valuation.dividend_yield
```

(c) Change the `populate_inputs` signature (currently :93-98) to add the `broker_reports` parameter:

```python
def populate_inputs(
    con: duckdb.DuckDBPyConnection,
    skeleton: OpportunityInput,
    *,
    holding_entry_date: date | None,
    broker_reports: tuple[BrokerReport, ...] = (),
) -> OpportunityInput:
    """Return a copy of skeleton with evidence fields filled from DuckDB.

    `broker_reports` (default empty) feeds the consensus-upside metric; today
    no wired feed carries target prices, so the metric degrades to None
    (ADR 0009). Index pe/pb/dividend are populated only for recognised broad
    indices and are inert until item 002.
    """
```

(d) Compute the new metrics inside `populate_inputs` (after the `series`/`bond_yield_pct` block, before the final `return replace(...)` at :124):

```python
    latest_close = float(series.iloc[-1]) if not series.empty else None
    upside = consensus_upside_pct(broker_reports, latest_close)
    pe_ttm, pb, dividend_yield = _index_valuation_metrics(skeleton.tracked_index)
```

(e) Extend the final `replace(...)` call (currently :124-137) to set the four new fields:

```python
    return replace(
        skeleton,
        expense_ratio=meta.get("expense_ratio"),
        aum_cny=meta.get("aum_cny"),
        manager_tenure_years=meta.get("manager_tenure_years"),
        tracking_error=tracking_err,
        ret_1m=returns["ret_1m"],
        ret_3m=returns["ret_3m"],
        ret_6m=returns["ret_6m"],
        ret_12m=returns["ret_12m"],
        valuation_percentile_self=percentile,
        drawdown_since_entry=dd,
        cn_bond_yield_percentile=bond_yield_pct,
        pe_ttm=pe_ttm,
        pb=pb,
        dividend_yield=dividend_yield,
        consensus_upside_pct=upside,
    )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -v`
Expected: PASS (all existing + 6 new tests pass).

- [ ] **Step 5: Verify line budget**

Run: `uv run python -c "print(sum(1 for _ in open('src/irc/opportunity/inputs_loader.py')))"`
Expected: a number < 200. (If it exceeds 200, move `_index_valuation_metrics` into `akshare_index_valuation.py` and import it — but with the helper it should land near ~165.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py tests/opportunity/test_inputs_loader.py
git commit -m "feat(inputs): wire pe/pb/dividend + consensus upside into populate_inputs (inert)"
```

---

## Task 7: Document why `target_price` stays None (no behaviour change)

**Files:**
- Modify: `src/irc/fundamentals/akshare_filing.py:83`

Spec AC5: keep the EastMoney `target_price=None` honest; add a comment recording *why* and pointing at the consumer + ADR 0009. The existing assertion at `tests/fundamentals/test_akshare_fundamentals.py:372` must stay green — do NOT change the value.

- [ ] **Step 1: Add the explanatory comment**

In `src/irc/fundamentals/akshare_filing.py`, change (current :83 inside the `BrokerReport(...)` constructor):

```python
            target_price=None,
```

to:

```python
            # No 目标价 column in EastMoney's stock_research_report_em
            # (indvAimPriceT/L dropped upstream). Stays None by contract — do
            # NOT fabricate. Consumed by irc.fundamentals.consensus
            # .consensus_upside_pct, which degrades to None. See
            # docs/adr/0009-consensus-upside-degrade-to-none.md.
            target_price=None,
```

- [ ] **Step 2: Verify the existing assertion still passes**

Run: `uv run pytest tests/fundamentals/test_akshare_fundamentals.py -v -k broker`
Expected: PASS (including `test_fetch_cn_broker_reports_happy_path_returns_recent_first` whose `target_price is None` assertion at :372 is unchanged).

- [ ] **Step 3: Commit**

```bash
git add src/irc/fundamentals/akshare_filing.py
git commit -m "docs(broker): record why target_price stays None (ADR 0009)"
```

---

## Task 8: Forbidden-indicator + whole-stage verification

**Files:** none (verification only).

- [ ] **Step 1: Confirm `基金概况` is not referenced in new production code**

Run: `grep -rn "基金概况" src/irc/fundamentals/consensus.py src/irc/fundamentals/akshare_index_valuation.py src/irc/fundamentals/index_valuation_types.py src/irc/opportunity/inputs_loader.py`
Expected: NO matches (exit code 1). The acceptance grep test stays green.

- [ ] **Step 2: Run the full affected test scope (spec AC6)**

Run: `uv run pytest tests/fundamentals tests/opportunity -q`
Expected: PASS, no failures. (Live test in Task 4 shows as skipped.)

- [ ] **Step 3: Lint (spec AC6)**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 4: Confirm new files are within the size budget**

Run: `uv run python -c "import pathlib; [print(p, sum(1 for _ in open(p))) for p in ['src/irc/fundamentals/consensus.py','src/irc/fundamentals/index_valuation_types.py','src/irc/fundamentals/akshare_index_valuation.py','src/irc/opportunity/inputs_loader.py']]"`
Expected: every count < 200.

- [ ] **Step 5: Full no-network suite sanity (optional but recommended)**

Run: `uv run pytest -q -m "not live_akshare and not live_llm"`
Expected: PASS. Confirms no collateral breakage (e.g. every existing `OpportunityInput(...)` and `populate_inputs(...)` caller still valid because the new field/param have defaults).

- [ ] **Step 6: Final commit (if any verification-only fixes were needed)**

If steps 1-5 required no source change, skip. Otherwise:

```bash
git add -A
git commit -m "test(item-001): verification fixes"
```

---

## Self-review checklist (run before declaring done)

- [ ] **Spec coverage:**
  - AC1 (pure `consensus_upside_pct`) → Task 1. *(Note: spec AC1 names the module `src/irc/fundamentals/consensus.py` and signature `consensus_upside_pct(reports, latest_close)` — implemented exactly.)*
  - AC2 (`OpportunityInput.consensus_upside_pct` default None) → Task 5.
  - AC3 (`fetch_cn_index_valuation` + `IndexValuation` + pure extraction helper) → Tasks 2-3.
  - AC4 (wire pe/pb/dividend + upside; recognised-index gate; inertness lock) → Task 6.
  - AC5 (`target_price` stays None + comment) → Task 7.
  - AC6 (no-network suite + ruff + size budget) → Task 8.
  - AC7 (double-gated live test) → Task 4.
- [ ] **Placeholder scan:** no TBD/TODO; every code step shows real code.
- [ ] **Type consistency:** `consensus_upside_pct` (function and field) spelled identically; `fetch_cn_index_valuation`/`IndexValuation`/`_extract_latest_value`/`_index_valuation_metrics` names match across Tasks 3 and 6; `broker_reports` kwarg spelled identically in Task 6 signature and tests.
- [ ] **Immutability:** all new types frozen; `populate_inputs` returns via `replace` (no mutation).
- [ ] **No new citations:** zero `ThesisEvidence` emitted; pe/pb/upside are plain scalars (spec §Constraints).
```
