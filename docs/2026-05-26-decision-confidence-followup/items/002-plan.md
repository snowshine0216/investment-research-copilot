# Item 002 — QDII premium-to-NAV fetcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire an AkShare premium-to-NAV fetcher (`fund_etf_spot_em`) into the scoring pass so the 8 currently-blocked QDII rows (3 on-exchange + 5 off-exchange) are scored against a real premium ratio; introduce a new `qdii_premium_too_high` gate distinct from the existing `qdii_premium_unknown`; consolidate `_QDII_ASSET_CLASSES` into a single home; raise the threshold default to `0.05` per the grill.

**Architecture:** Three-layer split — pure adapter (`src/irc/data/akshare_client.py::fetch_qdii_premium_pct` + `_fetch_full_etf_spot_table` lru_cache), pure router (`src/irc/scoring/qdii_premium.py::qdii_premium_for_row` + canonical `_QDII_ASSET_CLASSES`), command-layer composer (`src/irc/commands/score_cmd.py` builds the resolver and threads it into `run_scoring`). Gate plumbing in `decision/gates.py` gains the new `qdii_premium_too_high` parameter alongside the existing `qdii_premium_unknown`; `decide_row` learns the `qdii_max_premium_pct` threshold; `decision/report.py` gets label + remediation entries and the AC22 rewrite of the `qdii_premium_unknown` text. The memo-stage twin `_decision_status_for_pick` in `commands/memo_cmd.py` mirrors the gate update and reads the threshold from `DiscoveryConfig`.

**Tech Stack:** Python 3.12 / pandas / AkShare 1.18.63 / pydantic-settings / pytest / uv. TDD red→green→refactor throughout.

---

## File Structure

### New files
- `src/irc/scoring/qdii_premium.py` — pure router + canonical `_QDII_ASSET_CLASSES` constant + `qdii_premium_for_row` routing helper. Target: < 60 LOC.
- `tests/scoring/test_qdii_premium.py` — pure-helper tests, off-exchange synthetic-zero branch, end-to-end 8-instrument smoke.
- `tests/fixtures/akshare/fund_etf_spot_em.json` — column-shadow capture of AkShare's bulk ETF spot table.

### Modified files
- `src/irc/data/akshare_client.py` — add `_fetch_full_etf_spot_table` (lru_cache(maxsize=1)) + `fetch_qdii_premium_pct`. Target: < 40 LOC delta.
- `src/irc/scoring/pipeline.py` — accept optional `qdii_premium_resolver` parameter; stamp `qdii_premium_pct` on QDII rows.
- `src/irc/commands/score_cmd.py` — build resolver from fetcher + routing helper; pass into `run_scoring`.
- `src/irc/decision/gates.py` — add `qdii_premium_too_high` parameter to `compute_blocking_reasons`; thread `qdii_max_premium_pct` into `decide_row`; replace local `_QDII_ASSET_CLASSES` with import.
- `src/irc/commands/memo_cmd.py` — mirror the gate update; read threshold from `DiscoveryConfig`; replace local import.
- `src/irc/memo/diagnostics.py` — replace local `_QDII_ASSET_CLASSES` with import.
- `src/irc/allocation/target_weights.py` — replace local `_QDII_ASSET_CLASSES` with import.
- `src/irc/decision/report.py` — add `qdii_premium_too_high` label + remediation; rewrite the `qdii_premium_unknown` remediation per AC22.
- `src/irc/schemas/discovery.py` — add `QDII_MAX_PREMIUM_DEFAULT: Final[float] = 0.05` + new `HardFilters.qdii_max_premium_pct` field.
- `config/discovery.yaml` — add `qdii_max_premium_pct: 0.05` under `hard_filters`.
- `tests/data/test_akshare_client.py` — unit + live tests for `fetch_qdii_premium_pct`.
- `tests/decision/test_gates.py` — new `qdii_premium_too_high` tests; unchanged-when-healthy regression.
- `tests/decision/test_three_section_markdown.py` — render-in-blocked-section test for the new code.

---

## Task 1: Canonical `_QDII_ASSET_CLASSES` constant (consolidation prep)

**Files:**
- Create: `src/irc/scoring/qdii_premium.py`
- Test: `tests/scoring/test_qdii_premium.py`

- [ ] **Step 1.1: Write the failing test for the constant**

Create `tests/scoring/test_qdii_premium.py`:

```python
from __future__ import annotations

from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES


def test_qdii_asset_classes_is_frozenset_with_three_members() -> None:
    """_QDII_ASSET_CLASSES is the canonical immutable set; consumers import it."""
    assert isinstance(_QDII_ASSET_CLASSES, frozenset)
    assert _QDII_ASSET_CLASSES == frozenset({"us_etf", "hk_etf", "qdii_global"})
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `uv run pytest tests/scoring/test_qdii_premium.py::test_qdii_asset_classes_is_frozenset_with_three_members -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.scoring.qdii_premium'`.

- [ ] **Step 1.3: Create the new module with just the constant**

Create `src/irc/scoring/qdii_premium.py`:

```python
"""QDII premium-to-NAV routing helper.

Pure-routing layer that sits between the effectful AkShare adapter
(`src/irc/data/akshare_client.py::fetch_qdii_premium_pct`) and the
scoring pipeline. Decides for each watchlist row whether to invoke
the fetcher, return a synthetic zero (off-exchange feeders that
transact at NAV by construction), or skip the field entirely
(non-QDII rows).

See CONTEXT.md "QDII premium-to-NAV" and ADR 0002 §5 F6.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Final


# Canonical home for the QDII asset-class set. Previously triplicated in
# decision/gates.py, memo/diagnostics.py, allocation/target_weights.py;
# now imported from here (AC21).
_QDII_ASSET_CLASSES: Final[frozenset[str]] = frozenset(
    {"us_etf", "hk_etf", "qdii_global"}
)
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `uv run pytest tests/scoring/test_qdii_premium.py::test_qdii_asset_classes_is_frozenset_with_three_members -v`
Expected: PASS.

- [ ] **Step 1.5: Commit**

```bash
git add src/irc/scoring/qdii_premium.py tests/scoring/test_qdii_premium.py
git commit -m "$(cat <<'EOF'
feat(002): seed scoring/qdii_premium with canonical _QDII_ASSET_CLASSES

Introduces the new home for QDII routing helpers. Step 1 in the AC21
consolidation: the constant moves here first; the three existing call
sites are swapped to import in a later task.
EOF
)"
```

---

## Task 2: Pure `qdii_premium_for_row` router

**Files:**
- Modify: `src/irc/scoring/qdii_premium.py`
- Test: `tests/scoring/test_qdii_premium.py`

- [ ] **Step 2.1: Write the failing tests for the router**

Append to `tests/scoring/test_qdii_premium.py`:

```python
import pytest

from irc.scoring.qdii_premium import qdii_premium_for_row


class _StubFetcher:
    """Records calls so tests can assert the fetcher is/isn't invoked."""

    def __init__(self, return_value: float | None = 0.0292) -> None:
        self.return_value = return_value
        self.calls: list[str] = []

    def __call__(self, symbol: str) -> float | None:
        self.calls.append(symbol)
        return self.return_value


def test_returns_none_for_non_qdii_asset_class() -> None:
    """Non-QDII rows must not stamp the field — fetcher must not be called."""
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="cn_equity_fund",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="000001",
    )
    assert out is None
    assert fetcher.calls == []


def test_returns_zero_for_qdii_off_exchange_without_calling_fetcher() -> None:
    """Off-exchange QDII feeders transact at NAV; synthetic 0.0 is correct."""
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="017641",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_returns_zero_for_qdii_global_off_exchange() -> None:
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="qdii_global",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="019547",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_returns_zero_for_hk_etf_off_exchange() -> None:
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="hk_etf",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="161716",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_invokes_fetcher_for_qdii_on_exchange_us_etf() -> None:
    fetcher = _StubFetcher(return_value=0.0292)
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="513650",
    )
    assert out == 0.0292
    assert fetcher.calls == ["513650"]


def test_invokes_fetcher_for_qdii_on_exchange_hk_etf() -> None:
    fetcher = _StubFetcher(return_value=0.0079)
    out = qdii_premium_for_row(
        asset_class="hk_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="159691",
    )
    assert out == 0.0079
    assert fetcher.calls == ["159691"]


def test_propagates_none_from_fetcher() -> None:
    """When AkShare returns no row, the resolver propagates None."""
    fetcher = _StubFetcher(return_value=None)
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="999999",
    )
    assert out is None
    assert fetcher.calls == ["999999"]
```

- [ ] **Step 2.2: Run the new tests to verify they fail**

Run: `uv run pytest tests/scoring/test_qdii_premium.py -v -k "non_qdii or off_exchange or on_exchange or propagates"`
Expected: ALL FAIL with `ImportError: cannot import name 'qdii_premium_for_row'`.

- [ ] **Step 2.3: Implement `qdii_premium_for_row`**

Append to `src/irc/scoring/qdii_premium.py`:

```python
def qdii_premium_for_row(
    asset_class: str,
    market: str,
    fetcher: Callable[[str], float | None],
    symbol: str,
) -> float | None:
    """Pure routing helper for QDII premium-to-NAV.

    Returns:
      - ``None`` when ``asset_class`` is not a QDII class (non-QDII rows
        must not stamp the field).
      - ``0.0`` when the row is a QDII off-exchange feeder
        (open-ended LOF/FOF units transact at NAV by construction;
        the secondary-market premium concept does not apply).
      - ``fetcher(symbol)`` otherwise (QDII on-exchange ETFs).

    The fetcher is the only effectful boundary; this function is pure.
    """
    if asset_class not in _QDII_ASSET_CLASSES:
        return None
    if market == "cn_off_exchange":
        return 0.0
    return fetcher(symbol)
