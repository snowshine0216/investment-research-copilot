# Heat factor — restriction leg (item 003) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Light up the monitor `heat` (crowding) factor for all 10 monitor funds on the restriction leg (限购 / 申购状态) via a single market-wide `ak.fund_purchase_em()` call per `irc monitor` run; the AUM-Δ leg stays deferred (`aum_delta_pct` always `None`).

**Architecture:** New pure-edge module `src/irc/monitor/heat_fetch.py` — ONE network call (`fetch_purchase_table`, never-raises → `None` on failure) plus pure column-name-tolerant parsing (`parse_purchase_status`, `heat_inputs_for`). `monitor_cmd.py` fetches the table ONCE in `run_monitor` (next to where `con` is opened), threads it into `_process_fund`, and per fund computes `(restricted, aum_delta_pct)` — replacing the two hardcoded `None` heat lines. The existing `heat_score` (`factor_maps.py`) is untouched: with `aum_delta_pct=None` it reduces to `restricted → −0.5`, else `+0.3`, `None → None`.

**Tech Stack:** Python 3.12, pandas, AkShare (`ak.fund_purchase_em`), pytest, uv. CN endpoint stays DIRECT (no `IRC_HTTPS_PROXY`), per the project http-proxy rule.

---

## Context the implementer MUST know (read before coding)

### What already exists — DO NOT touch

- **`src/irc/monitor/factor_maps.py` — `heat_score` is FINAL. NO scoring change (spec §5.2, §7).** Confirmed exact behavior (re-read it):

  ```python
  def heat_score(*, restricted: bool | None, aum_delta_pct: float | None) -> float | None:
      if restricted is None and aum_delta_pct is None:
          return None                       # → heat_no_data
      rapid = aum_delta_pct is not None and aum_delta_pct >= _RAPID_INFLOW_PCT  # 20.0
      if restricted and rapid:
          return -1.0
      if restricted or rapid:
          return -0.5
      return 0.3
  ```

  With `aum_delta_pct=None` (this slice always passes `None`): `rapid` is always `False`, so
  `restricted=True → −0.5` (crowded), `restricted=False → +0.3` (calm),
  `restricted=None → None` (N/A). This is exactly spec §5.2. **factor_maps.py stays UNCHANGED in this item.**

- **`src/irc/monitor/factors.py` — `_heat` and `FactorInputs` are FINAL.** Confirmed:
  - `FactorInputs` already has fields `restricted: bool | None` and `aum_delta_pct: float | None`.
  - `_heat(profile, inp)` gates on `eligible_factors(profile)` then calls
    `heat_score(restricted=inp.restricted, aum_delta_pct=inp.aum_delta_pct)`; a `None` score →
    `_na("heat", _NA_HEAT_NO_DATA)`.
  - `_NA_HEAT_NO_DATA = "heat_no_data"` is already in `KNOWN_NA_REASONS`. **No new reason codes.**
    Do NOT edit `factors.py`.

- **Items 001 & 002 (valuation) are merged and wired.** `_process_fund` already takes `*, con=None`
  and calls `resolve_valuation_state(...)`. **Preserve all of that — only ADD the heat wiring.**

### The AkShare schema is LIVE-CONFIRMED (do not guess)

A live `ak.fund_purchase_em()` probe on the pinned version returned a market-wide table,
shape ≈ `(26756, 12)`, columns:

```
['序号', '基金代码', '基金简称', '基金类型', '最新净值/万份收益',
 '最新净值/万份收益-报告时间', '申购状态', '赎回状态', '下一开放日',
 '购买起点', '日累计限定金额', '手续费']
```

Confirmed facts the parse relies on:

- **`基金代码`** dtype is `str`, already 6-digit zero-padded (e.g. `'000001'`). It matches
  `MonitorFund.id` (also a 6-digit string) by **direct string equality after `str(...).strip()`**.
  Zero-pad defensively to width 6 on both sides (cheap insurance against an int-typed column on a
  future akshare version).
- **`申购状态`** observed values: `开放申购` (open), `限大额`, `暂停申购`, `场内交易`, `封闭期`,
  `认购期`, `''`. The open set is `{"开放申购"}`; everything else (incl. `''` and `场内交易`)
  counts as restricted, per spec §5.1's exact rule (`申购状态 ∉ {开放申购}`).
- **`日累计限定金额`** dtype is `float64`. Open funds show ≈ `1e11`; `限大额`/QDII restricted funds
  show `1e2`–`1e5`. The `< 1e8` cap test correctly flags them.
- All 10 monitor ids are present in the table. Live spot-check (will vary day to day, used only to
  reason about the rule — NOT asserted): `006533`, `009225`, `270023` were `限大额` cap `< 1e8`
  → restricted; the other 7 were `开放申购` cap `1e11` → not restricted.

