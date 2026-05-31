# Item 004 — Deterministic `compute_ratios` key-ratios surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, deterministic `compute_ratios(financials: FilingDigest) -> KeyRatios` that surfaces ROE + gross_margin (with `debt_equity`/`fcf_yield` honestly degrading to `None`) as a reason-only Chinese fragment appended to the per-constituent `one_line_view` — no state, no gate, no citation.

**Architecture:** Mirror the `consensus.py` (pure metric) + `_pe_pb_fragment` (reason-only Chinese fragment) precedents exactly. New pure module `src/irc/fundamentals/ratios.py` holds the frozen `KeyRatios` dataclass, `compute_ratios`, and the `ratios_reason_fragment` helper. `FilingDigest` gains one defaulted `roe: float | None` field, populated by a NEW `盈利能力`-section reader inside the existing `fetch_cn_filing_digest` I/O wrapper (NOT by editing the shared `_common_metric`, which hard-filters `常用指标`). The CN `FilingDigest` is threaded out of `_evidence_for_constituent` to the `_one_line_view` call site so the fragment can be appended within the hard `[:60]` cap.

**Tech Stack:** Python 3.12, frozen dataclasses, pandas (existing fetch path only), pytest. No new dependency, no LLM, no network.

---

## Why a new module (`ratios.py`), not `types.py`

`src/irc/fundamentals/types.py` is already **333 lines** — over the 200-line budget. Adding `KeyRatios` + `compute_ratios` + the fragment helper there would worsen it. CONTEXT.md (already committed at 4b9f050, lines 132–133) and spec D8/D9 both name `src/irc/fundamentals/ratios.py` as the home, parallel to `consensus.py` (a single-purpose pure module). **Decision: `KeyRatios`, `compute_ratios`, and `ratios_reason_fragment` ALL live in `src/irc/fundamentals/ratios.py`.** Only the one-field `roe` addition lands in `types.py`.

## File Structure (locked)

- **Create** `src/irc/fundamentals/ratios.py` — `KeyRatios` frozen dataclass, `compute_ratios`, `ratios_reason_fragment` (pure; no I/O).
- **Create** `tests/fundamentals/test_ratios.py` — mirrors `ratios.py`.
- **Modify** `src/irc/fundamentals/types.py:165-175` — add `roe: float | None = None` to `FilingDigest` (appended LAST, after `source_url`, to preserve the one fully-positional construction).
- **Modify** `src/irc/fundamentals/akshare_filing.py` — add `_KEY_ROE`, a `_profitability_metric` reader for the `盈利能力` section, and wire `roe=` into the `FilingDigest(...)` build.
- **Modify** `src/irc/fundamentals/snapshot.py:309-423` (`_evidence_for_constituent`) and `:530-543` (`_build_active_fund_snapshot` call site) and `:426-443` (`_one_line_view`) — thread the CN `FilingDigest` to the `one_line_view` call site and append the fragment within the `[:60]` cap.
- **Modify (test only)** `tests/fundamentals/test_snapshot.py:466-468` — update the `_fake_evidence_for_constituent` fake to the new 3-tuple return arity.
- **Touch (tests)** `tests/fundamentals/test_types.py`, `tests/fundamentals/test_akshare_fundamentals.py`, `tests/fundamentals/test_snapshot_acceptance.py` — new/updated assertions per task.

## Verified facts the implementer must not re-derive

- `_common_metric` (`akshare_filing.py:106`) **hard-codes** `选项 == "常用指标"` and is shared by revenue/NI/cost. DO NOT edit it. Add a SEPARATE `盈利能力`-section reader.
- `净资产收益率` is already in the fetched `stock_financial_abstract` frame (one AkShare call returns all sections) — the test fixture `_ABSTRACT_FRAME` (`test_akshare_fundamentals.py:410-420`) has row `"盈利能力" / "净资产收益率"` with `0.18` for the latest `20260331` column. NO new network call.
- `gross_margin` and `roe` are read from the SAME `latest` period column → period-aligned. Caveat `口径未核实` disclaims annualisation.
- The `[:60]` cap (`snapshot.py:443`) is a HARD byte-stability constraint (AC11). DO NOT raise it. Append the fragment to the `fragments` list before the join+cap, OR concatenate within the cap — best-effort.
- `debt_equity` / `fcf_yield` inputs (total debt, equity, FCF, market cap) are NOT on `FilingDigest` → always `None` today. They must be OMITTED from the fragment, never rendered as the string `"None"`.
- `FilingDigest` must stay frozen; `roe` is defaulted so old cache files (`snapshot_cache.py:66` rehydrates `FilingDigest(**f)`) re-hydrate without churn.
- CONTEXT.md entries for `KeyRatios` / `compute_ratios` / `FilingDigest.roe` ALREADY exist (committed 4b9f050, lines 132–134). NO new ADR (`docs/adr/0010-*.md` is OVERRULED — reuses ADR 0009).

---

### Task 1: Add `roe` field to `FilingDigest`

**Files:**
- Modify: `src/irc/fundamentals/types.py:165-175`
- Test: `tests/fundamentals/test_types.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/fundamentals/test_types.py` (after `test_filing_digest_defaults_and_optional_numerics`, ~line 102):

```python
def test_filing_digest_roe_defaults_none_and_is_settable() -> None:
    # roe defaults to None (existing call sites/cache files unaffected).
    default = FilingDigest(
        symbol="600519.SH",
        fiscal_period="2026Q1",
        filed_at_iso="2026-04-30",
        revenue_yoy=0.06,
        net_income_yoy=0.04,
        gross_margin=0.69,
    )
    assert default.roe is None
    # roe is the LAST positional field (after source_url) — preserves the one
    # fully-positional construction in test_snapshot_acceptance.py:69.
    positional = FilingDigest(
        "600519.SH", "2026Q1", "2026-04-30", 0.06, 0.04, 0.69, "", "https://x", 0.18,
    )
    assert positional.roe == 0.18
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fundamentals/test_types.py::test_filing_digest_roe_defaults_none_and_is_settable -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'roe'` (and the positional construction raises `too many positional arguments`).