```

- [ ] **Step 2.4: Run the router tests to verify they pass**

Run: `uv run pytest tests/scoring/test_qdii_premium.py -v`
Expected: ALL PASS (8 tests so far).

- [ ] **Step 2.5: Commit**

```bash
git add src/irc/scoring/qdii_premium.py tests/scoring/test_qdii_premium.py
git commit -m "$(cat <<'EOF'
feat(002): add pure qdii_premium_for_row routing helper

Routes QDII watchlist rows by (asset_class, market):
- non-QDII → None (field omitted)
- QDII off-exchange → 0.0 synthetic (feeders transact at NAV)
- QDII on-exchange → fetcher(symbol)

Pure function; fetcher injected; off-exchange branch must NOT call the
fetcher. Eight unit tests cover all three branches plus the
fetcher-returns-None propagation case.
EOF
)"
```

---

## Task 3: AkShare bulk-table fixture + `_fetch_full_etf_spot_table`

**Files:**
- Create: `tests/fixtures/akshare/fund_etf_spot_em.json`
- Modify: `src/irc/data/akshare_client.py`
- Test: `tests/data/test_akshare_client.py`

- [ ] **Step 3.1: Create the column-shadow fixture**

Create `tests/fixtures/akshare/fund_etf_spot_em.json`. This is the column-shadow capture of `ak.fund_etf_spot_em()` — a list of row dicts. Contents below cover: a premium case (513650 → -2.92 → 2.92% premium ratio), a discount case (159691 → +0.79 → -0.79% premium), a near-zero case (513690 → -0.22 → 0.22% premium), and an unrelated row.

```json
[
  {
    "代码": "513650",
    "名称": "全球医药",
    "最新价": 1.234,
    "IOPV实时估值": 1.199,
    "基金折价率": -2.92
  },
  {
    "代码": "159691",
    "名称": "港股医疗",
    "最新价": 0.512,
    "IOPV实时估值": 0.508,
    "基金折价率": 0.79
  },
  {
    "代码": "513690",
    "名称": "纳指生科",
    "最新价": 1.005,
    "IOPV实时估值": 1.003,
    "基金折价率": -0.22
  },
  {
    "代码": "510300",
    "名称": "沪深300ETF",
    "最新价": 4.123,
    "IOPV实时估值": 4.120,
    "基金折价率": -0.07
  }
]
```

- [ ] **Step 3.2: Write the failing test for `fetch_qdii_premium_pct` happy path (premium)**

Append to `tests/data/test_akshare_client.py`:

```python
import json
from pathlib import Path


_FUND_ETF_SPOT_EM_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "akshare" / "fund_etf_spot_em.json"
)