> **Why the parse is still column-name-tolerant despite the live confirmation:** spec §10 names
> `fund_purchase_em` schema drift as a risk. If a future akshare version renames/drops `申购状态`
> or `日累计限定金额`, the parse must degrade to `None` (→ `heat_no_data`), NEVER a wrong bool.
> The pure parser therefore checks column presence and degrades to `None` on any unexpected shape.

### The akshare import decision — LAZY default (justified)

The spec signature is `def fetch_purchase_table(fetch=ak.fund_purchase_em)`. A **literal** default
`fetch=ak.fund_purchase_em` would force `import akshare` at module import time. The house pattern
(`akshare_index_valuation.py`, `akshare_fundamentals.py`) deliberately does the opposite —
`import akshare as ak  # local import` *inside* a helper, "avoids importing akshare at module load".
**Mirror the house pattern:** default the `fetch` parameter to `None` and lazy-`import akshare`
inside the function body only when `fetch is None`. Tests inject a fake `fetch=...` and never import
akshare. This keeps the spec's injectable-default contract while honoring the no-module-top-akshare
convention.

### The pre-existing test breakage this item fixes (IMPORTANT)

`tests/commands/test_monitor_cmd_eval_wiring.py` is **ALREADY RED** on this branch HEAD: item 001
added `con=con` to the `_process_fund(...)` call, but that test's monkeypatch lambda is
`lambda fund, cfg, root, llm:` — it does NOT absorb keyword args, so the existing `con=con` already
raises `TypeError: ... got an unexpected keyword argument 'con'`. Item 003 adds a second kwarg
(`purchase_table=table`) at the same call site, so this plan **fixes that lambda** (Task 5) by adding
`**kw`. Confirm the red state before you start (Task 0) so you can tell item-001 debt apart from any
regression you introduce.

### http-proxy: CN endpoint stays DIRECT

`http_proxy.py` documents that akshare CN sources stay direct; only DXY-via-EastMoney uses the proxy.
`fund_purchase_em` is a CN EastMoney endpoint. **Do NOT touch `http_proxy` / `resolve_proxy`.** Make
the call exactly like the other `akshare_*.py` modules: a plain `ak.<fn>()` with no proxy plumbing.

---

## File Structure

```
src/irc/monitor/heat_fetch.py            # NEW  edge (1 akshare call) + pure parse_purchase_status / heat_inputs_for
tests/monitor/test_heat_fetch.py         # NEW  pure parse tests (table-driven) + fetch never-raises test
tests/monitor/test_heat_fetch_live.py    # NEW  double-gated live ak.fund_purchase_em() probe
src/irc/commands/monitor_cmd.py          # EDIT fetch table once in run_monitor + thread + per-fund heat_inputs_for; replace 2 hardcoded None heat lines
tests/commands/test_monitor_cmd_eval_wiring.py  # EDIT _process_fund monkeypatch lambda → absorb **kw (fixes item-001 debt + item-003 kwarg)
```

`factor_maps.py` and `factors.py` are **NOT** modified.

---

## Task 0: Baseline — confirm the pre-existing red and a green starting point

**Files:** none (verification only).

- [ ] **Step 1: Confirm the item-001 pre-existing failure**

Run: `uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'con'` (this is item-001 debt, fixed in Task 5).

- [ ] **Step 2: Confirm the heat-relevant existing tests are green**

Run: `uv run pytest tests/monitor/test_factor_maps.py tests/monitor/test_factors.py tests/monitor/test_known_na_reasons.py -q`
Expected: PASS (heat_score / _heat / KNOWN_NA_REASONS untouched; this is your no-regression baseline).

---

## Task 1: `parse_purchase_status` — pure restriction rule (TDD)

**Files:**
- Create: `src/irc/monitor/heat_fetch.py`
- Test: `tests/monitor/test_heat_fetch.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/monitor/test_heat_fetch.py`:

```python
from __future__ import annotations

import pandas as pd
import pytest

from irc.monitor.heat_fetch import (
    fetch_purchase_table,
    heat_inputs_for,
    parse_purchase_status,
    _RESTRICTION_CAP_THRESHOLD,
)


def _table(rows: list[dict]) -> pd.DataFrame:
    """Build a fund_purchase_em-shaped frame from minimal rows."""
    return pd.DataFrame(rows)


# ── parse_purchase_status: not-restricted (open + uncapped) ───────────────────

def test_open_status_high_cap_not_restricted():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is False


# ── parse_purchase_status: restricted by status ───────────────────────────────

@pytest.mark.parametrize("status", ["暂停申购", "限大额", "场内交易", "封闭期", "认购期", ""])
def test_non_open_status_is_restricted(status):
    # cap is high, but status alone (∉ {开放申购}) restricts.
    t = _table([{"基金代码": "519069", "申购状态": status, "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "519069") is True


# ── parse_purchase_status: restricted by cap ──────────────────────────────────

def test_open_status_low_cap_is_restricted():
    # 开放申购 but daily cap below 1e8 → restricted (限大额-style).
    t = _table([{"基金代码": "006533", "申购状态": "开放申购", "日累计限定金额": 1e5}])
    assert parse_purchase_status(t, "006533") is True


def test_cap_exactly_at_threshold_not_restricted():
    # cap == 1e8 is NOT < 1e8 → open status + at-threshold cap = not restricted.
    t = _table([{"基金代码": "000083", "申购状态": "开放申购",
                 "日累计限定金额": _RESTRICTION_CAP_THRESHOLD}])
    assert parse_purchase_status(t, "000083") is False


# ── parse_purchase_status: None paths (absent / unparseable / bad shape) ───────

def test_fund_absent_returns_none():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "999999") is None


def test_missing_status_column_returns_none():
    t = _table([{"基金代码": "000083", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is None


def test_missing_cap_column_falls_back_to_status_only():
    # No cap column: rule degrades to the status leg alone (open → not restricted),
    # NOT to None — status is parseable, so we emit an honest bool.
    t = _table([{"基金代码": "000083", "申购状态": "开放申购"}])
    assert parse_purchase_status(t, "000083") is False


def test_missing_code_column_returns_none():
    t = _table([{"申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is None


def test_none_table_returns_none():
    assert parse_purchase_status(None, "000083") is None


def test_empty_table_returns_none():
    assert parse_purchase_status(_table([]), "000083") is None


def test_unparseable_cap_with_open_status_not_restricted():
    # 开放申购 + non-numeric cap → cap leg can't fire; status leg says open → not restricted.
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": "—"}])
    assert parse_purchase_status(t, "000083") is False


def test_code_zero_pad_match():
    # Defensive: an int-typed code column still matches the 6-digit id.
    t = _table([{"基金代码": 83, "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_heat_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.heat_fetch'` (or ImportError on the symbols).

- [ ] **Step 3: Write the module — pure parse first (no network yet)**

Create `src/irc/monitor/heat_fetch.py`:

```python
"""EDGE + pure parse: monitor heat (crowding) restriction leg via AkShare.

`ak.fund_purchase_em()` returns ONE market-wide table (申购状态 + 日累计限定金额 per
fund). A single call per `irc monitor` run yields the restriction status for all
monitor ids — no per-fund fetch. The one network effect (`fetch_purchase_table`)
NEVER raises: any failure → None → every per-fund parse yields None → honest
`heat_no_data` (spec §5.3). Parsing is pure and column-name-tolerant: an
unexpected shape degrades to None, NEVER a wrong bool (spec §10).

CN endpoint stays DIRECT (no IRC_HTTPS_PROXY) per the project http-proxy rule.
AUM-Δ leg is deferred this slice — `heat_inputs_for` always returns aum_delta_pct=None.
"""
from __future__ import annotations

import logging

import pandas as pd

_log = logging.getLogger(__name__)

# Restriction rule (spec §5.1): restricted when 申购状态 ∉ _OPEN_STATUSES OR
# 日累计限定金额 < _RESTRICTION_CAP_THRESHOLD.
_RESTRICTION_CAP_THRESHOLD: float = 1e8
_OPEN_STATUSES: frozenset[str] = frozenset({"开放申购"})

# Column names from the live-confirmed fund_purchase_em schema. Parsing tolerates
# absence (degrade to None) so a future akshare rename can't produce a wrong bool.
_CODE_COL: str = "基金代码"
_STATUS_COL: str = "申购状态"
_CAP_COL: str = "日累计限定金额"


def _norm_code(value: object) -> str:
    """6-digit zero-padded fund code, tolerant of int/str/whitespace."""
    return str(value).strip().zfill(6)


def _row_for(table: pd.DataFrame, fund_id: str) -> pd.Series | None:
    """Pure: the single row whose code matches fund_id, else None."""
    if _CODE_COL not in table.columns:
        return None
    target = _norm_code(fund_id)
    codes = table[_CODE_COL].map(_norm_code)
    matched = table[codes == target]
    if matched.empty:
        return None
    return matched.iloc[0]


def _cap_below_threshold(row: pd.Series) -> bool:
    """Pure: True only when the cap is numeric AND < threshold. Missing/unparseable
    cap → False (cap leg can't fire; the status leg still decides)."""
    if _CAP_COL not in row.index:
        return False
    try:
        cap = float(row[_CAP_COL])
    except (TypeError, ValueError):
        return False
    if pd.isna(cap):
        return False
    return cap < _RESTRICTION_CAP_THRESHOLD


def parse_purchase_status(table: pd.DataFrame | None, fund_id: str) -> bool | None:
    """Pure: restricted=True when 申购状态 ∉ {开放申购} OR 日累计限定金额 < 1e8.
    Fund absent / missing code or status column / empty|None table → None
    (→ heat_no_data, surfaced — never a fabricated bool)."""
    if not isinstance(table, pd.DataFrame) or table.empty:
        return None
    row = _row_for(table, fund_id)
    if row is None or _STATUS_COL not in row.index:
        return None
    status = str(row[_STATUS_COL]).strip()
    restricted_by_status = status not in _OPEN_STATUSES
    return restricted_by_status or _cap_below_threshold(row)


def heat_inputs_for(
    fund_id: str, *, purchase_table: pd.DataFrame | None
) -> tuple[bool | None, float | None]:
    """Pure: (restricted, aum_delta_pct). aum_delta_pct is always None this slice
    (no per-fund live QoQ source — AUM-Δ leg deferred, spec §5)."""
    return parse_purchase_status(purchase_table, fund_id), None
```