- [ ] **Step 3: Add the `roe` field (appended LAST, defaulted)**

In `src/irc/fundamentals/types.py`, change the `FilingDigest` dataclass (lines 165–175) to:

```python
@dataclass(frozen=True)
class FilingDigest:
    symbol: str
    fiscal_period: str
    filed_at_iso: str
    revenue_yoy: float | None
    net_income_yoy: float | None
    gross_margin: float | None
    guidance_text: str = ""
    source_url: str = ""
    # Item 004: provider-computed 净资产收益率 (ROE), ratio units (0.18 = 18%),
    # sourced from the 盈利能力 section of stock_financial_abstract. Defaulted so
    # existing call sites + cached snapshots re-hydrate without churn. None when
    # the row is absent/NaN (ROE absence never fails the digest). Reason-only.
    roe: float | None = None
```

> NOTE: `roe` is appended AFTER `source_url`. Do NOT insert it between `gross_margin` and `guidance_text` — `test_snapshot_acceptance.py:69` constructs `FilingDigest(s, "2024Q1", "2024-04-15", 0.1, 0.1, 0.3, "", "")` (8 positional args) and an inserted field would silently mis-bind the 7th/8th positionals.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fundamentals/test_types.py -q`
Expected: PASS (all type tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/types.py tests/fundamentals/test_types.py
git commit -m "feat(fundamentals): add defaulted roe field to FilingDigest (004)"
```

---

### Task 2: Extract `roe` from the `盈利能力` section in `fetch_cn_filing_digest`

**Files:**
- Modify: `src/irc/fundamentals/akshare_filing.py` (add `_KEY_ROE` constant ~line 24; add `_profitability_metric` ~after line 114; wire `roe=` into the `FilingDigest(...)` build ~line 147)
- Test: `tests/fundamentals/test_akshare_fundamentals.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_akshare_fundamentals.py` (after `test_fetch_cn_filing_digest_computes_yoy_and_margin_for_latest_quarter`, ~line 438). The module already imports `pd`, `pytest`, `patch`, `fetch_cn_filing_digest`, and defines `_ABSTRACT_FRAME` (which carries the `"盈利能力" / "净资产收益率"` row with `0.18` for `20260331`):

```python
def test_fetch_cn_filing_digest_surfaces_roe_from_profitability_section() -> None:
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = _ABSTRACT_FRAME
        digest = fetch_cn_filing_digest("600519")
    assert digest is not None
    # 净资产收益率 for the latest column (20260331) is 0.18, read from the
    # 盈利能力 section (NOT 常用指标 — which _common_metric hard-filters).
    assert digest.roe == pytest.approx(0.18)


def test_fetch_cn_filing_digest_roe_none_when_section_absent() -> None:
    # Frame with NO 盈利能力 row: revenue/NI/cost still present → digest produced,
    # but roe degrades to None (ROE absence does NOT fail the digest).
    frame = pd.DataFrame({
        "选项": ["常用指标", "常用指标", "常用指标"],
        "指标": ["归母净利润", "营业总收入", "营业成本"],
        "20260331": [27.24e9, 54.70e9, 17.19e9],
        "20250331": [26.84e9, 51.44e9, 14.43e9],
    })
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = frame
        digest = fetch_cn_filing_digest("600519")
    assert digest is not None
    assert digest.roe is None


def test_fetch_cn_filing_digest_roe_none_when_value_nan() -> None:
    frame = pd.DataFrame({
        "选项": ["常用指标", "常用指标", "常用指标", "盈利能力"],
        "指标": ["归母净利润", "营业总收入", "营业成本", "净资产收益率"],
        "20260331": [27.24e9, 54.70e9, 17.19e9, float("nan")],
        "20250331": [26.84e9, 51.44e9, 14.43e9, 0.17],
    })
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = frame
        digest = fetch_cn_filing_digest("600519")
    assert digest is not None
    assert digest.roe is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_fundamentals.py -q -k roe`
Expected: FAIL — first test fails `assert digest.roe == ... ` (currently `roe` is the new default `None`); the other two pass-by-accident only if `None` (acceptable), but the first locks the behaviour red.

- [ ] **Step 3: Add the constant and the `盈利能力` reader**

In `src/irc/fundamentals/akshare_filing.py`, add the constant next to the existing keys (after line 24, `_KEY_COST = "营业成本"`):

```python
_KEY_ROE = "净资产收益率"
```

Add a NEW reader directly after `_common_metric` (after line 114). It MUST NOT edit `_common_metric` — it reads the `盈利能力` section instead of `常用指标`:

```python
def _profitability_metric(df: pd.DataFrame, name: str, col: str) -> float | None:
    """Read a 盈利能力-section metric (e.g. 净资产收益率/ROE). Separate from
    _common_metric, which hard-filters 常用指标 (shared by revenue/NI/cost)."""
    matches = df[(df.get("选项") == "盈利能力") & (df.get("指标") == name)]
    if matches.empty or col not in matches.columns:
        return None
    raw = matches.iloc[0][col]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value
```

- [ ] **Step 4: Wire `roe=` into the `FilingDigest(...)` build**

In `fetch_cn_filing_digest`, read ROE for the latest column right after the gross_margin computation (after line 145, `gross_margin = ...`), and pass it into the return. Change the return block (lines 145–155) to:

```python
    gross_margin = 1 - (cost / revenue) if revenue else None
    roe = _profitability_metric(df, _KEY_ROE, latest)
    period, filed = _yyyymmdd_to_period(latest)
    return FilingDigest(
        symbol=_to_qualified_symbol(akshare_symbol),
        fiscal_period=period,
        filed_at_iso=filed,
        revenue_yoy=revenue_yoy,
        net_income_yoy=net_income_yoy,
        gross_margin=gross_margin,
        source_url=_SINA_FINSUMMARY_URL.format(symbol=akshare_symbol),
        roe=roe,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_fundamentals.py -q`
Expected: PASS (all, including the three new `roe` tests and the pre-existing margin/YoY tests, which are unchanged because `_ABSTRACT_FRAME` already carried the `盈利能力` row).

- [ ] **Step 6: Verify file-size budget**

Run: `wc -l src/irc/fundamentals/akshare_filing.py`
Expected: under 200 lines (was 156; adding ~12 lines stays well under). If over 200, STOP and extract the reader to a helper module — but it will not be.

- [ ] **Step 7: Commit**

```bash
git add src/irc/fundamentals/akshare_filing.py tests/fundamentals/test_akshare_fundamentals.py
git commit -m "feat(fundamentals): extract roe from 盈利能力 section in filing digest (004)"
```

---

### Task 3: Create `KeyRatios` + `compute_ratios` (pure, deterministic)

**Files:**
- Create: `src/irc/fundamentals/ratios.py`
- Test: `tests/fundamentals/test_ratios.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/fundamentals/test_ratios.py`:

```python
from __future__ import annotations

import dataclasses
import inspect

import pytest

from irc.fundamentals.ratios import KeyRatios, compute_ratios
from irc.fundamentals.types import FilingDigest


def _digest(*, gross_margin=None, roe=None) -> FilingDigest:
    return FilingDigest(
        symbol="600519.SH",
        fiscal_period="2026Q1",
        filed_at_iso="2026-04-30",
        revenue_yoy=0.06,
        net_income_yoy=0.04,
        gross_margin=gross_margin,
        roe=roe,
    )


# ---------- AC1: KeyRatios shape + immutability ----------

def test_key_ratios_has_four_fields_all_default_none() -> None:
    kr = KeyRatios()
    assert kr.roe is None
    assert kr.debt_equity is None
    assert kr.gross_margin is None
    assert kr.fcf_yield is None


def test_key_ratios_is_frozen() -> None:
    kr = KeyRatios()
    with pytest.raises(dataclasses.FrozenInstanceError):
        kr.roe = 0.1  # type: ignore[misc]


# ---------- AC3: gross_margin pass-through ----------

def test_gross_margin_pass_through_finite() -> None:
    kr = compute_ratios(_digest(gross_margin=0.69))
    assert kr.gross_margin == pytest.approx(0.69)


def test_gross_margin_none_stays_none() -> None:
    assert compute_ratios(_digest(gross_margin=None)).gross_margin is None


def test_gross_margin_nan_screened_to_none() -> None:
    assert compute_ratios(_digest(gross_margin=float("nan"))).gross_margin is None


# ---------- AC4: roe pass-through ----------

def test_roe_pass_through_finite() -> None:
    assert compute_ratios(_digest(roe=0.18)).roe == pytest.approx(0.18)


def test_roe_none_stays_none() -> None:
    assert compute_ratios(_digest(roe=None)).roe is None


def test_roe_nan_screened_to_none() -> None:
    assert compute_ratios(_digest(roe=float("nan"))).roe is None


# ---------- AC5: debt_equity / fcf_yield always None today ----------

def test_debt_equity_and_fcf_yield_degrade_to_none_today() -> None:
    # FilingDigest carries no debt/equity/FCF/market-cap line items → always None.
    kr = compute_ratios(_digest(gross_margin=0.69, roe=0.18))
    assert kr.debt_equity is None
    assert kr.fcf_yield is None


# ---------- AC2: determinism ----------

def test_compute_ratios_is_deterministic() -> None:
    d = _digest(gross_margin=0.69, roe=0.18)
    assert compute_ratios(d) == compute_ratios(d)


# ---------- AC2: purity (no I/O imports in the module) ----------

def test_compute_ratios_source_imports_no_io() -> None:
    src = inspect.getsource(compute_ratios)
    for forbidden in ("akshare", "duckdb", "requests", "open(", "llm"):
        assert forbidden not in src
    import irc.fundamentals.ratios as mod
    mod_src = inspect.getsource(mod)
    for forbidden in ("import akshare", "import duckdb", "from irc.llm"):
        assert forbidden not in mod_src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_ratios.py -q`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'irc.fundamentals.ratios'`.

- [ ] **Step 3: Create `src/irc/fundamentals/ratios.py`**

```python
"""Pure key-ratios surface. No I/O, no LLM.

`compute_ratios(financials: FilingDigest) -> KeyRatios` returns a small frozen
record `{roe, debt_equity, gross_margin, fcf_yield}`, all RATIO units
(0.18 = 18%, matching gross_margin / consensus_upside_pct / qdii_premium_pct),
all `float | None`. `roe` and `gross_margin` are pass-throughs of the already-
fetched `FilingDigest` fields (NaN screened to None). `debt_equity` and
`fcf_yield` are ALWAYS None today — their balance-sheet / cash-flow / market-cap
input line items are not yet fetched — and self-activate with zero further wiring
when a richer source lands (wire-but-degrade-to-None, the same contract ADR 0009
records for consensus_upside_pct). Reason-only: never drives a state, gate, or
classifier; carries no citation (see CONTEXT.md `KeyRatios` / `compute_ratios`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from irc.fundamentals.types import FilingDigest


@dataclass(frozen=True)
class KeyRatios:
    roe: float | None = None
    debt_equity: float | None = None
    gross_margin: float | None = None
    fcf_yield: float | None = None


def _finite(value: float | None) -> float | None:
    """Pass-through a finite float; screen None / NaN to None (no fabrication)."""
    if value is None or math.isnan(value):
        return None
    return value


def compute_ratios(financials: FilingDigest) -> KeyRatios:
    """Pure, deterministic. Same FilingDigest in → equal KeyRatios out.

    roe / gross_margin pass through (NaN → None). debt_equity / fcf_yield have no
    input line items on FilingDigest today → None (degrade-to-None, ADR 0009).
    """
    return KeyRatios(
        roe=_finite(financials.roe),
        debt_equity=None,
        gross_margin=_finite(financials.gross_margin),
        fcf_yield=None,
    )
```

> NOTE on units: `gross_margin` is `1 - cost/revenue` (ratio, `akshare_filing.py:145`); `净资产收益率`/`roe` from AkShare is already a ratio (`0.18` in `_ABSTRACT_FRAME`); both match the `consensus_upside_pct` ratio convention (CONTEXT.md). No transformation — pass-through preserves units.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_ratios.py -q`
Expected: PASS (all 11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/ratios.py tests/fundamentals/test_ratios.py
git commit -m "feat(fundamentals): pure deterministic compute_ratios + KeyRatios (004)"
```

---

### Task 4: Add the reason-only `ratios_reason_fragment` helper

**Files:**
- Modify: `src/irc/fundamentals/ratios.py`
- Test: `tests/fundamentals/test_ratios.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_ratios.py`:

```python
from irc.fundamentals.ratios import ratios_reason_fragment  # noqa: E402


# ---------- AC7 / G4: compact reason fragment, non-None only ----------

def test_fragment_shows_roe_and_gross_margin_compact() -> None:
    frag = ratios_reason_fragment(KeyRatios(roe=0.18, gross_margin=0.69))
    # Compact form fits the [:60] one_line_view cap; caveat present.
    assert frag == "（ROE 18%·毛利69%，口径未核实）"


def test_fragment_omits_none_subfields_never_renders_none() -> None:
    # debt_equity / fcf_yield are None today → omitted (never the string "None").
    frag = ratios_reason_fragment(KeyRatios(roe=0.18, gross_margin=0.69))
    assert "None" not in frag
    assert "负债" not in frag and "FCF" not in frag


def test_fragment_roe_only() -> None:
    assert ratios_reason_fragment(KeyRatios(roe=0.18)) == "（ROE 18%，口径未核实）"


def test_fragment_gross_margin_only() -> None:
    assert ratios_reason_fragment(KeyRatios(gross_margin=0.69)) == "（毛利69%，口径未核实）"


def test_fragment_empty_when_all_none() -> None:
    assert ratios_reason_fragment(KeyRatios()) == ""


def test_fragment_carries_no_ref_marker() -> None:
    import re
    frag = ratios_reason_fragment(KeyRatios(roe=0.18, gross_margin=0.69))
    assert re.search(r"\[ref:[0-9a-f]{16}\]", frag) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_ratios.py -q -k fragment`
Expected: FAIL — `ImportError: cannot import name 'ratios_reason_fragment'`.

- [ ] **Step 3: Add the helper to `ratios.py`**

Append to `src/irc/fundamentals/ratios.py`:

```python
def ratios_reason_fragment(ratios: KeyRatios) -> str:
    """Optional compact Chinese ratios fragment (reason-only, mirrors
    valuation_fundamental._pe_pb_fragment). Emits ONLY non-None sub-fields;
    returns "" when all four are None. Percent display, ratio→% for readability.
    Carries the 口径未核实 caveat (filing-evidence-semantics, ADR 0001 §5);
    structurally separate from the locked 财报已披露（口径未核实）summary phrase.
    Never injects a [ref:...] marker. Best-effort within the one_line_view [:60]
    cap (debt_equity / fcf_yield are None today, so today's surface is ≤ ~22 chars).
    """
    parts: list[str] = []
    if ratios.roe is not None:
        parts.append(f"ROE {ratios.roe:.0%}")
    if ratios.gross_margin is not None:
        parts.append(f"毛利{ratios.gross_margin:.0%}")
    # debt_equity / fcf_yield are None today → never appended (omitted, not "None").
    if ratios.debt_equity is not None:
        parts.append(f"负债权益{ratios.debt_equity:.2f}")
    if ratios.fcf_yield is not None:
        parts.append(f"FCF {ratios.fcf_yield:.0%}")
    if not parts:
        return ""
    return f"（{'·'.join(parts)}，口径未核实）"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_ratios.py -q`
Expected: PASS (all fragment + compute tests).

- [ ] **Step 5: Verify file-size budget**

Run: `wc -l src/irc/fundamentals/ratios.py`
Expected: under 200 lines (≈ 75). PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/ratios.py tests/fundamentals/test_ratios.py
git commit -m "feat(fundamentals): compact reason-only ratios fragment (004)"
```

---

### Task 5: Thread the CN `FilingDigest` out of `_evidence_for_constituent`

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py:309-423` (return arity) and `:530-543` (call site)
- Modify (test fake): `tests/fundamentals/test_snapshot.py:466-468`
- Test: `tests/fundamentals/test_snapshot.py`

This task is a PURE refactor: change `_evidence_for_constituent` to also return the CN `FilingDigest` (or `None`), with NO change to `one_line_view` content yet. That lands in Task 6.

- [ ] **Step 1: Write the failing test**

Append to `tests/fundamentals/test_snapshot.py` (the module already imports `snapshot`/`FilingDigest`/`FundHolding` — confirm the imports; if `compute_ratios`/`KeyRatios` are needed they are added in Task 6):

```python
def test_evidence_for_constituent_returns_cn_digest_third(monkeypatch) -> None:
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    monkeypatch.setattr(_snap, "fetch_cn_filing_digest", lambda s: digest)
    monkeypatch.setattr(_snap, "fetch_cn_broker_reports", lambda s: ())
    monkeypatch.setattr(_snap, "fetch_cn_stock_news", lambda s, top_k=3: ())
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    result = _snap._evidence_for_constituent(holding, fund_id="fund_x")
    assert len(result) == 3  # (evidence, failures, digest)
    evidence, failures, returned_digest = result
    assert returned_digest is digest


def test_evidence_for_constituent_digest_none_for_non_cn(monkeypatch) -> None:
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding
    monkeypatch.setattr(_snap, "fetch_hk_filing_digest", lambda s: None)
    monkeypatch.setattr(_snap, "fetch_hk_stock_news", lambda s, top_k=3: ())
    monkeypatch.setattr(_snap, "hk_news_adapter_available", lambda: True)
    holding = FundHolding("0700.HK", "腾讯", 10.0, "HK", "00700")
    evidence, failures, digest = _snap._evidence_for_constituent(holding, fund_id="f")
    assert digest is None  # HK/US digests are out of scope for ratios (spec non-goal)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -q -k evidence_for_constituent_returns`
Expected: FAIL — `_evidence_for_constituent` currently returns a 2-tuple, so `len(result) == 3` fails (and the unpack `evidence, failures, digest = ...` raises `ValueError: not enough values to unpack`).

- [ ] **Step 3: Change `_evidence_for_constituent` to return a 3-tuple**

In `src/irc/fundamentals/snapshot.py`, update the signature/docstring (lines 309–317):

```python
def _evidence_for_constituent(
    holding: FundHolding,
    *,
    fund_id: str,
) -> tuple[tuple[ThesisEvidence, ...], list[str], FilingDigest | None]:
    """Fetch market-routed evidence for one holding.

    Returns (evidence_tuple, failure_reasons_list, cn_filing_digest_or_None).
    The CN digest is threaded out (it is dropped today) so the per-constituent
    ratios fragment can be appended to one_line_view at the call site (item 004).
    HK/US digests are NOT surfaced as ratios (spec non-goal) → digest is None.
    """
    failures: list[str] = []
    evidence: list[ThesisEvidence] = []
    cn_digest: FilingDigest | None = None
```

In the CN branch (`holding.exchange in ("SH", "SZ", "BJ")`), where the digest is fetched and consumed (around lines 337–346), capture it. Change the `if not _filing_exc:` block (lines 337–346) to also set `cn_digest`:

```python
        if not _filing_exc:
            if digest is None:
                failures.append(f"filing_empty:{holding.symbol}")
            else:
                cn_digest = digest
                evidence.append(ThesisEvidence(
                    type="filing", source=digest.symbol,
                    url=digest.source_url, date=digest.filed_at_iso,
                    summary=f"{digest.symbol} {digest.fiscal_period} 财报已披露（口径未核实）",
                    citation_kind="data", **common,
                ))
```

> Leave the HK branch (lines 379–397) and the US/UNKNOWN branches untouched — `cn_digest` stays `None` there (spec non-goal: no HK/US ratio path in V1).

Update the final `return` of the function (line 423, `return tuple(evidence), failures`) to:

```python
    return tuple(evidence), failures, cn_digest
```

Add `FilingDigest` to the snapshot.py imports if not already present.

- [ ] **Step 4: Update the real call site in `_build_active_fund_snapshot`**

In `src/irc/fundamentals/snapshot.py`, the loop at lines 532–543 unpacks the 2-tuple. Change line 533 from:

```python
        evidence, failures = _evidence_for_constituent(h, fund_id=fund_id)
```

to:

```python
        evidence, failures, _cn_digest = _evidence_for_constituent(h, fund_id=fund_id)
```

> Leave `one_line_view=_one_line_view(h, evidence)` (line 542) unchanged in THIS task — `_cn_digest` is captured but not yet used. Task 6 wires it in.

- [ ] **Step 5: Update the test fake in `test_snapshot.py`**

In `tests/fundamentals/test_snapshot.py`, the `_fake_evidence_for_constituent` (lines 466–468) returns a 2-tuple. Update it to the 3-tuple arity:

```python
    def _fake_evidence_for_constituent(holding, *, fund_id):
        # HK holding hits the no-filings path in real code; emulate empty.
        return (), [f"filing_fetch_failed:{holding.symbol}:KeyError"], None
```

- [ ] **Step 5b: Fix ALL four existing 2-tuple unpacks of `_evidence_for_constituent`**

VERIFIED — four existing tests unpack the OLD 2-tuple and WILL break. Update each to the 3-tuple arity (capture the digest into a throwaway `_`):

- `tests/opportunity/test_thesis_evidence.py:657` — change `evidence, _failures = snap_mod._evidence_for_constituent(` → `evidence, _failures, _digest = snap_mod._evidence_for_constituent(`
- `tests/opportunity/test_thesis_evidence.py:688` — same change (`evidence, _failures = ...` → `evidence, _failures, _digest = ...`)
- `tests/commands/test_opportunity_cmd.py:760` — change `_, failures = _evidence_for_constituent(holding, fund_id="005827")` → `_, failures, _digest = _evidence_for_constituent(holding, fund_id="005827")`
- `tests/commands/test_opportunity_cmd.py:800` — same change (`_, failures = ...` → `_, failures, _digest = ...`)

Re-confirm none remain: `grep -n "_evidence_for_constituent" tests/opportunity/test_thesis_evidence.py tests/commands/test_opportunity_cmd.py` — every unpack must now bind three names (the `def`/docstring grep hits at `test_thesis_evidence.py:628,633,669` are not unpacks; leave them).

- [ ] **Step 6: Run the full fundamentals + opportunity suites to verify the refactor is clean**

Run: `uv run pytest tests/fundamentals/test_snapshot.py tests/fundamentals/test_snapshot_acceptance.py tests/opportunity/test_thesis_evidence.py tests/commands/test_opportunity_cmd.py -q`
Expected: PASS — including the two new tests and the four fixed unpacks from Step 5b.

- [ ] **Step 7: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_snapshot.py tests/opportunity/test_thesis_evidence.py tests/commands/test_opportunity_cmd.py
git commit -m "refactor(fundamentals): thread CN filing digest out of _evidence_for_constituent (004)"
```

---

### Task 6: Append the ratios fragment to `one_line_view` within the `[:60]` cap

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py:426-443` (`_one_line_view`) and `:542` (call site)
- Test: `tests/fundamentals/test_snapshot.py`, `tests/fundamentals/test_snapshot_acceptance.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_snapshot.py`:

```python
def test_one_line_view_appends_ratios_fragment_within_cap() -> None:
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest, ThesisEvidence
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    view = _snap._one_line_view(holding, (ev,), digest)
    assert "ROE 18%" in view
    assert "毛利69%" in view
    assert "口径未核实" in view
    assert len(view) <= 60  # AC11 hard cap NOT raised


def test_one_line_view_byte_identical_when_digest_none() -> None:
    # AC11: rows where the fragment is empty/None are byte-stable vs the old behaviour.
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, ThesisEvidence
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    # digest=None → no fragment → byte-identical to the pre-004 join+cap output.
    assert _snap._one_line_view(holding, (ev,), None) == ev.summary[:24][:60]


def test_one_line_view_no_digest_arg_defaults_none() -> None:
    # Back-compat: the third arg is defaulted so unrelated call sites are unaffected.
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding
    assert _snap._one_line_view(FundHolding("X", "x", 1.0, "SH", "X"), ()) == "证据获取失败"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -q -k one_line_view`
Expected: FAIL — `_one_line_view()` currently takes 2 args; passing a third raises `TypeError`.

- [ ] **Step 3: Update `_one_line_view` to accept + append the fragment**

In `src/irc/fundamentals/snapshot.py`, change `_one_line_view` (lines 426–443). Add the import at the top of the module (with the other `irc.fundamentals` imports):

```python
from irc.fundamentals.ratios import compute_ratios, ratios_reason_fragment
```

Then:

```python
def _one_line_view(
    holding: FundHolding,
    evidence: tuple[ThesisEvidence, ...],
    cn_digest: FilingDigest | None = None,
) -> str:
    """≤60-char deterministic label. Empty evidence → '证据获取失败'.

    When a CN FilingDigest is supplied (item 004), a compact reason-only ratios
    fragment (ROE / 毛利 today; debt_equity / fcf_yield omitted while None) is
    appended, best-effort within the HARD [:60] cap (NOT raised — AC11). The
    fragment is empty when the digest carries no ROE and no gross_margin, so rows
    without ratios stay byte-identical to the pre-004 output.
    """
    if not evidence:
        return "证据获取失败"
    fragments: list[str] = []
    by_type: dict[str, ThesisEvidence | None] = {"filing": None, "broker": None, "news": None}
    for e in evidence:
        if e.type in by_type and by_type[e.type] is None:
            by_type[e.type] = e
    if by_type["filing"] is not None:
        fragments.append(by_type["filing"].summary[:24])
    if by_type["broker"] is not None:
        fragments.append(by_type["broker"].summary[:18])
    if by_type["news"] is not None:
        fragments.append(by_type["news"].summary[:24])
    if not fragments:
        return "证据获取失败"
    if cn_digest is not None:
        ratio_frag = ratios_reason_fragment(compute_ratios(cn_digest))
        if ratio_frag:
            fragments.append(ratio_frag)
    return " · ".join(fragments)[:60]
```

> The `[:60]` cap on the final join is UNCHANGED. The ratios fragment joins the existing `fragments` list and is truncated by the same cap — best-effort, no cap raise. When `cn_digest` is `None` (HK/US, or filing_empty) OR the fragment is `""` (no ROE and no gross_margin), the output is byte-identical to pre-004.

- [ ] **Step 4: Wire the digest at the call site**

In `_build_active_fund_snapshot`, change line 542 from:

```python
            one_line_view=_one_line_view(h, evidence),
```

to:

```python
            one_line_view=_one_line_view(h, evidence, _cn_digest),
```

(`_cn_digest` was captured in Task 5 Step 4.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -q -k one_line_view`
Expected: PASS (all three new tests).

- [ ] **Step 6: Run the acceptance suite — confirm the fragment lands end-to-end and rows without ratios are stable**

Run: `uv run pytest tests/fundamentals/test_snapshot_acceptance.py -q`
Expected: PASS. NOTE: `test_g6_a` fixtures supply `gross_margin=0.45` but no `roe` → those `one_line_view`s now carry `（毛利45%，口径未核实）` if it fits the cap. The acceptance tests assert on evidence counts/scope/kind, NOT on `one_line_view` byte content, so they stay green. If any acceptance test DOES assert `one_line_view` content and now fails, that is a real byte change for ratio-bearing rows (expected per AC7) — update that assertion to include the fragment; do NOT suppress the fragment.

- [ ] **Step 7: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_snapshot.py
git commit -m "feat(fundamentals): append reason-only ratios fragment to one_line_view (004)"
```

---

### Task 7: Lock PURITY of `compute_ratios` (no I/O, same-in→same-out)

**Files:**
- Test: `tests/fundamentals/test_ratios.py`

This task adds explicit AC2 purity locks beyond the ad-hoc determinism test in Task 3 (a dedicated regression so a future edit that sneaks in I/O fails loudly).

- [ ] **Step 1: Write the failing/locking test**

Append to `tests/fundamentals/test_ratios.py`:

```python
def test_compute_ratios_no_module_level_side_effects() -> None:
    # Importing the module must not perform I/O or call akshare/duckdb/llm.
    import importlib
    import irc.fundamentals.ratios as mod
    importlib.reload(mod)  # re-import: raises if import does any forbidden effect
    # 1000x repeated calls are byte-stable (determinism under repetition).
    d = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    results = {mod.compute_ratios(d) for _ in range(1000)}
    assert len(results) == 1  # single equal value → frozen dataclass hashes equal


def test_compute_ratios_does_not_mutate_input() -> None:
    import dataclasses
    d = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    snapshot = dataclasses.astuple(d)
    compute_ratios(d)
    assert dataclasses.astuple(d) == snapshot  # input untouched (immutability)
```

- [ ] **Step 2: Run tests to verify they pass (purity already holds)**

Run: `uv run pytest tests/fundamentals/test_ratios.py -q -k "purity or no_module or does_not_mutate or source_imports"`
Expected: PASS — `compute_ratios` is already pure from Task 3. These are regression locks; if any fails, the implementation regressed purity — STOP and fix `ratios.py`, do not weaken the test.

> KeyRatios is a frozen dataclass → hashable → the `set` comprehension collapses 1000 equal results to one. If it fails with `unhashable type`, KeyRatios was made non-frozen — revert that.

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_ratios.py
git commit -m "test(fundamentals): lock compute_ratios purity + determinism (004)"
```

---

### Task 8: Lock NO change to state / gate / classifier / citation / byte-stability (reason-only)

**Files:**
- Test: `tests/fundamentals/test_snapshot.py` (AC11 byte-stability) — plus a targeted run of the existing opportunity-state, Policy B, SAME-3/H3, and citation suites to prove they stay green.

This task proves AC8 (no `valuation_state`/`thesis_state`/`opportunity_state`/Policy B/partition change), AC9 (no `[ref:...]`, no `ThesisEvidence`), AC10 (filing-evidence-semantics + `基金概况` greps green), and AC11 (byte-stability).

- [ ] **Step 1: Write the byte-stability lock (AC11) for an empty-fragment row**

Append to `tests/fundamentals/test_snapshot.py`:

```python
def test_one_line_view_two_run_byte_stable_for_ratio_bearing_row() -> None:
    # AC11: same digest → byte-identical one_line_view across two calls.
    from irc.fundamentals import snapshot as _snap
    from irc.fundamentals.types import FundHolding, FilingDigest, ThesisEvidence
    holding = FundHolding("600519.SH", "贵州茅台", 10.0, "SH", "600519")
    ev = ThesisEvidence(
        type="filing", source="600519.SH", url="", date="2026-04-30",
        summary="600519.SH 2026Q1 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id="f", parent_fund_id="f", constituent_key="600519.SH",
    )
    digest = FilingDigest(
        symbol="600519.SH", fiscal_period="2026Q1", filed_at_iso="2026-04-30",
        revenue_yoy=0.06, net_income_yoy=0.04, gross_margin=0.69, roe=0.18,
    )
    a = _snap._one_line_view(holding, (ev,), digest)
    b = _snap._one_line_view(holding, (ev,), digest)
    assert a == b
    # AC9: the fragment carries no [ref:...] marker.
    import re
    assert re.search(r"\[ref:[0-9a-f]{16}\]", a) is None
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -q -k two_run_byte_stable`
Expected: PASS.

- [ ] **Step 3: Prove the state/gate/citation suites stay green (AC8/AC9/AC10)**

Run the existing classifiers/Policy B/partition/citation suites unchanged:

```bash
uv run pytest tests/opportunity/test_policy_b.py tests/opportunity/test_states.py tests/opportunity/test_thesis_evidence.py tests/opportunity/test_citation_map.py tests/commands/test_opportunity_cmd_citation_gate.py -q
```

Expected: ALL PASS — `compute_ratios` / the fragment touch none of these. If any fails, the change leaked into a state/gate/citation path — STOP, the change is no longer reason-only. (Per spec AC8/D5: no edit to `opportunity/states.py`, `valuation_fundamental.py`, `policy_b.py`, `derive_thesis_from_evidence`, `compose_opportunity_state`.)

- [ ] **Step 4: Prove the forbidden-grep acceptance tests stay green (AC10)**

The project enforces `基金概况`-forbidden and `revenue_yoy=`-in-summary-forbidden greps via acceptance tests. Locate and run them:

```bash
uv run pytest -q -k "forbidden or 基金概况 or acceptance" tests/fundamentals tests/opportunity
grep -rn "基金概况" src/irc/fundamentals/ratios.py src/irc/fundamentals/akshare_filing.py || echo "OK: no 基金概况 introduced"
grep -rn "revenue_yoy=" src/irc/fundamentals/ratios.py || echo "OK: no raw-scalar-in-summary"
```

Expected: PASS / both `OK:` lines print (the ratios fragment is NOT inserted into any `ThesisEvidence.summary`; the locked `财报已披露（口径未核实）` phrase in `_evidence_for_constituent` is untouched).

- [ ] **Step 5: Commit**

```bash
git add tests/fundamentals/test_snapshot.py
git commit -m "test(fundamentals): lock reason-only posture (no state/gate/citation change) (004)"
```

---

### Task 9: Documentation assertion + full-suite + lint gate

**Files:**
- Touch: none (CONTEXT.md entries already exist; this task ASSERTS them and runs the full gate)

Per spec AC12 (corrected): NO `docs/adr/0010-*.md` is created. CONTEXT.md already carries the `KeyRatios` / `compute_ratios` / `FilingDigest.roe` entries (committed 4b9f050). This task asserts they exist and runs the full verification gate.

- [ ] **Step 1: Assert CONTEXT.md entries exist (no ADR)**

```bash
grep -q "KeyRatios" CONTEXT.md && echo "OK: KeyRatios entry"
grep -q "compute_ratios" CONTEXT.md && echo "OK: compute_ratios entry"
grep -q "FilingDigest.roe" CONTEXT.md && echo "OK: FilingDigest.roe entry"
test ! -e docs/adr/0010-key-ratios-degrade-to-none.md && echo "OK: no ADR 0010 (reuses ADR 0009)"
```

Expected: four `OK:` lines. If a CONTEXT.md entry is missing, add a one-paragraph entry mirroring the `consensus_upside_pct` entry style (lines 131–137) and cross-referencing `docs/adr/0009-consensus-upside-degrade-to-none.md`; do NOT create an ADR.

- [ ] **Step 2: Run the full fundamentals + opportunity test suite**

Run: `uv run pytest tests/fundamentals tests/opportunity tests/commands -q`
Expected: PASS (no failures, no errors). This is the regression gate for AC8/AC9/AC10/AC11.

- [ ] **Step 3: Run the entire suite (no network)**

Run: `uv run pytest -q`
Expected: PASS. (Live tests are double-gated and stay skipped without `IRC_*=1`.)

- [ ] **Step 4: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (line-length 100, target py312). Fix any lint error in the new/modified files before committing.

- [ ] **Step 5: Final size-budget check**

```bash
wc -l src/irc/fundamentals/ratios.py src/irc/fundamentals/akshare_filing.py
```

Expected: `ratios.py` ≈ 75 lines, `akshare_filing.py` ≈ 168 lines — both under 200. `types.py` is ~339 after the field + comment (pre-existing 333, already over budget; not a 004 regression — `KeyRatios`/`compute_ratios` were deliberately placed in `ratios.py`, NOT `types.py`, precisely to avoid bloating it; the lone `roe` field belongs on `FilingDigest` and cannot move).

- [ ] **Step 6: Commit (only if Step 1 added a CONTEXT.md entry; otherwise nothing to commit here)**

```bash
git add CONTEXT.md 2>/dev/null && git commit -m "docs(004): assert KeyRatios/compute_ratios/FilingDigest.roe CONTEXT.md entries" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage (AC1–AC13):**
- AC1 (`KeyRatios` frozen, 4 fields, default None) → Task 3.
- AC2 (pure/deterministic, no I/O imports) → Task 3 + Task 7.
- AC3 (gross_margin pass-through) → Task 3.
- AC4 (`roe` from `盈利能力` section, never fails digest) → Task 1 + Task 2.
- AC5 (`debt_equity`/`fcf_yield` → None today) → Task 3.
- AC6 (zero/NaN-denominator safety) → Task 3 (`_finite` NaN screen; no division today, screening bites future fields).
- AC7 (reason-only compact fragment, non-None only, appended to `_one_line_view`) → Task 4 + Task 6.
- AC8 (no state/gate/classifier change) → Task 8 Step 3.
- AC9 (no citation/no `ThesisEvidence`) → Task 4 + Task 8.
- AC10 (filing-evidence-semantics, `基金概况` grep green) → Task 8 Step 4.
- AC11 (byte-stability of `one_line_view`) → Task 6 + Task 8 Step 1.
- AC12 (CONTEXT.md entries, NO ADR) → Task 9 Step 1.
- AC13 (size + TDD budget, test mirrors source) → enforced every task; size checks Task 2/4/9.

**Grill catches honored:**
- CATCH 1 — separate `_profitability_metric` for `盈利能力`/`净资产收益率`, `_common_metric` untouched, no new fetch → Task 2.
- CATCH 2 — digest threaded out of `_evidence_for_constituent` (3-tuple) to the call site; `[:60]` cap unchanged; byte-stability locked for empty-fragment rows → Task 5 + Task 6.
- CATCH 3 — `roe`+`gross_margin` period-aligned (same `latest` col, read in Task 2); None ratios omitted from fragment (Task 4) → never "None".

**Placeholder scan:** none — every code/test step shows full content. **Type consistency:** `KeyRatios(roe, debt_equity, gross_margin, fcf_yield)`, `compute_ratios(financials)`, `ratios_reason_fragment(ratios)`, `_evidence_for_constituent → 3-tuple`, `_one_line_view(holding, evidence, cn_digest=None)` are used identically across tasks.

**Judgment calls (spec gaps):**
1. Exact fragment string `（ROE 18%·毛利69%，口径未核实）` — the spec (AC7, Q2 resolved) gives the form as illustrative (`（ROE 18%·毛利69%，口径未核实）`); I locked it verbatim as the canonical output and chose `·` separator + `毛利{n}%` label to match the spec's compact example and stay within `[:60]`.
2. `roe` placed as the LAST `FilingDigest` field (after `source_url`) rather than next to `gross_margin` — required to preserve the one fully-positional construction (`test_snapshot_acceptance.py:69`); spec D1/AC4 only require "one new field," silent on position.
3. `_evidence_for_constituent` made a 3-tuple (vs a NamedTuple/dataclass) — minimal-churn realisation of the spec's "thread the digest out" (Q2 resolved); only one test fake needed updating.