def _load_etf_spot_fixture_df() -> pd.DataFrame:
    rows = json.loads(_FUND_ETF_SPOT_EM_FIXTURE.read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


def test_fetch_qdii_premium_pct_returns_signed_ratio_for_premium_case() -> None:
    """基金折价率=-2.92 (discount-positive native) → premium ratio +0.0292."""
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.return_value = _load_etf_spot_fixture_df()
            out = fetch_qdii_premium_pct("513650")
        assert out == pytest.approx(0.0292)
        assert mocked.call_args[0][0] == "fund_etf_spot_em"
    finally:
        _fetch_full_etf_spot_table.cache_clear()
```

- [ ] **Step 3.3: Run the test to verify it fails**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_returns_signed_ratio_for_premium_case -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_qdii_premium_pct'`.

- [ ] **Step 3.4: Implement `_fetch_full_etf_spot_table` + `fetch_qdii_premium_pct`**

Append to `src/irc/data/akshare_client.py` (place near `_fetch_full_etf_table` so the file's structure stays grouped):

```python
def _raw_etf_spot_table_call() -> pd.DataFrame:
    """Raw call to akshare for the bulk ETF spot table. Extracted for lru_cache wrapping."""
    return _ak_call("fund_etf_spot_em")


@lru_cache(maxsize=1)
def _fetch_full_etf_spot_table() -> pd.DataFrame:
    """Master bulk ETF spot table from EastMoney (one snapshot per pipeline run).

    Source of `基金折价率` (discount-rate, percent units) used by
    ``fetch_qdii_premium_pct``. Decorated with ``lru_cache(maxsize=1)`` so
    every QDII symbol in a single ``irc run`` shares ONE AkShare call.

    Test isolation: callers MUST invoke ``_fetch_full_etf_spot_table.cache_clear()``
    in fixture teardown — same pattern as ``_fetch_full_fund_table`` and
    ``_fetch_full_etf_table``.
    """
    return _raw_etf_spot_table_call()


def fetch_qdii_premium_pct(symbol: str) -> float | None:
    """Single-symbol premium-to-NAV ratio for a QDII feeder ETF.

    Returns a **signed** float in ratio units (positive = trading **above**
    NAV; negative = trading **below** NAV / discount). Computed as
    ``-(基金折价率) / 100.0`` because AkShare's native column is
    discount-positive.

    Degrade-to-``None`` on any failure: AkShare exception, empty table,
    missing required columns (`代码` or `基金折价率`), or symbol not in the
    table (mirrors ``fetch_fund_nav_report``'s contract per ADR 0002 §5).

    Dispatches through ``_fetch_full_etf_spot_table`` so all QDII symbols
    in one pipeline run share a single AkShare call (1 against
    ``IRC_FETCH_BUDGET``).
    """
    try:
        df = _fetch_full_etf_spot_table()
    except Exception:
        return None
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if "代码" not in df.columns or "基金折价率" not in df.columns:
        return None
    normalized = _normalize_fund_code(symbol)
    codes = df["代码"].astype(str).map(_normalize_fund_code)
    matches = df[codes == normalized]
    if matches.empty:
        return None
    raw = matches.iloc[0]["基金折价率"]
    try:
        return -(float(raw)) / 100.0
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 3.5: Run the premium test to verify it passes**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_returns_signed_ratio_for_premium_case -v`
Expected: PASS.

- [ ] **Step 3.6: Commit**

```bash
git add src/irc/data/akshare_client.py tests/data/test_akshare_client.py tests/fixtures/akshare/fund_etf_spot_em.json
git commit -m "$(cat <<'EOF'
feat(002): fetch_qdii_premium_pct + lru_cache bulk-table accessor

Adds the only effectful entry point for QDII premium values.
_fetch_full_etf_spot_table is lru_cache(maxsize=1) so all QDII symbols
share one AkShare call per run (+1 vs IRC_FETCH_BUDGET=2000).
Sign flip: AkShare's 基金折价率 is discount-positive; adapter returns
signed premium = -(基金折价率)/100.

Includes the column-shadow fixture (fund_etf_spot_em.json) and a happy-
path test for the premium case (-2.92 → +0.0292).
EOF
)"
```

---

## Task 4: Fetcher resilience — discount, missing-symbol, missing-column, empty, exception

**Files:**
- Test: `tests/data/test_akshare_client.py`

- [ ] **Step 4.1: Write the failing resilience tests**

Append to `tests/data/test_akshare_client.py`:

```python
def test_fetch_qdii_premium_pct_returns_negative_ratio_for_discount_case() -> None:
    """基金折价率=+0.79 (true discount) → premium ratio -0.0079."""
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.return_value = _load_etf_spot_fixture_df()
            out = fetch_qdii_premium_pct("159691")
        assert out == pytest.approx(-0.0079)
    finally:
        _fetch_full_etf_spot_table.cache_clear()


def test_fetch_qdii_premium_pct_returns_none_for_missing_symbol() -> None:
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.return_value = _load_etf_spot_fixture_df()
            out = fetch_qdii_premium_pct("999999")
        assert out is None
    finally:
        _fetch_full_etf_spot_table.cache_clear()


def test_fetch_qdii_premium_pct_returns_none_for_missing_required_column() -> None:
    """Schema drift: 基金折价率 column missing → degrade to None."""
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        fake = pd.DataFrame({"代码": ["513650"], "最新价": [1.234]})
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.return_value = fake
            out = fetch_qdii_premium_pct("513650")
        assert out is None
    finally:
        _fetch_full_etf_spot_table.cache_clear()


def test_fetch_qdii_premium_pct_returns_none_for_empty_table() -> None:
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.return_value = pd.DataFrame()
            out = fetch_qdii_premium_pct("513650")
        assert out is None
    finally:
        _fetch_full_etf_spot_table.cache_clear()


def test_fetch_qdii_premium_pct_returns_none_on_akshare_exception() -> None:
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.side_effect = ConnectionError("EastMoney unreachable")
            out = fetch_qdii_premium_pct("513650")
        assert out is None
    finally:
        _fetch_full_etf_spot_table.cache_clear()


def test_fetch_qdii_premium_pct_uses_bulk_table_once_for_many_symbols() -> None:
    """All QDII symbols in one run share ONE AkShare call (lru_cache contract)."""
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        with patch("irc.data.akshare_client._ak_call") as mocked:
            mocked.return_value = _load_etf_spot_fixture_df()
            a = fetch_qdii_premium_pct("513650")
            b = fetch_qdii_premium_pct("159691")
            c = fetch_qdii_premium_pct("513690")
        assert a == pytest.approx(0.0292)
        assert b == pytest.approx(-0.0079)
        assert c == pytest.approx(0.0022)
        # ONE AkShare call regardless of how many symbols asked.
        assert mocked.call_count == 1
    finally:
        _fetch_full_etf_spot_table.cache_clear()
```

- [ ] **Step 4.2: Run the resilience tests**

Run: `uv run pytest tests/data/test_akshare_client.py -v -k "qdii_premium_pct"`
Expected: ALL 6 PASS (the implementation from Task 3 already covers these — they're the spec's locked contracts).

- [ ] **Step 4.3: Commit**

```bash
git add tests/data/test_akshare_client.py
git commit -m "$(cat <<'EOF'
test(002): resilience tests for fetch_qdii_premium_pct

Covers: discount sign (基金折价率 positive → premium negative), missing
symbol, missing required column (schema drift), empty DataFrame,
AkShare exception, and the lru_cache "one call for many symbols"
contract.

Every test calls _fetch_full_etf_spot_table.cache_clear() in
teardown (AC20 isolation contract).
EOF
)"
```

---

## Task 5: Live AkShare test (double-gated)

**Files:**
- Test: `tests/data/test_akshare_client.py`

- [ ] **Step 5.1: Add the double-gated live test**

Append to `tests/data/test_akshare_client.py`:

```python
import os as _os_live  # local alias so we don't shadow other imports


@pytest.mark.live_akshare
@pytest.mark.skipif(
    _os_live.environ.get("IRC_RUN_LIVE_AKSHARE") != "1",
    reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
)
def test_fetch_qdii_premium_pct_live() -> None:
    """Live: at least one of {159691, 513690, 513650} returns a sane float.

    Sanity bound (-1.0, 1.0): premium values outside ±100% indicate a parser
    error (the column should never be that large in normal markets).
    """
    from irc.data.akshare_client import (
        _fetch_full_etf_spot_table,
        fetch_qdii_premium_pct,
    )
    _fetch_full_etf_spot_table.cache_clear()
    try:
        symbols = ("159691", "513690", "513650")
        results = {s: fetch_qdii_premium_pct(s) for s in symbols}
        floats = [v for v in results.values() if isinstance(v, float)]
        assert floats, f"no float returned for any of {symbols}: {results!r}"
        for v in floats:
            assert -1.0 < v < 1.0, f"premium {v!r} outside ±100% sanity bound"
    finally:
        _fetch_full_etf_spot_table.cache_clear()
```

- [ ] **Step 5.2: Confirm the live test SKIPS under default invocation**

Run: `uv run pytest tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_live -v`
Expected: SKIPPED with reason `set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests`.

- [ ] **Step 5.3: Commit**

```bash
git add tests/data/test_akshare_client.py
git commit -m "$(cat <<'EOF'
test(002): live double-gated test for fetch_qdii_premium_pct

pytest.mark.live_akshare + module-level skipif on IRC_RUN_LIVE_AKSHARE.
Asserts at least one of the three on-exchange QDII tickers returns a
float in (-1.0, 1.0). Default pytest invocations skip silently.
EOF
)"
```

---

## Task 6: Add `QDII_MAX_PREMIUM_DEFAULT` and `qdii_max_premium_pct` to discovery schema + YAML

**Files:**
- Modify: `src/irc/schemas/discovery.py`
- Modify: `config/discovery.yaml`
- Test: `tests/schemas/test_discovery.py`

- [ ] **Step 6.1: Write the failing schema test**

Append to `tests/schemas/test_discovery.py`:

```python
def test_hard_filters_qdii_max_premium_pct_default_is_qdii_max_premium_default():
    """AC9: default field value is the named Final constant 0.05."""
    from irc.schemas.discovery import HardFilters, QDII_MAX_PREMIUM_DEFAULT
    assert QDII_MAX_PREMIUM_DEFAULT == 0.05
    raw = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
    }
    cfg = HardFilters.model_validate(raw)
    assert cfg.qdii_max_premium_pct == QDII_MAX_PREMIUM_DEFAULT


def test_hard_filters_qdii_max_premium_pct_rejects_negative():
    from irc.schemas.discovery import HardFilters
    raw = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
        "qdii_max_premium_pct": -0.01,
    }
    with pytest.raises(ValidationError):
        HardFilters.model_validate(raw)


def test_hard_filters_qdii_max_premium_pct_accepts_yaml_override():
    from irc.schemas.discovery import HardFilters
    raw = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
        "qdii_max_premium_pct": 0.08,
    }
    cfg = HardFilters.model_validate(raw)
    assert cfg.qdii_max_premium_pct == 0.08
```

- [ ] **Step 6.2: Run schema tests to verify they fail**

Run: `uv run pytest tests/schemas/test_discovery.py -v -k qdii_max_premium`
Expected: FAIL with `ImportError: cannot import name 'QDII_MAX_PREMIUM_DEFAULT'`.

- [ ] **Step 6.3: Add the constant + field to the schema**

Edit `src/irc/schemas/discovery.py` — replace the file contents with:

```python
from __future__ import annotations

from typing import Final

from pydantic import Field, model_validator

from ._types import FrozenModel


# AC9: named Final constant so the magic number has a name (mirrors
# FOREIGN_HEAVY_THRESHOLD in policy_b.py). YAML key stays lowercase per
# existing config convention; the constant lives at module scope so
# downstream consumers can introspect the default without instantiating.
QDII_MAX_PREMIUM_DEFAULT: Final[float] = 0.05


class HardFilters(FrozenModel):
    inception_years_min: int = Field(ge=0)
    cn_fund_aum_cny_min: float = Field(ge=0)
    us_etf_aum_usd_min: float = Field(ge=0)
    cn_active_expense_ratio_max: float = Field(ge=0, le=1)
    cn_passive_expense_ratio_max: float = Field(ge=0, le=1)
    us_etf_expense_ratio_max: float = Field(ge=0, le=1)
    qdii_feeder_expense_ratio_max: float = Field(default=0.012, ge=0, le=1)
    etf_daily_volume_cny_min: float = Field(ge=0)
    qdii_max_premium_pct: float = Field(
        default=QDII_MAX_PREMIUM_DEFAULT, ge=0, le=1
    )


class QualityFilters(FrozenModel):
    drawdown_3y_buffer: float = Field(gt=0)
    drawdown_3y_buffer_by_asset_class: dict[str, float] = Field(default_factory=dict)
    tracking_error_max: float = Field(ge=0, le=1)
    manager_tenure_years_min: float = Field(ge=0)


class RoleBucketConfig(FrozenModel):
    min_candidates_per_role: int = Field(gt=0)
    fail_below: int = Field(ge=0)

    @model_validator(mode="after")
    def _fail_below_lt_min(self) -> "RoleBucketConfig":
        if self.fail_below >= self.min_candidates_per_role:
            raise ValueError(
                f"fail_below ({self.fail_below}) must be < min_candidates_per_role ({self.min_candidates_per_role})"
            )
        return self


class DiscoveryConfig(FrozenModel):
    hard_filters: HardFilters
    quality_filters: QualityFilters
    role_bucket: RoleBucketConfig
```

- [ ] **Step 6.4: Add the YAML key under `hard_filters`**

Edit `config/discovery.yaml`. Add a new line after `etf_daily_volume_cny_min: 10000000`:

```yaml
  # AC9 (item 002): premium-to-NAV ceiling for QDII feeders (ratio units).
  # 0.05 matches CONTEXT.md's "QDII feeders frequently trade 5–15% above NAV".
  # Strict-greater comparison (`premium > threshold` blocks; boundary admits).
  qdii_max_premium_pct: 0.05
```

- [ ] **Step 6.5: Run schema tests + config-loader smoke**

Run: `uv run pytest tests/schemas/test_discovery.py tests/test_config_loader.py -v`
Expected: ALL PASS. The existing `test_discovery_config_default` still passes because `qdii_max_premium_pct` has a default.

- [ ] **Step 6.6: Verify `irc config validate` passes**

Run: `uv run irc config validate`
Expected: exit 0; printed message confirms every YAML validated.

- [ ] **Step 6.7: Commit**

```bash
git add src/irc/schemas/discovery.py config/discovery.yaml tests/schemas/test_discovery.py
git commit -m "$(cat <<'EOF'
feat(002): add qdii_max_premium_pct config knob (default 0.05)

QDII_MAX_PREMIUM_DEFAULT: Final[float] = 0.05 in schemas/discovery.py;
HardFilters.qdii_max_premium_pct = Field(default=QDII_MAX_PREMIUM_DEFAULT,
ge=0, le=1). Mirrors FOREIGN_HEAVY_THRESHOLD's naming pattern from item
001. YAML key added under hard_filters with comment block.
EOF
)"
```

---

## Task 7: Consolidate `_QDII_ASSET_CLASSES` across three call sites (AC21)

**Files:**
- Modify: `src/irc/decision/gates.py`
- Modify: `src/irc/memo/diagnostics.py`
- Modify: `src/irc/allocation/target_weights.py`
- Modify: `src/irc/commands/memo_cmd.py` (already imports from `decision.gates`; just relocate)
- Test: `tests/scoring/test_qdii_premium.py`

- [ ] **Step 7.1: Write a failing acceptance test for the single-definition invariant**

Append to `tests/scoring/test_qdii_premium.py`:

```python
def test_qdii_asset_classes_defined_exactly_once_in_src() -> None:
    """AC21: the constant lives in qdii_premium.py only; other modules import."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "grep", "-l", "_QDII_ASSET_CLASSES.*=.*frozenset", "src/"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    matching_files = [
        line for line in result.stdout.strip().splitlines() if line
    ]
    assert matching_files == ["src/irc/scoring/qdii_premium.py"], (
        f"_QDII_ASSET_CLASSES must be defined in exactly one file, found: {matching_files!r}"
    )
```

- [ ] **Step 7.2: Run the invariant test to verify it fails**

Run: `uv run pytest tests/scoring/test_qdii_premium.py::test_qdii_asset_classes_defined_exactly_once_in_src -v`
Expected: FAIL — `_QDII_ASSET_CLASSES` is currently defined in `decision/gates.py`, `memo/diagnostics.py`, `allocation/target_weights.py`, and `scoring/qdii_premium.py` (four sites).

- [ ] **Step 7.3: Swap `decision/gates.py` to import**

In `src/irc/decision/gates.py`, replace the local definition:

```python
_QDII_ASSET_CLASSES = {"us_etf", "hk_etf", "qdii_global"}
```

with the import (place at top of file, after the existing imports):

```python
from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES
```

Delete the prose comment that hung above the local definition. The file's other behaviour is unchanged.

- [ ] **Step 7.4: Swap `memo/diagnostics.py` to import**

In `src/irc/memo/diagnostics.py`, replace:

```python
_QDII_ASSET_CLASSES: frozenset[str] = frozenset({"us_etf", "hk_etf", "qdii_global"})
```

with:

```python
from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES
```

(Place the import at the top of the file alongside the other imports; remove the line and its preceding comment block.)

- [ ] **Step 7.5: Swap `allocation/target_weights.py` to import**

In `src/irc/allocation/target_weights.py`, replace:

```python
_QDII_ASSET_CLASSES: frozenset[str] = frozenset({"us_etf", "hk_etf", "qdii_global"})
```

with:

```python
from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES
```

- [ ] **Step 7.6: Confirm `memo_cmd.py` already gets the constant transitively**

`src/irc/commands/memo_cmd.py` already imports `_QDII_ASSET_CLASSES` from `irc.decision.gates` (line ~42 per the grep). That re-export keeps working because `decision.gates` now imports the constant from the new home, but make the import explicit — change the existing line:

```python
from irc.decision.gates import (
    ...,
    _QDII_ASSET_CLASSES,
    ...,
)
```

to import directly from the new module:

```python
from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES
```

(Keep the other names imported from `irc.decision.gates`; delete only `_QDII_ASSET_CLASSES` from that import block.)

- [ ] **Step 7.7: Run the invariant test + full suite to verify green**

Run: `uv run pytest tests/scoring/test_qdii_premium.py tests/decision/test_gates.py tests/memo/ tests/allocation/ -v`
Expected: ALL PASS (the constant is now defined once, three modules import it, gate / memo / allocation tests stay green).

- [ ] **Step 7.8: Commit**

```bash
git add src/irc/decision/gates.py src/irc/memo/diagnostics.py src/irc/allocation/target_weights.py src/irc/commands/memo_cmd.py tests/scoring/test_qdii_premium.py
git commit -m "$(cat <<'EOF'
refactor(002): consolidate _QDII_ASSET_CLASSES into scoring/qdii_premium

AC21 — moves the canonical home from three drift-prone sites
(decision/gates, memo/diagnostics, allocation/target_weights) to a
single import-from-shared module. Type unified to frozenset (was a
plain set in decision/gates).

A new acceptance test asserts the constant is defined in exactly one
file via git grep — guards against future re-introduction.
EOF
)"
```

---

## Task 8: `qdii_premium_too_high` parameter on `compute_blocking_reasons`

**Files:**
- Modify: `src/irc/decision/gates.py`
- Test: `tests/decision/test_gates.py`

- [ ] **Step 8.1: Write the failing test for the new blocking reason**

Append to `tests/decision/test_gates.py`:

```python
def test_compute_blocking_reasons_emits_qdii_premium_too_high() -> None:
    """AC8: when the qdii_premium_too_high flag is True, the code lands in reasons."""
    from irc.decision.gates import compute_blocking_reasons

    reasons = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=1.0,
        completeness_threshold=0.8,
        target_weight_valid=True,
        venue_status="direct",
        evidence_status="evidence_linked",
        score_action="buy_candidate",
        qdii_premium_unknown=False,
        qdii_premium_too_high=True,
    )
    assert reasons == ["qdii_premium_too_high"]


def test_compute_blocking_reasons_qdii_premium_too_high_default_is_false() -> None:
    """Existing call sites stay working (default False)."""
    from irc.decision.gates import compute_blocking_reasons

    reasons = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=1.0,
        completeness_threshold=0.8,
        target_weight_valid=True,
        venue_status="direct",
        evidence_status="evidence_linked",
        score_action="buy_candidate",
        qdii_premium_unknown=False,
    )
    assert reasons == []
```

- [ ] **Step 8.2: Run the new tests to verify failure**

Run: `uv run pytest tests/decision/test_gates.py -v -k "qdii_premium_too_high"`
Expected: FAIL with `TypeError: compute_blocking_reasons() got an unexpected keyword argument 'qdii_premium_too_high'`.

- [ ] **Step 8.3: Add the parameter to `compute_blocking_reasons`**

Edit `src/irc/decision/gates.py`. Change the signature of `compute_blocking_reasons` from:

```python
def compute_blocking_reasons(
    pipeline_halted: bool,
    completeness: float,
    completeness_threshold: float,
    target_weight_valid: bool,
    venue_status: VenueStatus,
    evidence_status: str,
    score_action: str,
    qdii_premium_unknown: bool = False,
    excluded_from_opportunity: bool = False,
) -> list[str]:
```

to:

```python
def compute_blocking_reasons(
    pipeline_halted: bool,
    completeness: float,
    completeness_threshold: float,
    target_weight_valid: bool,
    venue_status: VenueStatus,
    evidence_status: str,
    score_action: str,
    qdii_premium_unknown: bool = False,
    excluded_from_opportunity: bool = False,
    qdii_premium_too_high: bool = False,
) -> list[str]:
```

In the body, append the new branch after `qdii_premium_unknown` and before `excluded_from_opportunity`:

```python
    if qdii_premium_too_high:
        reasons.append("qdii_premium_too_high")
```

- [ ] **Step 8.4: Run the new tests to verify they pass + full gate suite for regression**

Run: `uv run pytest tests/decision/test_gates.py -v`
Expected: ALL PASS (new tests green + every existing gate test still green).

- [ ] **Step 8.5: Commit**

```bash
git add src/irc/decision/gates.py tests/decision/test_gates.py
git commit -m "$(cat <<'EOF'
feat(002): compute_blocking_reasons gains qdii_premium_too_high

New kwarg (default False) emits the qdii_premium_too_high blocking
reason — peer of the existing qdii_premium_unknown. Existing call sites
stay green because the parameter has a default.
EOF
)"
```

---

## Task 9: Thread `qdii_max_premium_pct` through `decide_row` and compute the boolean

**Files:**
- Modify: `src/irc/decision/gates.py`
- Test: `tests/decision/test_gates.py`

- [ ] **Step 9.1: Write the failing tests for `decide_row`**

Append to `tests/decision/test_gates.py`:

```python
def test_qdii_buy_with_premium_above_threshold_blocks() -> None:
    """AC15: QDII buy_candidate with premium > qdii_max_premium_pct → blocked."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.10),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "blocked"
    assert "qdii_premium_too_high" in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_buy_with_premium_at_threshold_admits_boundary() -> None:
    """AC15: premium == threshold passes (strict-greater comparison)."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.05),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_buy_with_healthy_premium_passes() -> None:
    """AC15: small positive premium below threshold admits; no QDII code fires."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.01),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_off_exchange_synthetic_zero_passes() -> None:
    """qdii_premium_pct=0.0 (off-exchange synthetic) clears both QDII codes."""
    decision = decide_row(
        score=_score(asset_class="us_etf", qdii_premium_pct=0.0),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_premium_unknown_unchanged_when_premium_is_none() -> None:
    """Regression: the existing qdii_premium_unknown branch still fires."""
    decision = decide_row(
        score=_score(asset_class="us_etf"),  # no qdii_premium_pct
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert decision["decision_status"] == "blocked"
    assert "qdii_premium_unknown" in decision["blocking_reasons"]
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]


def test_non_qdii_premium_above_threshold_is_ignored() -> None:
    """Non-QDII rows with arbitrary qdii_premium_pct must not trigger either code."""
    decision = decide_row(
        score=_score(asset_class="cn_equity_fund", qdii_premium_pct=0.99),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
    assert "qdii_premium_unknown" not in decision["blocking_reasons"]


def test_qdii_watch_action_with_high_premium_does_not_block() -> None:
    """Only BUY actions trigger the QDII premium gate."""
    decision = decide_row(
        score=_score(asset_class="us_etf", action="watch", qdii_premium_pct=0.10),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        qdii_max_premium_pct=0.05,
    )
    assert "qdii_premium_too_high" not in decision["blocking_reasons"]
```

- [ ] **Step 9.2: Run the tests to verify failure**

Run: `uv run pytest tests/decision/test_gates.py -v -k "qdii_buy_with_premium or qdii_off_exchange_synthetic or qdii_premium_unknown_unchanged or non_qdii_premium_above or qdii_watch_action_with_high"`
Expected: FAIL with `TypeError: decide_row() got an unexpected keyword argument 'qdii_max_premium_pct'`.

- [ ] **Step 9.3: Add `qdii_max_premium_pct` to `decide_row` and compute the boolean**

Edit `src/irc/decision/gates.py`. Add the import for the default at the top of the file:

```python
from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT
```

Change the `decide_row` signature — add `qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT` to the keyword-only block, right after `excluded_from_opportunity`:

```python
def decide_row(
    score: dict[str, Any],
    allocation_selected: bool,
    target_weight_valid: bool,
    trade: dict[str, Any] | None,
    pipeline_halted: bool,
    memo_traceability_coverage: float,
    completeness_threshold: float = MIN_BUY_COMPLETENESS,
    *,
    venue_required: list[str] | tuple[str, ...] | None = None,
    available_venues: list[str] | tuple[str, ...] | set[str] | None = None,
    proxy_id: str | None = None,
    instrument_name: str | None = None,
    target_weight: float = 0.0,
    role: str = "",
    excluded_from_opportunity: bool = False,
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
) -> dict[str, Any]:
```

In the body, replace the existing `qdii_premium_unknown = (...)` block with the mutual-exclusion pair:

```python
    raw_premium = score.get("qdii_premium_pct")
    try:
        premium_value = float(raw_premium) if raw_premium is not None else None
    except (TypeError, ValueError):
        premium_value = None
    is_qdii_buy = (
        asset_class in _QDII_ASSET_CLASSES
        and score_action in _BUY_ACTIONS
    )
    qdii_premium_unknown = is_qdii_buy and premium_value is None
    qdii_premium_too_high = (
        is_qdii_buy
        and premium_value is not None
        and premium_value > qdii_max_premium_pct
    )
```

Then pass `qdii_premium_too_high` into `compute_blocking_reasons`:

```python
    blocking_reasons = _blocking_reasons(
        pipeline_halted=pipeline_halted,
        completeness=completeness,
        completeness_threshold=completeness_threshold,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        evidence_status=evidence_status,
        score_action=score_action,
        qdii_premium_unknown=qdii_premium_unknown,
        qdii_premium_too_high=qdii_premium_too_high,
        excluded_from_opportunity=excluded_from_opportunity,
    )
```

- [ ] **Step 9.4: Run the tests to verify they pass**

Run: `uv run pytest tests/decision/test_gates.py -v`
Expected: ALL PASS (new + existing). The existing `test_qdii_buy_with_premium_passes_qdii_gate` (premium=0.05) still passes because `0.05 > 0.05` is False — at-boundary admission.

- [ ] **Step 9.5: Commit**

```bash
git add src/irc/decision/gates.py tests/decision/test_gates.py
git commit -m "$(cat <<'EOF'
feat(002): decide_row computes qdii_premium_too_high vs threshold

Thread qdii_max_premium_pct (default QDII_MAX_PREMIUM_DEFAULT=0.05) into
decide_row. The pair (qdii_premium_unknown, qdii_premium_too_high) is
mutually exclusive: unknown when premium is None, too_high when premium
> threshold. Strict-greater so the boundary case (premium == threshold)
admits, mirroring FOREIGN_HEAVY_THRESHOLD precedent.

Six new tests cover above-threshold (blocks), at-boundary (admits),
healthy (admits), off-exchange synthetic 0.0 (admits), None
(unchanged unknown path), and non-QDII (ignored).
EOF
)"
```

---

## Task 10: `compose_decision_report` passes the threshold through to `decide_row`

**Files:**
- Modify: `src/irc/decision/report.py`
- Modify: `src/irc/commands/decision_cmd.py`
- Test: `tests/decision/test_gates.py` (smoke via report)

- [ ] **Step 10.1: Write a failing integration smoke test through `compose_decision_report`**

Append to `tests/decision/test_three_section_markdown.py` (this file already imports the compose function — keep the pattern):

```python
def test_qdii_premium_too_high_renders_in_blocked_section():
    """AC17: a buy_candidate QDII row with premium > threshold lands in the
    blocked section with the new label + remediation."""
    report = compose_decision_report(
        date="2026-05-26",
        scoring={"scores": [{
            "instrument_id": "513650", "asset_class": "us_etf",
            "action": "buy_candidate", "conviction": "med",
            "data_completeness": 1.0, "missing_data": [],
            "qdii_premium_pct": 0.10,
        }]},
        allocation={"selected_instruments": [
            {"instrument_id": "513650", "target_weight": 0.2}
        ], "diagnostics": {"total_weight": 1.0}},
        trade_plan={"trades": [
            {"target": "513650", "asset_class": "us_etf",
             "venue_compatible": True, "proxy_id": None,
             "target_weight": 0.2}
        ]},
        memo_traceability={"n_refs_quoted_verbatim": 1, "n_refs_provided": 1},
        pipeline_halted=False,
        qdii_max_premium_pct=0.05,
    )
    md = render_decision_markdown(report)
    section = md.split("## Blocked — fixable today", 1)[1].split("\n## ", 1)[0]
    assert "QDII premium-to-NAV above threshold" in section
```

- [ ] **Step 10.2: Run the test to verify failure**

Run: `uv run pytest tests/decision/test_three_section_markdown.py::test_qdii_premium_too_high_renders_in_blocked_section -v`
Expected: FAIL with `TypeError: compose_decision_report() got an unexpected keyword argument 'qdii_max_premium_pct'`.

- [ ] **Step 10.3: Thread `qdii_max_premium_pct` through `compose_decision_report` and `_build_rows`**

Edit `src/irc/decision/report.py`. Add to the `compose_decision_report` signature (after `opportunity_state_by_id`):

```python
    qdii_max_premium_pct: float | None = None,
```

Add the import at top of file:

```python
from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT
```

Inside `compose_decision_report`, just before the `_build_rows(...)` call, resolve the effective value:

```python
    threshold = (
        QDII_MAX_PREMIUM_DEFAULT
        if qdii_max_premium_pct is None
        else qdii_max_premium_pct
    )
```

Pass `threshold` through to `_build_rows`:

```python
    rows = _build_rows(
        scoring, selected_ids, trades_by_target, target_weight_valid,
        pipeline_halted, coverage,
        venue_requirements_by_id=venue_requirements_by_id or {},
        available_venues=available_venues,
        proxies_by_id=proxies_by_id or {},
        names_by_id=names_by_id or {},
        target_weight_by_id=target_weight_by_id,
        role_by_id=role_by_id,
        opportunity_published_ids=opportunity_published_ids,
        trade_plan_targets={str(t.get("target")) for t in trade_plan.get("trades", [])},
        qdii_max_premium_pct=threshold,
    )
```

Add `qdii_max_premium_pct: float` to the `_build_rows` signature (the function lower in the same file). In the `decide_row(...)` call inside `_build_rows`, append `qdii_max_premium_pct=qdii_max_premium_pct,`.

- [ ] **Step 10.4: Thread the threshold from `decision_cmd.py`**

Edit `src/irc/commands/decision_cmd.py`. After loading the bundle (around line 205), pass the threshold into `compose_decision_report`. Add this kwarg in the call (around line 226):

```python
        qdii_max_premium_pct=bundle.discovery.hard_filters.qdii_max_premium_pct,
```

If the load_repo_configs call fails (the existing except block), the kwarg becomes `qdii_max_premium_pct=QDII_MAX_PREMIUM_DEFAULT` — add the import at top:

```python
from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT
```

And in the except branch initialise a local:

```python
    try:
        bundle = load_repo_configs(root)
        venue_reqs, available_venues = _venue_maps_from_bundle(bundle, root)
        names = _names_from_bundle(bundle)
        qdii_max_premium = bundle.discovery.hard_filters.qdii_max_premium_pct
    except Exception as exc:  # noqa: BLE001 — graceful degrade
        print(f"WARNING: could not load venue context ({exc}); falling back to unknown venue for rows without trades.")
        venue_reqs, available_venues, names = {}, [], {}
        qdii_max_premium = QDII_MAX_PREMIUM_DEFAULT
```

Then in the `compose_decision_report` call:

```python
        qdii_max_premium_pct=qdii_max_premium,
```

- [ ] **Step 10.5: Run the smoke test + full decision suite**

Run: `uv run pytest tests/decision/ -v`
Expected: ALL PASS. The new `test_qdii_premium_too_high_renders_in_blocked_section` will still fail at the assertion `"QDII premium-to-NAV above threshold" in section` because the label is added in the next task — keep this expected. **However**, the report compose call no longer errors; the test failure is now an assertion miss, not a TypeError.

- [ ] **Step 10.6: Commit**

```bash
git add src/irc/decision/report.py src/irc/commands/decision_cmd.py tests/decision/test_three_section_markdown.py
git commit -m "$(cat <<'EOF'
feat(002): compose_decision_report threads qdii_max_premium_pct

decision_cmd reads HardFilters.qdii_max_premium_pct from the loaded
DiscoveryConfig and passes it through compose_decision_report → _build_rows
→ decide_row. Falls back to QDII_MAX_PREMIUM_DEFAULT when the bundle
fails to load (existing graceful-degrade branch).
EOF
)"
```

---

## Task 11: Decision-report label + remediation for `qdii_premium_too_high`

**Files:**
- Modify: `src/irc/decision/report.py`
- Test: `tests/decision/test_three_section_markdown.py`

- [ ] **Step 11.1: Confirm the failing assertion from Task 10**

Run: `uv run pytest tests/decision/test_three_section_markdown.py::test_qdii_premium_too_high_renders_in_blocked_section -v`
Expected: FAIL with `assert "QDII premium-to-NAV above threshold" in section`.

- [ ] **Step 11.2: Add the label + remediation**

Edit `src/irc/decision/report.py`. In `_BLOCKING_REASON_LABEL` (the dict around line 409), add a new entry between `qdii_premium_unknown` and `opportunity_excluded`:

```python
    "qdii_premium_too_high": "QDII premium-to-NAV above threshold",
```

In `_BLOCKING_REMEDIATION` (around line 420), add:

```python
    "qdii_premium_too_high":
        "QDII premium-to-NAV exceeds the configured ceiling "
        "(qdii_max_premium_pct in config/discovery.yaml; default 5%). "
        "Wait for the premium to normalise or use an alternative venue.",
```

- [ ] **Step 11.3: Run the markdown test to verify it passes**

Run: `uv run pytest tests/decision/test_three_section_markdown.py -v`
Expected: ALL PASS (the new test green; existing `test_qdii_premium_unknown_renders_in_blocked_section` still green).

- [ ] **Step 11.4: Commit**

```bash
git add src/irc/decision/report.py
git commit -m "$(cat <<'EOF'
feat(002): label + remediation for qdii_premium_too_high

AC11: surface the new blocking reason in the decision report markdown
with a static remediation that names the qdii_max_premium_pct knob and
the operator's two responses (wait for normalisation / alternative
venue).
EOF
)"
```

---

## Task 12: Wire the resolver into `run_scoring` and stamp `qdii_premium_pct`

**Files:**
- Modify: `src/irc/scoring/pipeline.py`
- Test: `tests/scoring/test_qdii_premium.py`

- [ ] **Step 12.1: Write the failing test — pipeline stamps `qdii_premium_pct` for QDII rows**

Append to `tests/scoring/test_qdii_premium.py`:

```python
from unittest.mock import MagicMock, patch

import pandas as pd

from irc.schemas.scoring import ScoringConfig


def _scoring_cfg() -> ScoringConfig:
    return ScoringConfig.model_validate({
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 80, "buy_candidate": 60,
            "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v1",
    })


@patch("irc.scoring.pipeline.score_macro_fit")
def test_run_scoring_stamps_qdii_premium_pct_when_resolver_provided(
    mock_macro,
) -> None:
    """AC6: run_scoring invokes the resolver per QDII row and stamps the result."""
    from irc.scoring.pipeline import run_scoring
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([
        {"instrument_id": "513650", "name_cn": "全球医药", "asset_class": "us_etf",
         "market": "cn_on_exchange", "role": "core_us_equity",
         "cited_refs": "r1", "tracked_index": ""},
        {"instrument_id": "000001", "name_cn": "华夏成长", "asset_class": "cn_equity_fund",
         "market": "cn_off_exchange", "role": "core_cn_equity",
         "cited_refs": "r2", "tracked_index": ""},
    ])
    metrics = pd.DataFrame([
        {"instrument_id": "513650", "expense_ratio": 0.006,
         "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
         "vol_1y": 0.18, "downside_capture": 0.9,
         "aum_stability_pct": 0.05, "manager_tenure_years": 8,
         "holdings_concentration_top10": 0.25},
        {"instrument_id": "000001", "expense_ratio": 0.015,
         "premium_discount_pct": 0.0, "drawdown_3y": 0.20,
         "vol_1y": 0.20, "downside_capture": 1.0,
         "aum_stability_pct": 0.05, "manager_tenure_years": 5,
         "holdings_concentration_top10": 0.30},
    ])
    resolver_calls: list[tuple[str, str, str]] = []

    def fake_resolver(asset_class: str, market: str, symbol: str) -> float | None:
        resolver_calls.append((asset_class, market, symbol))
        if asset_class == "us_etf":
            return 0.0292
        return None

    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
        qdii_premium_resolver=fake_resolver,
    )
    by_id = {s["instrument_id"]: s for s in out["scores"]}
    assert by_id["513650"]["qdii_premium_pct"] == pytest.approx(0.0292)
    assert "qdii_premium_pct" not in by_id["000001"]
    assert resolver_calls == [("us_etf", "cn_on_exchange", "513650")]


@patch("irc.scoring.pipeline.score_macro_fit")
def test_run_scoring_omits_qdii_premium_pct_when_no_resolver(mock_macro) -> None:
    """No resolver → no qdii_premium_pct key (back-compat)."""
    from irc.scoring.pipeline import run_scoring
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([{
        "instrument_id": "513650", "name_cn": "全球医药", "asset_class": "us_etf",
        "market": "cn_on_exchange", "role": "core_us_equity",
        "cited_refs": "r1", "tracked_index": "",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "513650", "expense_ratio": 0.006,
        "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
        "vol_1y": 0.18, "downside_capture": 0.9,
        "aum_stability_pct": 0.05, "manager_tenure_years": 8,
        "holdings_concentration_top10": 0.25,
    }])
    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
    )
    assert "qdii_premium_pct" not in out["scores"][0]


@patch("irc.scoring.pipeline.score_macro_fit")
def test_run_scoring_omits_qdii_premium_pct_when_resolver_returns_none(
    mock_macro,
) -> None:
    """Resolver returning None → key absent (existing serialiser convention)."""
    from irc.scoring.pipeline import run_scoring
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    watchlist = pd.DataFrame([{
        "instrument_id": "513650", "name_cn": "全球医药", "asset_class": "us_etf",
        "market": "cn_on_exchange", "role": "core_us_equity",
        "cited_refs": "r1", "tracked_index": "",
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "513650", "expense_ratio": 0.006,
        "premium_discount_pct": 0.0, "drawdown_3y": 0.15,
        "vol_1y": 0.18, "downside_capture": 0.9,
        "aum_stability_pct": 0.05, "manager_tenure_years": 8,
        "holdings_concentration_top10": 0.25,
    }])
    out = run_scoring(
        watchlist=watchlist, metrics=metrics, news_summaries={},
        regime_summary="x", route=MagicMock(),
        cfg_scoring=_scoring_cfg(),
        qdii_premium_resolver=lambda ac, mk, sym: None,
    )
    assert "qdii_premium_pct" not in out["scores"][0]
```

- [ ] **Step 12.2: Run the tests to verify failure**

Run: `uv run pytest tests/scoring/test_qdii_premium.py -v -k "run_scoring_stamps or run_scoring_omits"`
Expected: FAIL with `TypeError: run_scoring() got an unexpected keyword argument 'qdii_premium_resolver'`.

- [ ] **Step 12.3: Add the resolver parameter to `run_scoring`**

Edit `src/irc/scoring/pipeline.py`. Add the import at top:

```python
from collections.abc import Callable
```

Change the `run_scoring` signature — add at end of the parameter list:

```python
def run_scoring(
    watchlist: pd.DataFrame,
    metrics: pd.DataFrame,
    news_summaries: dict[str, tuple[str, ...]],
    regime_summary: str,
    route: Any,
    cfg_scoring: ScoringConfig,
    qdii_premium_resolver: Callable[[str, str, str], float | None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
```

In the per-row loop (the `for r in rows:` block), after `tn = score_thesis_news(...)` and the `compose_score(...)` call, change the score-row construction to optionally include `qdii_premium_pct`. Replace the `out.append({...})` block at the end of the loop with:

```python
        score_row: dict[str, Any] = {
            "instrument_id": score_obj.instrument_id,
            "composite_score": score_obj.composite_score,
            "action": score_obj.action,
            "conviction": score_obj.conviction,
            "factor_breakdown": score_obj.factor_breakdown,
            "data_completeness": score_obj.data_completeness,
            "missing_data": missing_data,
            "weights_version": score_obj.weights_version,
        }
        if qdii_premium_resolver is not None:
            row_market = str(market or "")
            row_asset_class = str(asset_class or "")
            premium = qdii_premium_resolver(
                row_asset_class, row_market, str(r.instrument_id)
            )
            if premium is not None:
                score_row["qdii_premium_pct"] = premium
        out.append(score_row)
```

- [ ] **Step 12.4: Run the scoring tests to verify they pass + full scoring suite for regression**

Run: `uv run pytest tests/scoring/ -v`
Expected: ALL PASS.

- [ ] **Step 12.5: Commit**

```bash
git add src/irc/scoring/pipeline.py tests/scoring/test_qdii_premium.py
git commit -m "$(cat <<'EOF'
feat(002): run_scoring stamps qdii_premium_pct via injected resolver

AC6 — optional qdii_premium_resolver(asset_class, market, symbol) → float|None.
When provided and the resolver returns a non-None float, the value lands on
the score row as qdii_premium_pct. Key is omitted when the resolver returns
None (matches the existing convention for empty scalar fields).

The pipeline stays pure: AkShare calls happen in the resolver provided by
the command layer (effects at edges).
EOF
)"
```

---

## Task 13: Command-layer composition — `score_cmd.py` builds the resolver

**Files:**
- Modify: `src/irc/commands/score_cmd.py`

- [ ] **Step 13.1: Wire the resolver in `run_score`**

Edit `src/irc/commands/score_cmd.py`. Add imports at top:

```python
from irc.data.akshare_client import fetch_qdii_premium_pct
from irc.scoring.qdii_premium import qdii_premium_for_row
```

In `run_score`, just before the `out = run_scoring(...)` call (around line 53), build the resolver:

```python
    def _resolve_qdii_premium(
        asset_class: str, market: str, symbol: str
    ) -> float | None:
        return qdii_premium_for_row(
            asset_class=asset_class,
            market=market,
            fetcher=fetch_qdii_premium_pct,
            symbol=symbol,
        )
```

Pass the resolver into `run_scoring`:

```python
    out = run_scoring(
        watchlist=watchlist,
        metrics=metrics,
        news_summaries={},
        regime_summary=regime,
        route=route,
        cfg_scoring=bundle.scoring,
        qdii_premium_resolver=_resolve_qdii_premium,
    )
```

- [ ] **Step 13.2: Smoke the wire-in via a unit test that asserts the resolver is reachable**

Append to `tests/scoring/test_qdii_premium.py`:

```python
def test_score_cmd_composes_resolver_via_qdii_premium_for_row() -> None:
    """Smoke: score_cmd's _resolve_qdii_premium routes through qdii_premium_for_row.

    Don't run the full CLI — just confirm the imports resolve and the
    helper is reachable from the command layer.
    """
    from irc.commands import score_cmd  # noqa: F401
    from irc.data.akshare_client import fetch_qdii_premium_pct
    from irc.scoring.qdii_premium import qdii_premium_for_row

    # The two functions must be importable in the same namespace where
    # the resolver is composed.
    assert callable(fetch_qdii_premium_pct)
    assert callable(qdii_premium_for_row)
```

- [ ] **Step 13.3: Run the smoke + full suite**

Run: `uv run pytest tests/ -x`
Expected: ALL PASS.

- [ ] **Step 13.4: Commit**

```bash
git add src/irc/commands/score_cmd.py tests/scoring/test_qdii_premium.py
git commit -m "$(cat <<'EOF'
feat(002): score_cmd composes resolver from fetcher + routing helper

run_score builds _resolve_qdii_premium(asset_class, market, symbol) by
composing fetch_qdii_premium_pct (effectful) with qdii_premium_for_row
(pure) and passes it into run_scoring. AkShare calls live exclusively
in the command layer (effects at edges).
EOF
)"
```

---

## Task 14: Memo-stage twin (`_decision_status_for_pick`) reads threshold from DiscoveryConfig

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Test: existing tests must stay green; add a new test for the threshold-from-config path.

- [ ] **Step 14.1: Verify the existing memo gate semantics**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k qdii 2>/dev/null || uv run pytest tests/ -v -k "memo and qdii"`
Expected: existing tests stay green; the goal of this task is additive (memo gate gets the threshold-aware branch).

- [ ] **Step 14.2: Write the failing test for memo-stage threshold awareness**

Add to whichever existing memo test file covers `_decision_status_for_pick` (find it):

Run: `grep -rln "_decision_status_for_pick\|decision_status_for_pick" /Users/snow/Documents/Repository/investment-research-copilot/tests/`
Expected: identifies the file. Append a new test to the same file:

```python
def test_decision_status_for_pick_uses_qdii_premium_threshold() -> None:
    """AC10: memo-stage twin honours the qdii_max_premium_pct threshold."""
    from irc.commands.memo_cmd import _decision_status_for_pick

    score_row = {
        "instrument_id": "513650",
        "asset_class": "us_etf",
        "action": "buy_candidate",
        "data_completeness": 1.0,
        "qdii_premium_pct": 0.10,  # above default 0.05
    }
    trade = {
        "target": "513650", "asset_class": "us_etf",
        "venue_compatible": True, "proxy_id": None,
        "target_weight": 0.2,
    }
    op_row = {"instrument_id": "513650", "asset_class": "us_etf"}
    status = _decision_status_for_pick(
        score_row, trade, op_row, qdii_max_premium_pct=0.05,
    )
    assert status == "blocked"


def test_decision_status_for_pick_synthetic_zero_passes() -> None:
    """Off-exchange synthetic 0.0 passes the memo-stage gate."""
    from irc.commands.memo_cmd import _decision_status_for_pick

    score_row = {
        "instrument_id": "017641",
        "asset_class": "us_etf",
        "action": "buy_candidate",
        "data_completeness": 1.0,
        "qdii_premium_pct": 0.0,
    }
    trade = {
        "target": "017641", "asset_class": "us_etf",
        "venue_compatible": True, "proxy_id": None,
        "target_weight": 0.2,
    }
    op_row = {"instrument_id": "017641", "asset_class": "us_etf"}
    status = _decision_status_for_pick(
        score_row, trade, op_row, qdii_max_premium_pct=0.05,
    )
    assert status == "actionable_buy"
```

- [ ] **Step 14.3: Run the test to verify failure**

Run: `uv run pytest tests/ -v -k "decision_status_for_pick_uses_qdii_premium_threshold or synthetic_zero_passes"`
Expected: FAIL with TypeError or signature mismatch.

- [ ] **Step 14.4: Update `_decision_status_for_pick`**

Edit `src/irc/commands/memo_cmd.py`. Update the function signature (around line 433):

```python
def _decision_status_for_pick(
    score_row: dict,
    trade: dict | None,
    op_row: dict,
    *,
    qdii_max_premium_pct: float = 0.05,
) -> str:
```

Inside the function body, replace the `qdii_premium_unknown` block with the same mutual-exclusion pair as `decide_row`:

```python
    asset_class = str(op_row.get("asset_class") or score_row.get("asset_class") or "")
    raw_premium = score_row.get("qdii_premium_pct")
    try:
        premium_value = float(raw_premium) if raw_premium is not None else None
    except (TypeError, ValueError):
        premium_value = None
    is_qdii_buy = (
        asset_class in _QDII_ASSET_CLASSES
        and score_action in _BUY_ACTIONS
    )
    qdii_premium_unknown = is_qdii_buy and premium_value is None
    qdii_premium_too_high = (
        is_qdii_buy
        and premium_value is not None
        and premium_value > qdii_max_premium_pct
    )
```

Add `_BUY_ACTIONS` to the imports (if not already imported from `decision/gates.py`):

```python
from irc.decision.gates import (
    ...,
    _BUY_ACTIONS,
)
```

(If `_BUY_ACTIONS` is module-private and not exported, instead inline the set locally:)

```python
    _MEMO_BUY_ACTIONS = {"buy_candidate", "strong_buy_candidate"}
    is_qdii_buy = (
        asset_class in _QDII_ASSET_CLASSES
        and score_action in _MEMO_BUY_ACTIONS
    )
```

Pass `qdii_premium_too_high` into `compute_blocking_reasons`:

```python
    blocking = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=completeness,
        completeness_threshold=MIN_BUY_COMPLETENESS,
        target_weight_valid=True,
        venue_status=venue_status,
        evidence_status="evidence_linked",
        score_action=score_action,
        qdii_premium_unknown=qdii_premium_unknown,
        qdii_premium_too_high=qdii_premium_too_high,
    )
```

- [ ] **Step 14.5: Thread the bundle's threshold into every caller of `_decision_status_for_pick`**

Run: `grep -n "_decision_status_for_pick(" /Users/snow/Documents/Repository/investment-research-copilot/src/irc/commands/memo_cmd.py`
Expected: identifies each call site (likely inside `_build_pick_rows` or similar). For each call, pass:

```python
        qdii_max_premium_pct=bundle.discovery.hard_filters.qdii_max_premium_pct,
```

The `bundle` is already in scope wherever the memo composes its picks table — confirm by reading the surrounding function. If `bundle` isn't in scope, plumb the float through the function signatures.

- [ ] **Step 14.6: Run the memo tests + full suite**

Run: `uv run pytest tests/ -x`
Expected: ALL PASS.

- [ ] **Step 14.7: Commit**

```bash
git add src/irc/commands/memo_cmd.py tests/
git commit -m "$(cat <<'EOF'
feat(002): memo-stage twin honours qdii_max_premium_pct threshold

_decision_status_for_pick mirrors decide_row's mutual-exclusion pair
(qdii_premium_unknown vs qdii_premium_too_high). Threshold flows from
DiscoveryConfig (default QDII_MAX_PREMIUM_DEFAULT=0.05) so the memo
§5 decision column matches the decision_report verdict for QDII rows.
EOF
)"
```

---

## Task 15: End-to-end smoke for the 8 MASTER-SPEC instruments

**Files:**
- Test: `tests/scoring/test_qdii_premium.py`

- [ ] **Step 15.1: Add the smoke test**

Append to `tests/scoring/test_qdii_premium.py`:

```python
def test_smoke_eight_master_spec_instruments_route_correctly() -> None:
    """Per spec Goal: the 8 MASTER-SPEC instruments split into 3 on-exchange
    (fetcher invoked) + 5 off-exchange (synthetic 0.0 injected).
    """
    on_exchange = [
        ("159691", "hk_etf"),
        ("513690", "us_etf"),
        ("513650", "us_etf"),
    ]
    off_exchange = [
        ("517641", "us_etf"),
        ("019172", "us_etf"),
        ("161716", "us_etf"),
        ("016452", "us_etf"),
        ("019547", "qdii_global"),
    ]
    fetcher_calls: list[str] = []

    def fetcher(symbol: str) -> float | None:
        fetcher_calls.append(symbol)
        return 0.01  # healthy 1% premium

    on_results = [
        qdii_premium_for_row(
            asset_class=ac, market="cn_on_exchange",
            fetcher=fetcher, symbol=sym,
        )
        for sym, ac in on_exchange
    ]
    off_results = [
        qdii_premium_for_row(
            asset_class=ac, market="cn_off_exchange",
            fetcher=fetcher, symbol=sym,
        )
        for sym, ac in off_exchange
    ]
    assert on_results == [0.01, 0.01, 0.01]
    assert off_results == [0.0, 0.0, 0.0, 0.0, 0.0]
    # Fetcher invoked exactly 3 times — one per on-exchange row.
    assert sorted(fetcher_calls) == ["159691", "513650", "513690"]