> NOTE: `fetch_purchase_table` is defined in Task 2. The test file imports it at top; until Task 2
> lands, the `parse_*` / `heat_inputs_for` tests in this task still import-fail. To keep Task 1
> independently green, define `fetch_purchase_table` as a stub NOW with the real body in Task 2,
> OR run Task 1 + Task 2 back-to-back before the first green. **Chosen approach:** define the full
> `fetch_purchase_table` now too (next block) so the import resolves and Task 1's parse tests go
> green immediately; Task 2 then only adds the *network-failure* test around it.

Append to `src/irc/monitor/heat_fetch.py`:

```python
def fetch_purchase_table(fetch=None) -> pd.DataFrame | None:
    """EDGE: ONE network call per run → the market-wide purchase table, or None on
    ANY failure (never raises — spec §5.3). `fetch` is injectable for tests; the
    default lazy-imports akshare (house pattern: no module-top akshare). CN endpoint
    is DIRECT (no IRC_HTTPS_PROXY)."""
    if fetch is None:
        import akshare as ak  # local import — house pattern, avoids akshare at module load
        fetch = ak.fund_purchase_em
    try:
        table = fetch()
    except Exception:  # noqa: BLE001 — degrade to None, never crash the brief
        _log.warning("fetch_purchase_table: ak.fund_purchase_em() failed", exc_info=True)
        return None
    if not isinstance(table, pd.DataFrame) or table.empty:
        _log.warning("fetch_purchase_table: empty/invalid purchase table")
        return None
    return table
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_heat_fetch.py -q`
Expected: PASS (all parse + heat_inputs_for cases). If `test_missing_cap_column_falls_back_to_status_only` or `test_unparseable_cap_*` fail, recheck `_cap_below_threshold` returns `False` (not None) on a missing/unparseable cap.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/heat_fetch.py tests/monitor/test_heat_fetch.py
git commit -m "feat(monitor): heat restriction-leg parse + edge (heat_fetch)"
```

---

## Task 2: `fetch_purchase_table` + `heat_inputs_for` — edge never-raises + aum=None (TDD)

**Files:**
- Modify: `src/irc/monitor/heat_fetch.py` (already complete from Task 1 — this task only ADDS tests)
- Test: `tests/monitor/test_heat_fetch.py`

- [ ] **Step 1: Write the failing tests (append to `tests/monitor/test_heat_fetch.py`)**

```python
# ── fetch_purchase_table: never raises, returns None on failure ───────────────

def test_fetch_returns_table_from_injected_fetch():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    out = fetch_purchase_table(fetch=lambda: t)
    assert out is t


def test_fetch_returns_none_when_fetch_raises():
    def _boom():
        raise RuntimeError("network down")
    assert fetch_purchase_table(fetch=_boom) is None


def test_fetch_returns_none_on_empty_frame():
    assert fetch_purchase_table(fetch=lambda: _table([])) is None


def test_fetch_returns_none_on_non_dataframe():
    assert fetch_purchase_table(fetch=lambda: "not a frame") is None


# ── heat_inputs_for: always aum_delta_pct=None; restricted threads parse result ─

def test_heat_inputs_for_open_fund():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    restricted, aum = heat_inputs_for("000083", purchase_table=t)
    assert restricted is False and aum is None


def test_heat_inputs_for_restricted_fund():
    t = _table([{"基金代码": "006533", "申购状态": "限大额", "日累计限定金额": 1e5}])
    restricted, aum = heat_inputs_for("006533", purchase_table=t)
    assert restricted is True and aum is None


def test_heat_inputs_for_none_table_yields_none_restricted():
    restricted, aum = heat_inputs_for("000083", purchase_table=None)
    assert restricted is None and aum is None


def test_heat_inputs_for_absent_fund_yields_none_restricted():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    restricted, aum = heat_inputs_for("999999", purchase_table=t)
    assert restricted is None and aum is None
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest tests/monitor/test_heat_fetch.py -q`
Expected: PASS (the Task-1 module already implements both `fetch_purchase_table` and `heat_inputs_for`; this task locks their contract with tests). No source change needed unless a test fails — if so, fix `heat_fetch.py` minimally.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/irc/monitor/heat_fetch.py tests/monitor/test_heat_fetch.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/irc/monitor/heat_fetch.py tests/monitor/test_heat_fetch.py
git commit -m "test(monitor): heat_fetch edge never-raises + heat_inputs_for aum=None"
```