```

- [ ] **Step 15.2: Run the smoke**

Run: `uv run pytest tests/scoring/test_qdii_premium.py::test_smoke_eight_master_spec_instruments_route_correctly -v`
Expected: PASS.

- [ ] **Step 15.3: Commit**

```bash
git add tests/scoring/test_qdii_premium.py
git commit -m "$(cat <<'EOF'
test(002): smoke 8 MASTER-SPEC QDII instruments route correctly

3 on-exchange (159691, 513690, 513650) invoke the fetcher; 5
off-exchange (517641, 019172, 161716, 016452, 019547) get the
synthetic 0.0 without touching the fetcher. Confirms the spec Goal's
"unblock 8 instruments" claim by domain.
EOF
)"
```

---

## Task 16: Rewrite the `qdii_premium_unknown` remediation text (AC22 — last by ordering)

**Files:**
- Modify: `src/irc/decision/report.py`
- Test: `tests/decision/test_three_section_markdown.py`

This task is intentionally last per the spec ("AC22 goes last after all fetcher behavior is in"). Until now, both QDII codes coexist; this task updates the operator-facing copy so `qdii_premium_unknown` describes the post-Item-002 reality.

- [ ] **Step 16.1: Write the failing assertion for the new remediation text**

Append to `tests/decision/test_three_section_markdown.py`:

```python
def test_qdii_premium_unknown_remediation_mentions_akshare():
    """AC22: the rewritten remediation must reference AkShare so operators
    know 'unknown' = 'AkShare returned no row'."""
    from irc.decision.report import _BLOCKING_REMEDIATION
    text = _BLOCKING_REMEDIATION["qdii_premium_unknown"]
    assert "AkShare" in text
    # AC22 explicitly drops the FX-status half (out of V1 scope).
    assert "FX status" not in text