---

## Task 3: Heat scoring integration — restricted maps through `heat_score` (TDD)

This proves the wiring contract end-to-end at the pure layer (no monitor_cmd yet): a `restricted`
value from `heat_inputs_for` → `FactorInputs` → `build_factor_scores` → an eligible `heat`
FactorScore with the right value. Guards against a future change to `heat_score` silently breaking
the slice.

**Files:**
- Test: `tests/monitor/test_heat_fetch.py`

- [ ] **Step 1: Write the failing tests (append)**

```python
# ── integration with the existing (untouched) heat_score via build_factor_scores ─

def _heat_score_for(profile, restricted, aum):
    from irc.monitor.factors import FactorInputs, build_factor_scores
    inp = FactorInputs(
        acc_nav=(), minimum_observations=251,
        valuation_state=None, valuation_cached=False,
        restricted=restricted, aum_delta_pct=aum,
        macro_rows=(), constituent_rows=(),
    )
    return {s.name: s for s in build_factor_scores(profile, inp)}["heat"]


def test_restricted_true_yields_eligible_crowded_heat():
    s = _heat_score_for("active_cn_equity", restricted=True, aum=None)
    assert s.eligible is True and s.value == -0.5


def test_restricted_false_yields_eligible_calm_heat():
    s = _heat_score_for("active_cn_equity", restricted=False, aum=None)
    assert s.eligible is True and s.value == 0.3


def test_restricted_none_yields_heat_no_data():
    s = _heat_score_for("active_cn_equity", restricted=None, aum=None)
    assert s.eligible is False and s.reason == "heat_no_data"


def test_gold_profile_heat_still_eligible_when_restricted():
    # gold's weight vector includes heat (spec §3 table) → an eligible crowded score.
    s = _heat_score_for("gold", restricted=True, aum=None)
    assert s.eligible is True and s.value == -0.5
```

> Before relying on `test_gold_profile_heat_still_eligible_when_restricted`, the implementer MUST
> confirm `"heat" in eligible_factors("gold")`. If gold's profile does NOT include heat (the gate
> would then return `profile_ineligible`), change the assertion to
> `assert s.eligible is False and s.reason == "profile_ineligible"`. Run:
> `uv run python -c "from irc.monitor.profiles import eligible_factors; print('gold', eligible_factors('gold')); print('active', eligible_factors('active_cn_equity'))"`
> and pick the matching assertion. (Spec §3's table marks every monitor profile heat-`eligible`, so
> the `-0.5` assertion is expected to hold — but verify, do not assume.)

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/monitor/test_heat_fetch.py -q`
Expected: PASS. (No source change — `heat_score`/`_heat` already implement this. If gold differs, adjust the one assertion per the note above.)

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_heat_fetch.py
git commit -m "test(monitor): heat restricted→score integration through build_factor_scores"
```

---

## Task 4: Live double-gated probe — real `ak.fund_purchase_em()` (TDD-skipped by default)

**Files:**
- Create: `tests/monitor/test_heat_fetch_live.py`

- [ ] **Step 1: Write the live test**

Create `tests/monitor/test_heat_fetch_live.py`:

```python
"""Live AkShare probe for the heat restriction leg (spec §8 — Live).

DOUBLE-GATED: BOTH ``IRC_RUN_LIVE_AKSHARE=1`` AND ``-m live_akshare`` are required.
Without the env var the module-level ``pytestmark`` skips every test here — this
makes ONE real ``ak.fund_purchase_em()`` call and is out of the offline suite.

Run::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest tests/monitor/test_heat_fetch_live.py -v -m live_akshare
"""
from __future__ import annotations

import os

import pytest

from irc.monitor.heat_fetch import (
    fetch_purchase_table,
    heat_inputs_for,
    parse_purchase_status,
)

pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1",
        reason="double-gated: set IRC_RUN_LIVE_AKSHARE=1 to hit AkShare",
    ),
]

_MONITOR_IDS = ["008986", "270023", "519069", "260112", "006533", "009225",
                "000083", "519770", "018132", "161903"]


def test_purchase_table_reachable_and_all_ids_parse():
    """ONE real call → table reachable; every monitor id parses to a real bool."""
    table = fetch_purchase_table()  # default: real ak.fund_purchase_em via lazy import
    assert table is not None, "fund_purchase_em returned None — network error or empty result."
    for fund_id in _MONITOR_IDS:
        restricted, aum = heat_inputs_for(fund_id, purchase_table=table)
        assert restricted in (True, False), (
            f"{fund_id} did not parse to a bool (got {restricted!r}) — schema drift? "
            "Check 申购状态 / 日累计限定金额 column names in heat_fetch."
        )
        assert aum is None  # AUM-Δ leg deferred this slice.


def test_missing_id_parses_to_none_gracefully():
    """A fund absent from the table degrades to None (→ heat_no_data), not an error."""
    table = fetch_purchase_table()
    assert table is not None
    assert parse_purchase_status(table, "999999") is None
```