```

- [ ] **Step 16.2: Run the test to verify failure**

Run: `uv run pytest tests/decision/test_three_section_markdown.py::test_qdii_premium_unknown_remediation_mentions_akshare -v`
Expected: FAIL — the current text says "Fetch real-time QDII premium / FX status..." which contains "FX status" and not "AkShare".

- [ ] **Step 16.3: Update `_BLOCKING_REMEDIATION["qdii_premium_unknown"]`**

Edit `src/irc/decision/report.py`. Replace the existing entry:

```python
    "qdii_premium_unknown":
        "Fetch real-time QDII premium / FX status before treating as actionable. "
        "QDII feeders frequently trade 5–15% above NAV.",
```

with:

```python
    "qdii_premium_unknown":
        "AkShare returned no premium snapshot for this QDII symbol. "
        "Refresh fund_etf_spot_em data or wait for the next ingest. "
        "QDII feeders frequently trade 5–15% above NAV — premium must "
        "be known before treating as actionable.",
```

- [ ] **Step 16.4: Verify the existing in-section test (looks for "Fetch real-time QDII premium") still passes or update it**

Run: `uv run pytest tests/decision/test_three_section_markdown.py -v`
Expected: `test_qdii_premium_unknown_renders_in_blocked_section` will FAIL because it asserts `"Fetch real-time QDII premium" in section`. Update it to:

```python
    assert "AkShare returned no premium snapshot" in section
```

- [ ] **Step 16.5: Run the full markdown suite**

Run: `uv run pytest tests/decision/test_three_section_markdown.py -v`
Expected: ALL PASS.

- [ ] **Step 16.6: Commit**

```bash
git add src/irc/decision/report.py tests/decision/test_three_section_markdown.py
git commit -m "$(cat <<'EOF'
docs(002): rewrite qdii_premium_unknown remediation per AC22

After item 002 lands, "unknown" means "AkShare returned no row for
this symbol" — distinct from the new "too high" code which means
"data available, premium exceeds the threshold". The rewrite drops
the now-misleading "FX status" half (out of V1 scope per Non-goals)
and names the fund_etf_spot_em endpoint operators should refresh.
EOF
)"
```

---

## Task 17: Final verification — full suite, lint, config validate

**Files:** none (verification only).

- [ ] **Step 17.1: Run the full test suite (no live tests)**

Run: `uv run pytest`
Expected: ALL PASS. Zero failures, zero new warnings about deprecated APIs.

- [ ] **Step 17.2: Run the live AkShare test (optional, manual)**

Run: `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_live -v`
Expected: PASS — at least one of `{159691, 513690, 513650}` returned a finite ratio in `(-1.0, 1.0)`. (Skip in CI; document the run.)

- [ ] **Step 17.3: Lint**

Run: `uv run ruff check src tests`
Expected: zero issues.

- [ ] **Step 17.4: Config validate**

Run: `uv run irc config validate`
Expected: exit 0; every YAML validated.

- [ ] **Step 17.5: End-to-end smoke against today's outputs (optional, depends on a previous `irc run --only discover`)**

Run: `uv run irc run --only score`
Expected: `outputs/<today>/scoring.json` contains `qdii_premium_pct` for the 3 on-exchange QDII tickers in the universe and `0.0` for the 5 off-exchange feeders. (This step is documentation-only; do NOT commit `outputs/` — the directory is gitignored.)

- [ ] **Step 17.6: Commit (verification log only, if needed)**

No file changes — verification is a check, not a commit.

---

## Self-review

**Spec coverage:**

- AC1 (signed float, ratio) → Task 3.
- AC2 (bulk-fetch + lru_cache) → Task 3 (impl) + Task 4 (test for one-call-many-symbols).
- AC3 (column resilience) → Task 4.
- AC4 (symbol normalisation via `_normalize_fund_code`) → Task 3 (impl uses the existing helper).
- AC5 (off-exchange synthetic 0.0) → Task 2.
- AC6 (`run_scoring` accepts resolver) → Task 12.
- AC7 (command-layer composition) → Task 13.
- AC8 (new `qdii_premium_too_high` parameter on `compute_blocking_reasons`) → Task 8.
- AC9 (threshold default `0.05` + `QDII_MAX_PREMIUM_DEFAULT` constant) → Task 6.
- AC10 (`decide_row` + memo twin receive threshold) → Tasks 9 + 14.
- AC11 (label + remediation) → Task 11.
- AC12 (live double-gated test) → Task 5.
- AC13 (fixture + bulk-table test) → Tasks 3 (fixture) + 4 (one-call-many-symbols).
- AC14 (scoring-level TDD coverage) → Task 12.
- AC15 (gate-level TDD coverage) → Task 9.
- AC16 (fetch-budget bookkeeping) → Task 4 (the one-call assertion is the bookkeeping proof).
- AC17 (three-section markdown render) → Task 10/11.
- AC18 (`irc config validate` passes) → Tasks 6 + 17.
- AC19 (CONTEXT.md addendum) → already merged in commit `a389c94` (verified via grep at planning time); not a code change.
- AC20 (cache_clear teardown) → Tasks 3 + 4 (every fetcher test calls `_fetch_full_etf_spot_table.cache_clear()` in try/finally).
- AC21 (`_QDII_ASSET_CLASSES` consolidation) → Task 7 (with single-definition acceptance test).
- AC22 (rewrite `qdii_premium_unknown` remediation) → Task 16, last per the user's directive.

**Placeholder scan:** none — every code block contains the actual diff content.

**Type consistency:** `qdii_premium_resolver: Callable[[str, str, str], float | None]` matches its only call site in pipeline.py (`asset_class, market, symbol`). `qdii_premium_for_row(asset_class, market, fetcher, symbol)` has the routing helper signature; the resolver built in `score_cmd.py` closes over `fetch_qdii_premium_pct` and exposes the three-argument shape `run_scoring` expects. `_fetch_full_etf_spot_table` is the lru_cache'd accessor; `fetch_qdii_premium_pct` is the per-symbol wrapper. `QDII_MAX_PREMIUM_DEFAULT: Final[float] = 0.05` is referenced consistently in `decide_row`, `compose_decision_report`, and `decision_cmd.py`.

**Files touched / not touched (vs spec):**
- All 18 files listed in the spec's "Files touched (summary)" table are covered.
- ADR 0002 §5 F6 paragraph was already added in commit `a389c94` per the grill (verified at planning time) — no further docs edit needed.
- CONTEXT.md "QDII premium-to-NAV" section already exists in commit `a389c94` — no further docs edit needed.

**Judgment calls made during planning:**
- The spec says "register `qdii_premium_too_high` reason" but the project has no central `_GAP_TO_REASON` table for decision gates (that's an opportunity-layer pattern from item 001). The plan instead registers the reason in `_BLOCKING_REASON_LABEL` + `_BLOCKING_REMEDIATION` in `decision/report.py`, which IS the central place for decision-stage reasons. See Task 11.
- The spec text says `compose_decision_report` gains an optional `qdii_max_premium_pct` parameter; the plan adds it with a `None` sentinel that resolves to `QDII_MAX_PREMIUM_DEFAULT`, so legacy callers (tests that don't pass the kwarg) keep working. See Task 10.

Plan complete and saved to `docs/2026-05-26-decision-confidence-followup/items/002-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.