- [ ] **Step 2: Confirm it SKIPS without the env (offline default)**

Run: `uv run pytest tests/monitor/test_heat_fetch_live.py -q`
Expected: `2 skipped` (double-gated; env var unset).

- [ ] **Step 3: (Optional, network) Confirm it PASSES with the env**

Run: `IRC_RUN_LIVE_AKSHARE=1 uv run pytest tests/monitor/test_heat_fetch_live.py -v -m live_akshare`
Expected: `2 passed` when AkShare is reachable. If the network is unavailable, the first assert fails with a clear message — that is a network/environment issue, not a code bug.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check tests/monitor/test_heat_fetch_live.py
git add tests/monitor/test_heat_fetch_live.py
git commit -m "test(monitor): double-gated live ak.fund_purchase_em heat probe"
```

---

## Task 5: Wire into `monitor_cmd.py` — fetch once + thread + replace the two None heat lines (TDD)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
  - import `heat_inputs_for`, `fetch_purchase_table` from `irc.monitor.heat_fetch`
  - `_process_fund` signature: add `purchase_table=None` (keyword, default None)
  - inside `_process_fund`: `restricted, aum_delta_pct = heat_inputs_for(fund.id, purchase_table=purchase_table)`
  - replace `restricted=None, aum_delta_pct=None` in the `FactorInputs(...)` with `restricted=restricted, aum_delta_pct=aum_delta_pct`
  - `run_monitor`: fetch the table ONCE next to where `con` is opened; pass `purchase_table=table` into the `_process_fund(...)` call
- Modify: `tests/commands/test_monitor_cmd_eval_wiring.py` (lambda → absorb `**kw`)
- Test (new behavior): `tests/commands/test_monitor_cmd_heat.py`

- [ ] **Step 1: Write the failing wiring tests**

Create `tests/commands/test_monitor_cmd_heat.py`:

```python
"""_process_fund wires heat restriction inputs from the purchase table (item 003).

Mirrors the constituent-wiring test style: stub every edge except the heat path,
then assert the resulting heat FactorScore. _process_fund must accept the table
as a keyword and default to None (offline / test callers) → heat_no_data.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from irc.commands import monitor_cmd as mc
from irc.monitor.types import MonitorFund, NarrativeDoc


class _MinCfg:
    class history:
        minimum_observations = 2


def _fund(fund_id: str, profile: str = "active_cn_equity") -> MonitorFund:
    return MonitorFund(
        id=fund_id, name_cn="测试", market="cn_off_exchange", analysis_profile=profile,
        themes=(), constituent_news=False, weights={"trend": 1.0},
        bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5,
    )


def _patch_edges(monkeypatch, fund_id: str) -> None:
    """Stub all I/O in _process_fund except the heat path."""
    monkeypatch.setattr(mc, "nav_series_for", lambda fid: None)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, repo_root: ())

    class _Imp:
        impacts = ()
        status = "empty_pool"
        cost_entries = ()

    monkeypatch.setattr(mc, "gather_impacts", lambda **kw: _Imp())

    class _Narr:
        doc = NarrativeDoc(fund_id, (), (), (), "empty_pool")
        cost_entries = ()

    monkeypatch.setattr(mc, "gather_narrative", lambda **kw: _Narr())


def _heat_score(view):
    return {s.name: s for s in view.factor_scores}["heat"]


def _table(rows):
    return pd.DataFrame(rows)


def test_process_fund_restricted_fund_gets_crowded_heat(tmp_path: Path, monkeypatch):
    _patch_edges(monkeypatch, "006533")
    table = _table([{"基金代码": "006533", "申购状态": "限大额", "日累计限定金额": 1e5}])
    view, _costs, _bundle = mc._process_fund(
        _fund("006533"), _MinCfg(), tmp_path, object(), purchase_table=table,
    )
    s = _heat_score(view)
    assert s.eligible is True and s.value == -0.5


def test_process_fund_open_fund_gets_calm_heat(tmp_path: Path, monkeypatch):
    _patch_edges(monkeypatch, "000083")
    table = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    view, _costs, _bundle = mc._process_fund(
        _fund("000083"), _MinCfg(), tmp_path, object(), purchase_table=table,
    )
    s = _heat_score(view)
    assert s.eligible is True and s.value == 0.3


def test_process_fund_no_table_defaults_to_heat_no_data(tmp_path: Path, monkeypatch):
    # No purchase_table kwarg → heat_inputs_for yields None → heat_no_data (no break).
    _patch_edges(monkeypatch, "000083")
    view, _costs, _bundle = mc._process_fund(_fund("000083"), _MinCfg(), tmp_path, object())
    s = _heat_score(view)
    assert s.eligible is False and s.reason == "heat_no_data"
```

> If `test_*_calm_heat` / `*_crowded_heat` come back `profile_ineligible`, confirm
> `"heat" in eligible_factors("active_cn_equity")` (per Task 3 note) — it should be eligible.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/commands/test_monitor_cmd_heat.py -q`
Expected: FAIL — `_process_fund()` got an unexpected keyword argument `purchase_table` (signature not yet updated).

- [ ] **Step 3: Update `_process_fund` — add the kwarg + heat wiring**

In `src/irc/commands/monitor_cmd.py`, add the import near the other monitor imports (after the
`from irc.monitor.fetch import ...` line):

```python
from irc.monitor.heat_fetch import fetch_purchase_table, heat_inputs_for
```

Change the `_process_fund` signature (currently `def _process_fund(fund, cfg, root, llm_config, *, con=None,)`):

```python
def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config, *, con=None, purchase_table=None,
) -> tuple[FundView, list, FundTraceBundle]:
```

Inside `_process_fund`, just BEFORE the `inp = FactorInputs(` construction (keeping the existing
valuation `val = ...` block from items 001/002 intact), add:

```python
    restricted, aum_delta_pct = heat_inputs_for(fund.id, purchase_table=purchase_table)
```

Then replace the two hardcoded heat lines inside `FactorInputs(...)`:

```python
        restricted=None,
        aum_delta_pct=None,
```

with:

```python
        restricted=restricted,
        aum_delta_pct=aum_delta_pct,
```

Leave `valuation_state=val.state, valuation_cached=val.cached` untouched.

- [ ] **Step 4: Fetch the table once in `run_monitor` + thread it**

In `run_monitor`, find the block that opens `con` (just before `views: list[FundView] = []`):

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

Immediately AFTER that block (still before `views = []`), fetch the purchase table ONCE:

```python
    purchase_table = fetch_purchase_table()  # ONE akshare call/run; None on failure → heat_no_data
    if purchase_table is None:
        _log.warning("monitor heat: purchase table unavailable → heat_no_data for all funds")
```

Then thread it into the per-fund call. Change:

```python
            view, costs, bundle = _process_fund(fund, cfg, root, llm_config, con=con)
```

to:

```python
            view, costs, bundle = _process_fund(
                fund, cfg, root, llm_config, con=con, purchase_table=purchase_table,
            )
```

- [ ] **Step 5: Fix the pre-existing eval-wiring monkeypatch lambda (absorb `**kw`)**

In `tests/commands/test_monitor_cmd_eval_wiring.py`, the `_patch_pipeline` lambda is currently
`lambda fund, cfg, root, llm:` and already breaks on `con=` (item-001 debt). Change it to absorb
keyword args:

```python
    monkeypatch.setattr(
        monitor_cmd, "_process_fund",
        lambda fund, cfg, root, llm, **kw: (next(view_iter), [],
                                            FundTraceBundle(fund.id, (), (), ())),
    )
```

(The `test_monitor_cmd_trace.py` and `test_acceptance_eval.py` lambdas already either use `**kw` or
call `_process_fund` positionally with the default — no change needed there. Verify in Step 7.)

- [ ] **Step 6: Run the new wiring tests**

Run: `uv run pytest tests/commands/test_monitor_cmd_heat.py -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the full monitor + command suites to confirm no regression**

Run: `uv run pytest tests/monitor/ tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_trace.py tests/commands/test_monitor_constituent.py tests/commands/test_acceptance_eval.py tests/monitor/test_acceptance_eval.py -q`
Expected: PASS — including `test_monitor_cmd_eval_wiring.py` which was RED at Task 0 (now fixed by Step 5). If any `_process_fund` monkeypatch elsewhere raises `unexpected keyword argument 'purchase_table'`, add `**kw` to that lambda too (same fix as Step 5).

> Note: `run_monitor` now makes a real `fetch_purchase_table()` call. Tests that exercise
> `run_monitor` end-to-end monkeypatch `_process_fund` (so the table is fetched but unused) — the
> real call still fires. If any offline `run_monitor` test becomes flaky/slow due to the live akshare
> call, monkeypatch it: `monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)` in
> that test's pipeline patcher (`_patch` / `_patch_pipeline`). Add this to `_patch_pipeline` in
> `test_monitor_cmd_eval_wiring.py` and `_patch` in `test_acceptance_eval.py` proactively so the
> offline suite never hits the network:
>
> ```python
>     monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)
> ```

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_heat.py tests/commands/test_monitor_cmd_eval_wiring.py`
Expected: no errors. (Watch the line-length-100 limit on the threaded `_process_fund(...)` call — the multi-line form above stays under 100.)

- [ ] **Step 9: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_heat.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_acceptance_eval.py
git commit -m "feat(monitor): wire heat restriction leg into monitor_cmd (item 003)"
```

---

## Task 6: Determinism + final verification

**Files:** none (verification only).

- [ ] **Step 1: Confirm KNOWN_NA_REASONS / determinism unaffected**

Run: `uv run pytest tests/monitor/test_known_na_reasons.py tests/monitor/test_factor_maps.py tests/monitor/test_factors.py -q`
Expected: PASS — `heat_no_data` is the only heat N/A reason; no new codes; `heat_score` untouched.

- [ ] **Step 2: Full monitor + heat slice**

Run: `uv run pytest tests/monitor/ tests/commands/ -q`
Expected: PASS (offline; live test SKIPPED). No regression in valuation wiring (items 001/002 tests still green).

- [ ] **Step 3: Final lint of the whole change**

Run: `uv run ruff check src/irc/monitor/heat_fetch.py src/irc/commands/monitor_cmd.py tests/monitor/test_heat_fetch.py tests/monitor/test_heat_fetch_live.py tests/commands/test_monitor_cmd_heat.py`
Expected: no errors.

- [ ] **Step 4: Size-budget check (CLAUDE.md: files < 200 lines)**

Run: `wc -l src/irc/monitor/heat_fetch.py`
Expected: well under 200 (≈ 90 lines). If `_process_fund` grew past comfortable size, that's acceptable (pre-existing function); do not refactor it in this item.

---

## Self-Review (done while authoring)

**Spec coverage (003-spec.md / design §5):**
- AC1 (new module, edge + pure, house pattern) → Tasks 1–2. ✓
- AC2 (restriction rule: status ∉ {开放申购} OR cap < 1e8; absent/unparseable → None) → Task 1 tests. ✓
- AC3 (`heat_inputs_for` returns `(parse, None)`, aum always None) → Task 2 tests. ✓
- AC4 (ONE call/run; CN direct) → Task 5 Step 4 (`fetch_purchase_table()` once in `run_monitor`); no proxy plumbing anywhere. ✓
- AC5 (availability contract: returns None not raises → heat_no_data + structured log) → Task 2 (`test_fetch_returns_none_when_fetch_raises`) + `_log.warning` in `fetch_purchase_table` and `run_monitor`. ✓
- AC6 (wire at the FactorInputs site; replace the two None lines) → Task 5 Step 3. ✓
- AC7 (no scoring change; heat_score handles aum=None) → Task 3 integration tests; `factor_maps.py` NOT in the file list. ✓
- AC8 (heat lights for all 10) → Task 4 live probe asserts all 10 ids parse. ✓
- Invariants §6 (eligibility behind `eligible_factors`, heat_no_data in KNOWN_NA_REASONS, determinism) → Tasks 3 + 6. ✓
- Tests §8 (pure / integration / live double-gated / determinism) → Tasks 1–4, 6. ✓

**Judgment calls flagged for the implementer:**
1. **akshare import = LAZY** (default `fetch=None`, `import akshare` inside the body) — honors the
   house "no module-top akshare" convention while keeping the spec's injectable default. (Justified
   in the Context section.)
2. **Missing-cap-column degrades to the status leg, NOT to None.** Spec §5.1 says absent/unparseable
   *row* → None, but the rule is an OR of two legs; if `申购状态` is present and parseable, we have
   an honest signal even without the cap column. Returning None there would discard a real status
   signal. The cap leg simply can't fire (`_cap_below_threshold` → False). A *missing status column*
   or *absent fund* → None (no honest signal). This is a deliberate reading of "unparseable row" as
   "no parseable status," not "any column missing." If the reviewer prefers strict (any missing
   column → None), tighten `parse_purchase_status` to also `return None` when `_CAP_COL` is absent —
   one-line change, and adjust `test_missing_cap_column_*`.
3. **`场内交易` (on-exchange ETF) counts as restricted** because it is ∉ {开放申购}. The monitor
   set's only ETF-联接 (`008986`) reports `开放申购`, so the set is unaffected; the behavior is the
   literal spec rule. Noted, not changed.
4. **Fixing item-001's pre-existing red** (`test_monitor_cmd_eval_wiring.py` lambda) is in-scope
   because item 003 touches the same call site; a reviewer expecting a clean green suite would
   otherwise see it as item-003 breakage.

**Type/signature consistency:** `fetch_purchase_table(fetch=None)`, `parse_purchase_status(table, fund_id) -> bool | None`, `heat_inputs_for(fund_id, *, purchase_table) -> tuple[bool|None, float|None]`, `_process_fund(..., *, con=None, purchase_table=None)` — used identically across Tasks 1–5. ✓

**No placeholders:** every code/test step contains the full content. ✓
