# Item 002 — Fundamental `valuation_state` + `core_dca` cheap-AND-intact gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the valuation axis consume `consensus_upside_pct` as an *augmenting* fundamental anchor (reason annotation + one-notch cheap-direction adjustment under corroboration), and tighten the `core_dca` gate so a row is refused core dollar-cost-averaging when a `"rich"` fundamental signal contradicts a cheap percentile — all dormant-by-default (byte-identical to today when the input is `None`, ADR 0009).

**Architecture:** A new small pure module `src/irc/opportunity/valuation_fundamental.py` holds the two named threshold constants, the pure `valuation_fundamental_signal(inp)` helper, and a pure reason-annotation helper. `states.py` imports them: `classify_valuation` appends the equity caveat and (only on `cheap`/`reasonable_low` percentile + `"cheap"` signal) moves one notch toward cheaper; `compose_opportunity_state` gains an optional `valuation_fundamental` parameter that, when `"rich"` AND `cheap_or_low`, skips the `core_dca` branch; `build_opportunity_row` computes the signal once and threads it in. No new `ThesisEvidence`, no gap codes, no Policy B / `thesis_state` touch.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest (offline, no mocks — pure functions), ruff.

---

## Source-of-truth references (read before starting)

- Spec: `docs/2026-05-31-funding-analysis/items/002-spec.md` (REFINED — honour the `## Resolved decisions` corrections; the `fundamental_blocks_core_dca` predicate and the belt-and-suspenders notch-refusal are STRUCK OUT — do NOT reintroduce them).
- Resolved decisions: `docs/2026-05-31-funding-analysis/items/002-grill.md` (Q-T2 threading mechanism is LOCKED to the explicit `compose_opportunity_state(valuation_fundamental=...)` parameter; Q-T4 the 001 lock breaks via REASON ANNOTATION only for its `very_expensive` row).
- Binding decision: `docs/adr/0009-consensus-upside-degrade-to-none.md` (`consensus_upside_pct` is `None` in production; the metric activates automatically when data lands; degrade-to-None is the contract).
- Domain glossary (already updated by the grill — do NOT re-edit): CONTEXT.md terms `consensus_upside_pct` (:131), `Valuation-input inertness` (:133), `valuation_fundamental_signal` (:134), `Fundamental-aware core_dca gate` (:135).

## Verified anchors (pinned by reading the real code)

- `src/irc/opportunity/states.py:129-133` — `_percentile(inp)` (self → vs-benchmark fallback).
- `src/irc/opportunity/states.py:136-140` — `_BOND_ASSET_CLASSES`, `_EQUITY_ASSET_CLASSES`, `_EXPENSIVE_VALUATION_STATES` frozensets.
- `src/irc/opportunity/states.py:143-154` — `expected_real_return_positive` (the exact annotate-never-change precedent for the new helper signature shape).
- `src/irc/opportunity/states.py:188-233` — `classify_valuation`; equity earnings-yield block at :218-232; `return state, reason` at :233.
- `src/irc/opportunity/states.py:388-420` — `compose_opportunity_state`; `cheap_or_low` computed at :403; `core_dca` branch at :410-411; `expensive or hot_heat → pause_wait` at :413-414; `small_watch` fall-through at :416-420.
- `src/irc/opportunity/states.py:423-464` — `derive_contributing_dimensions` (UNCHANGED by this item; the block only suppresses entry into the `core_dca` branch).
- `src/irc/opportunity/states.py:535-537` — the `compose_opportunity_state(valuation, heat, thesis, product, inp.venue_compatible)` call site inside `build_opportunity_row`.
- `src/irc/opportunity/types.py:120` — `OpportunityInput.consensus_upside_pct: float | None = None` (ratio units, 0.12 = +12%).
- `tests/opportunity/test_earnings_yield_anchor.py:18-25` — `_equity(**kwargs)` helper shape to mirror.
- `tests/opportunity/test_states.py:8-11` — `_make(**kwargs)` helper (`cn_etf`/`cn_on_exchange`).
- `tests/opportunity/test_states.py:200-216` — existing `core_dca` composer tests (must stay green — default `None` param).
- `tests/opportunity/test_states.py:384-394` — `_make_full_input(**overrides)` (`valuation_percentile_self=0.25`, semiconductor, csi300).
- `tests/opportunity/test_inputs_loader.py:169-184` — `_seed_csi300_instrument_with_prices` (flat 300×100.0 series → percentile 1.0).
- `tests/opportunity/test_inputs_loader.py:307-334` — the item-001 AC4 inertness lock `test_population_is_inert_classify_valuation_byte_identical` (must be UPDATED, not deleted).

## Judgment calls (made by the planner — cite the spec section)

1. **New module vs in-place helpers (spec AC9 / Constraints "Size budget").** `states.py` is **already 564 lines** — far over the 200-line ideal before this item. The spec's sanctioned fallback ("If `states.py` would exceed budget, `valuation_fundamental_signal` + the reason-annotation helper may move to a small new `src/irc/opportunity/valuation_fundamental.py`") therefore applies. **Decision:** put the two constants, `valuation_fundamental_signal`, and `_fundamental_reason_phrase` in the new module; `states.py` imports them. This keeps new pure logic in a focused <200-line file and minimises growth of the already-oversized `states.py`.

2. **Notch table (spec AC3).** AC3 says "at most one notch toward cheaper … only when signal == `"cheap"` AND the percentile path already says `cheap`/`reasonable_low`". `cheap` is already the cheapest band, so the notch maps `reasonable_low → cheap` and `cheap → cheap` (no-op, stays cheap). No other percentile state is touched. The notch reuses the SAME reason string semantics as the percentile band (it does not invent a new reason; the fundamental caveat from AC2 is appended regardless).

3. **Where the AC2 caveat is appended relative to the earnings-yield caveat (spec AC2).** The earnings-yield caveat fires only for `expensive`/`very_expensive` equities; the new fundamental caveat fires for ANY equity with a non-`None` signal. They are independent and may both appear on a `very_expensive` equity. **Decision:** append the fundamental caveat AFTER the existing earnings-yield block, so a `very_expensive` equity reads "…percentile… [earnings-yield caveat] [fundamental caveat]". Order is deterministic and tested.

4. **pe/pb in the reason phrase (spec AC2 / Open Q3).** pe/pb are reason-only and may be `None`. **Decision:** `_fundamental_reason_phrase` always states the consensus-upside read (the state-affecting scalar) and appends a "指数 PE/PB" fragment ONLY when `pe_ttm`/`pb` are present, so a `None`-pe/pb equity still gets the upside caveat. pe/pb never enter the signal/notch.

---

## Task 1: New module — threshold constants + `valuation_fundamental_signal`

**Files:**
- Create: `src/irc/opportunity/valuation_fundamental.py`
- Test: `tests/opportunity/test_valuation_fundamental_anchor.py`

- [ ] **Step 1: Write the failing test (signal branches + None)**

Create `tests/opportunity/test_valuation_fundamental_anchor.py`:

```python
"""Item 002 — pure fundamental valuation anchor over `consensus_upside_pct`.

Spec: docs/2026-05-31-funding-analysis/items/002-spec.md (AC1).
ADR 0009: the input is `None` in production today → signal `None` (no opinion).
"""
from __future__ import annotations

from irc.opportunity.types import OpportunityInput
from irc.opportunity.valuation_fundamental import (
    CHEAP_UPSIDE_THRESHOLD,
    RICH_UPSIDE_THRESHOLD,
    valuation_fundamental_signal,
)


def _equity(**kwargs) -> OpportunityInput:
    base = dict(instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange")
    base.update(kwargs)
    return OpportunityInput(**base)


def test_thresholds_are_ratio_constants() -> None:
    assert CHEAP_UPSIDE_THRESHOLD == 0.20
    assert RICH_UPSIDE_THRESHOLD == -0.10


def test_signal_cheap_at_and_above_threshold() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.20)) == "cheap"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.25)) == "cheap"


def test_signal_rich_at_and_below_threshold() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.10)) == "rich"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.30)) == "rich"


def test_signal_neutral_between_thresholds() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.05)) == "neutral"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.05)) == "neutral"


def test_signal_none_when_input_none() -> None:
    """Production-today case (ADR 0009): no target price → no opinion."""
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=None)) is None
    assert valuation_fundamental_signal(_equity()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.opportunity.valuation_fundamental'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/opportunity/valuation_fundamental.py`:

```python
"""Pure fundamental valuation anchor over `consensus_upside_pct` (item 002).

`consensus_upside_pct` is the one honestly-obtainable, already-relative
fundamental valuation scalar (price vs analyst target, ratio units). It needs
no peer/history normalisation — unlike absolute pe/pb, which therefore stay
reason-only (spec Open Q3). The anchor AUGMENTS the percentile band, mirroring
the `earnings_yield`/`real_yield_10y` anchor; it never replaces it. `None` in
production today (ADR 0009) → no opinion.

Thresholds are module-level named constants so future tuning is a one-line
change (spec AC1 / Open Q2). +20% is a conventional material-upside-vs-consensus
bar; -10% is asymmetric/tighter so the DCA gate errs slow to call cheap.
"""
from __future__ import annotations

from typing import Literal

from irc.opportunity.types import OpportunityInput

CHEAP_UPSIDE_THRESHOLD: float = 0.20
RICH_UPSIDE_THRESHOLD: float = -0.10

ValuationFundamental = Literal["cheap", "rich", "neutral"]


def valuation_fundamental_signal(
    inp: OpportunityInput,
) -> ValuationFundamental | None:
    """Map `consensus_upside_pct` (ratio) to a fundamental valuation signal.

    cheap   — upside >= CHEAP_UPSIDE_THRESHOLD
    rich    — upside <= RICH_UPSIDE_THRESHOLD
    neutral — present but between the thresholds
    None    — `consensus_upside_pct` is None (production-today; no opinion)
    """
    upside = inp.consensus_upside_pct
    if upside is None:
        return None
    if upside >= CHEAP_UPSIDE_THRESHOLD:
        return "cheap"
    if upside <= RICH_UPSIDE_THRESHOLD:
        return "rich"
    return "neutral"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/valuation_fundamental.py tests/opportunity/test_valuation_fundamental_anchor.py
git commit -m "feat(opportunity): pure valuation_fundamental_signal anchor (002)"
```

---

## Task 2: Reason-annotation helper (`_fundamental_reason_phrase`)

**Files:**
- Modify: `src/irc/opportunity/valuation_fundamental.py`
- Test: `tests/opportunity/test_valuation_fundamental_anchor.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/opportunity/test_valuation_fundamental_anchor.py`:

```python
from irc.opportunity.valuation_fundamental import _fundamental_reason_phrase


def test_reason_phrase_cheap_mentions_upside() -> None:
    phrase = _fundamental_reason_phrase("cheap", _equity(consensus_upside_pct=0.25))
    assert "上行空间" in phrase
    assert "便宜" in phrase
    assert "25%" in phrase  # ratio rendered as percent for humans


def test_reason_phrase_rich_mentions_downside() -> None:
    phrase = _fundamental_reason_phrase("rich", _equity(consensus_upside_pct=-0.30))
    assert "目标价" in phrase or "下行" in phrase
    assert "-30%" in phrase


def test_reason_phrase_appends_pe_pb_when_present() -> None:
    phrase = _fundamental_reason_phrase(
        "neutral", _equity(consensus_upside_pct=0.05, pe_ttm=12.1, pb=1.31)
    )
    assert "PE 12.1" in phrase
    assert "PB 1.31" in phrase


def test_reason_phrase_omits_pe_pb_when_absent() -> None:
    phrase = _fundamental_reason_phrase("neutral", _equity(consensus_upside_pct=0.05))
    assert "PE" not in phrase
    assert "PB" not in phrase
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: FAIL — `ImportError: cannot import name '_fundamental_reason_phrase'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/irc/opportunity/valuation_fundamental.py`:

```python
def _pe_pb_fragment(inp: OpportunityInput) -> str:
    """Optional 'PE x.x / PB x.x' fragment (reason-only; never state, Open Q3)."""
    parts: list[str] = []
    if inp.pe_ttm is not None:
        parts.append(f"PE {inp.pe_ttm}")
    if inp.pb is not None:
        parts.append(f"PB {inp.pb}")
    return f"（指数 {' / '.join(parts)}）" if parts else ""


def _fundamental_reason_phrase(
    signal: ValuationFundamental,
    inp: OpportunityInput,
) -> str:
    """Chinese caveat describing the consensus-upside read (+ optional pe/pb)."""
    upside_pct = f"{inp.consensus_upside_pct:.0%}"
    if signal == "cheap":
        head = f"券商一致目标价隐含上行空间 {upside_pct}，基本面偏便宜。"
    elif signal == "rich":
        head = f"券商一致目标价隐含 {upside_pct} 下行，基本面不便宜。"
    else:
        head = f"券商一致目标价隐含上行空间 {upside_pct}，基本面中性。"
    return head + _pe_pb_fragment(inp)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: PASS — 9 passed.

- [ ] **Step 5: Verify ruff is clean**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/valuation_fundamental.py tests/opportunity/test_valuation_fundamental_anchor.py
git commit -m "feat(opportunity): fundamental reason-annotation helper (002)"
```

---

## Task 3: `classify_valuation` — equity caveat annotation (AC2)

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_valuation_fundamental_anchor.py`

- [ ] **Step 1: Write the failing test (annotation present for equity, absent for bond)**

Append to `tests/opportunity/test_valuation_fundamental_anchor.py`:

```python
from irc.opportunity.states import classify_valuation


def test_classify_valuation_appends_fundamental_phrase_for_equity() -> None:
    """AC2: equity with consensus_upside_pct gets the 便宜/上行空间 caveat."""
    inp = _equity(valuation_percentile_self=0.55, consensus_upside_pct=0.25)
    state, reason = classify_valuation(inp)
    assert state == "fair"  # AC3: no notch from a `fair` percentile
    assert "上行空间" in reason


def test_classify_valuation_no_fundamental_phrase_for_bond_class() -> None:
    """AC5: bonds use the yield-percentile anchor — fundamental caveat never fires.

    Mirrors test_classify_valuation_does_not_append_phrase_for_bond_class.
    """
    inp = OpportunityInput(
        instrument_id="000111", asset_class="cn_bond_fund", market="CN",
        cn_bond_yield_percentile=0.05, consensus_upside_pct=0.25,
    )
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    assert "上行空间" not in reason


def test_classify_valuation_no_fundamental_phrase_when_signal_none() -> None:
    """AC6: consensus_upside_pct None → no caveat, byte-identical to today."""
    inp = _equity(valuation_percentile_self=0.55)
    state, reason = classify_valuation(inp)
    assert state == "fair"
    assert "上行空间" not in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -k fundamental_phrase -q`
Expected: FAIL — `test_classify_valuation_appends_fundamental_phrase_for_equity` fails (`"上行空间" not in reason`); the bond and None tests pass (caveat not yet wired so they trivially hold — they lock the negative path).

- [ ] **Step 3: Write minimal implementation**

In `src/irc/opportunity/states.py`, add the import to the existing block (after line 23, the `from irc.opportunity.types import (...)` import group). Insert this new import line:

```python
from irc.opportunity.valuation_fundamental import (
    _fundamental_reason_phrase,
    valuation_fundamental_signal,
)
```

Then in `classify_valuation`, insert the fundamental annotation block AFTER the existing earnings-yield block (after the `elif signal is False:` clause that ends at line 232) and BEFORE `return state, reason` (line 233). The function currently ends:

```python
        elif signal is False:
            reason = (
                f"{reason} 且 earnings_yield - real_yield 非正，"
                f"长期实际回报预期偏弱。"
            )
    return state, reason
```

Change it to:

```python
        elif signal is False:
            reason = (
                f"{reason} 且 earnings_yield - real_yield 非正，"
                f"长期实际回报预期偏弱。"
            )
    if inp.asset_class in _EQUITY_ASSET_CLASSES:
        fundamental = valuation_fundamental_signal(inp)
        if fundamental is not None:
            reason = f"{reason} {_fundamental_reason_phrase(fundamental, inp)}"
    return state, reason
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: PASS — 12 passed.

- [ ] **Step 5: Run the earnings-yield precedent suite (no regression)**

Run: `uv run pytest tests/opportunity/test_earnings_yield_anchor.py -q`
Expected: PASS — 8 passed (those tests set no `consensus_upside_pct`, so the new block is dormant for them).

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_valuation_fundamental_anchor.py
git commit -m "feat(opportunity): classify_valuation appends fundamental caveat for equities (002)"
```

---

## Task 4: `classify_valuation` — one-notch cheap-direction adjustment (AC3)

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_valuation_fundamental_anchor.py`

- [ ] **Step 1: Write the failing test (the AC3 notch table)**

Append to `tests/opportunity/test_valuation_fundamental_anchor.py`:

```python
def test_notch_reasonable_low_plus_cheap_signal_becomes_cheap() -> None:
    """AC3(a): percentile reasonable_low + 'cheap' signal → cheap (corroboration)."""
    inp = _equity(valuation_percentile_self=0.30, consensus_upside_pct=0.25)
    state, _ = classify_valuation(inp)
    assert state == "cheap"


def test_notch_cheap_plus_cheap_signal_stays_cheap() -> None:
    """AC3: already cheap stays cheap (notch is a no-op, never moves expensive)."""
    inp = _equity(valuation_percentile_self=0.10, consensus_upside_pct=0.25)
    state, _ = classify_valuation(inp)
    assert state == "cheap"


def test_notch_does_not_fire_for_fair_percentile() -> None:
    """AC3(b): percentile fair + 'cheap' signal → fair (no jump)."""
    inp = _equity(valuation_percentile_self=0.55, consensus_upside_pct=0.25)
    state, _ = classify_valuation(inp)
    assert state == "fair"


def test_notch_never_moves_toward_more_expensive() -> None:
    """AC3(c): percentile expensive + 'rich' signal → expensive (reason only)."""
    inp = _equity(valuation_percentile_self=0.80, consensus_upside_pct=-0.30)
    state, reason = classify_valuation(inp)
    assert state == "expensive"
    assert "下行" in reason  # contradiction annotated


def test_notch_does_not_fire_for_neutral_signal() -> None:
    """AC3: corroboration requires signal=='cheap'; neutral leaves state alone."""
    inp = _equity(valuation_percentile_self=0.30, consensus_upside_pct=0.05)
    state, _ = classify_valuation(inp)
    assert state == "reasonable_low"


def test_notch_does_not_fire_when_signal_none() -> None:
    """AC6: None signal → state byte-identical to today (dormant)."""
    inp = _equity(valuation_percentile_self=0.30)
    state, _ = classify_valuation(inp)
    assert state == "reasonable_low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -k notch -q`
Expected: FAIL — `test_notch_reasonable_low_plus_cheap_signal_becomes_cheap` fails (`reasonable_low != cheap`). The other notch tests pass already (they lock the no-move paths).

- [ ] **Step 3: Write minimal implementation**

In `src/irc/opportunity/states.py`, add a module-level constant next to the existing frozensets (after line 140, `_EXPENSIVE_VALUATION_STATES = ...`):

```python
_NOTCHABLE_VALUATION_STATES: frozenset[str] = frozenset({"cheap", "reasonable_low"})
```

Then extend the equity block added in Task 3. Replace:

```python
    if inp.asset_class in _EQUITY_ASSET_CLASSES:
        fundamental = valuation_fundamental_signal(inp)
        if fundamental is not None:
            reason = f"{reason} {_fundamental_reason_phrase(fundamental, inp)}"
    return state, reason
```

with:

```python
    if inp.asset_class in _EQUITY_ASSET_CLASSES:
        fundamental = valuation_fundamental_signal(inp)
        if fundamental is not None:
            reason = f"{reason} {_fundamental_reason_phrase(fundamental, inp)}"
            # AC3: corroboration-only one-notch move toward cheaper. Never
            # toward more-expensive; never promotes fair/expensive/very_expensive.
            if fundamental == "cheap" and state in _NOTCHABLE_VALUATION_STATES:
                state = "cheap"
    return state, reason
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: PASS — 18 passed.

- [ ] **Step 5: Verify the percentile-band tests in test_states.py still pass**

Run: `uv run pytest tests/opportunity/test_states.py -k valuation -q`
Expected: PASS (those tests set no `consensus_upside_pct`, so notch + caveat are dormant).

- [ ] **Step 6: Verify ruff is clean**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_valuation_fundamental_anchor.py
git commit -m "feat(opportunity): classify_valuation one-notch cheap-direction adjustment (002)"
```

---

## Task 5: `compose_opportunity_state` — fundamental `core_dca` block (AC4)

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

- [ ] **Step 1: Write the failing test (explicit composer parameter)**

Append to `tests/opportunity/test_states.py` (after `test_core_dca_when_reasonable_low_normal_intact_strong`, near line 217):

```python
def test_core_dca_blocked_when_fundamental_rich():
    """AC4: cheap percentile + 'rich' fundamental → NOT core_dca (falls to small_watch).

    The percentile fact (`valuation == cheap`) stays true; only the opportunity
    state falls through. Threading is the explicit composer parameter (grill Q-T2).
    """
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", valuation_fundamental="rich",
    )
    assert state == "small_watch"


def test_core_dca_allowed_when_fundamental_neutral():
    """AC4: only 'rich' blocks; neutral/cheap/None keep the core_dca path."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", valuation_fundamental="neutral",
    )
    assert state == "core_dca"


def test_core_dca_default_param_keeps_existing_callers_green():
    """AC4: default None keeps every existing caller byte-identical (dormancy)."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable",
    )
    assert state == "core_dca"


def test_fundamental_rich_does_not_change_pause_wait():
    """AC4/AC5: the block only suppresses core_dca; an expensive row is
    pause_wait regardless of the fundamental signal."""
    state, _ = compose_opportunity_state(
        valuation="expensive", heat="normal", thesis="intact",
        product_quality="acceptable", valuation_fundamental="rich",
    )
    assert state == "pause_wait"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_states.py -k "fundamental_rich or fundamental_neutral or default_param_keeps" -q`
Expected: FAIL — `TypeError: compose_opportunity_state() got an unexpected keyword argument 'valuation_fundamental'`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/opportunity/states.py`, change the `compose_opportunity_state` signature (line 388-394). Replace:

```python
def compose_opportunity_state(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
    venue_compatible: bool = True,
) -> tuple[OpportunityState, str]:
    """Compose final opportunity state from four sub-states."""
```

with:

```python
def compose_opportunity_state(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
    venue_compatible: bool = True,
    valuation_fundamental: ValuationFundamental | None = None,
) -> tuple[OpportunityState, str]:
    """Compose final opportunity state from four sub-states.

    `valuation_fundamental` (item 002, grill Q-T2): when `"rich"` AND the
    percentile path is cheap/reasonable_low, the cheap-AND-intact `core_dca`
    gate is refused (the row falls through to `small_watch`). Default `None`
    keeps every existing caller byte-identical. `valuation_state` itself stays
    `cheap` — only the opportunity state falls through (AC3-preserving).
    """
```

Add the `ValuationFundamental` import. Update the existing import block added in Task 3 so it reads:

```python
from irc.opportunity.valuation_fundamental import (
    ValuationFundamental,
    _fundamental_reason_phrase,
    valuation_fundamental_signal,
)
```

Then guard the `core_dca` branch. Replace lines 410-411:

```python
    if cheap_or_low and quiet_heat and intact_thesis and decent_product:
        return "core_dca", "估值便宜、热度可控、长期逻辑完好、产品质量合格，适合定投。"
```

with:

```python
    fundamental_contradiction = valuation_fundamental == "rich" and cheap_or_low
    if (
        cheap_or_low and quiet_heat and intact_thesis and decent_product
        and not fundamental_contradiction
    ):
        return "core_dca", "估值便宜、热度可控、长期逻辑完好、产品质量合格，适合定投。"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_states.py -k "fundamental_rich or fundamental_neutral or default_param_keeps or pause_wait" -q`
Expected: PASS (the four new tests + existing pause_wait test).

- [ ] **Step 5: Run the full composer suite (no regression)**

Run: `uv run pytest tests/opportunity/test_states.py -q`
Expected: PASS — all existing composer/contributing-dimensions tests stay green (default `None` param is inert; `derive_contributing_dimensions` is untouched because a blocked row never enters the `core_dca` branch and the resulting `small_watch` already has correct dimension logic).

- [ ] **Step 6: Verify ruff is clean**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): fundamental-aware core_dca gate via explicit composer param (002)"
```

---

## Task 6: `build_opportunity_row` — thread the signal once (AC4 end-to-end)

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

- [ ] **Step 1: Write the failing test (end-to-end through build_opportunity_row)**

Append to `tests/opportunity/test_states.py` (after `test_build_opportunity_row_populates_contributing_dimensions_for_core_dca`, near line 627):

```python
def test_build_opportunity_row_core_dca_when_consensus_upside_none():
    """AC6: all-None fundamentals → cheap percentile core_dca, unchanged."""
    inp = _make_full_input(valuation_percentile_self=0.15)  # cheap percentile
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.valuation_state == "cheap"
    assert row.opportunity_state == "core_dca"


def test_build_opportunity_row_blocks_core_dca_when_fundamental_rich():
    """AC4 end-to-end: cheap percentile + rich consensus upside →
    valuation_state STAYS cheap, opportunity_state falls to small_watch,
    reason annotates the contradiction. No new ThesisEvidence (AC8)."""
    inp = _make_full_input(
        valuation_percentile_self=0.15,  # cheap percentile (fact stays true)
        consensus_upside_pct=-0.30,      # 'rich' → contradiction
    )
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.valuation_state == "cheap"          # AC3-preserving
    assert row.opportunity_state == "small_watch"  # AC4 block
    assert "下行" in row.opportunity_reason         # contradiction annotated
    assert row.thesis_evidence == ()               # AC8: no citation surface
    assert row.evidence_gaps  # only the pre-existing snapshot/news gaps; no new gap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_states.py -k "core_dca_when_consensus_upside_none or blocks_core_dca_when_fundamental_rich" -q`
Expected: FAIL — `test_build_opportunity_row_blocks_core_dca_when_fundamental_rich` fails (`opportunity_state == "core_dca"`, block not threaded). The `_none` test passes (already correct).

- [ ] **Step 3: Write minimal implementation**

In `src/irc/opportunity/states.py`, update the `compose_opportunity_state` call inside `build_opportunity_row` (lines 535-537). Replace:

```python
    state, state_reason = compose_opportunity_state(
        valuation, heat, thesis, product, inp.venue_compatible,
    )
```

with:

```python
    state, state_reason = compose_opportunity_state(
        valuation, heat, thesis, product, inp.venue_compatible,
        valuation_fundamental=valuation_fundamental_signal(inp),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_states.py -k "core_dca_when_consensus_upside_none or blocks_core_dca_when_fundamental_rich" -q`
Expected: PASS — 2 passed.

- [ ] **Step 5: Run the full states + anchor suites (no regression)**

Run: `uv run pytest tests/opportunity/test_states.py tests/opportunity/test_valuation_fundamental_anchor.py -q`
Expected: PASS — all green.

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): thread valuation_fundamental_signal into build_opportunity_row (002)"
```

---

## Task 7: Bonds/gold/QDII byte-identical lock (AC5)

**Files:**
- Test: `tests/opportunity/test_valuation_fundamental_anchor.py`

- [ ] **Step 1: Write the failing test (no implementation change expected — this LOCKS existing behaviour)**

Append to `tests/opportunity/test_valuation_fundamental_anchor.py`:

```python
import dataclasses

from irc.opportunity.states import compose_opportunity_state


def test_bond_classify_byte_identical_with_consensus_upside_set() -> None:
    """AC5: bonds are yield-percentile-anchored; consensus_upside_pct must not
    change classify_valuation output (bond-valuation invariant)."""
    bare = OpportunityInput(
        instrument_id="014502", asset_class="cn_bond_fund", market="cn_off_exchange",
        cn_bond_yield_percentile=0.65,
    )
    populated = dataclasses.replace(bare, consensus_upside_pct=0.25, pe_ttm=8.0, pb=0.9)
    assert classify_valuation(populated) == classify_valuation(bare)


def test_gold_classify_byte_identical_with_consensus_upside_set() -> None:
    """AC5: gold has no equity fundamentals; the anchor must not fire."""
    bare = OpportunityInput(
        instrument_id="518880", asset_class="gold", market="cn_on_exchange",
        valuation_percentile_self=0.50,
    )
    populated = dataclasses.replace(bare, consensus_upside_pct=-0.30)
    assert classify_valuation(populated) == classify_valuation(bare)


def test_compose_state_block_inert_for_none_fundamental() -> None:
    """AC5/AC6: the composer block is keyed on valuation_fundamental only; a
    bond/gold row never supplies it → core_dca path unchanged."""
    with_none = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", valuation_fundamental=None,
    )
    legacy = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable",
    )
    assert with_none == legacy == ("core_dca", with_none[1])
```

- [ ] **Step 2: Run test to verify it passes immediately**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -k "bond_classify_byte_identical or gold_classify_byte_identical or block_inert" -q`
Expected: PASS — 3 passed. (No code change: `cn_bond_fund` dispatches to `classify_bond_valuation` before the equity block; `gold` is not in `_EQUITY_ASSET_CLASSES`; the composer block is inert when `valuation_fundamental is None`. This task is a regression lock, not a behaviour change — no RED step exists because the behaviour is already correct from Tasks 3-5.)

- [ ] **Step 3: Commit**

```bash
git add tests/opportunity/test_valuation_fundamental_anchor.py
git commit -m "test(opportunity): lock bond/gold/QDII inertness for fundamental anchor (002, AC5)"
```

---

## Task 8: Update the item-001 AC4 inertness lock (AC7)

**Files:**
- Modify: `tests/opportunity/test_inputs_loader.py:307-334`

- [ ] **Step 1: Read the current lock test to confirm the row's behaviour**

The row is `510300`/csi300 with a flat 300×100.0 price series (`_seed_csi300_instrument_with_prices`). `self_history_percentile` uses inclusive ranking (`count_le/len`) → `valuation_percentile_self == 1.0` → `classify_valuation` returns `very_expensive`. The single broker report has `target_price=120.0`, `latest_close=100.0` → `consensus_upside_pct = 120/100 − 1 = 0.20` → `valuation_fundamental_signal == "cheap"`. AC3's notch fires ONLY on `cheap`/`reasonable_low`, so for a `very_expensive` row the notch NEVER fires — the byte-difference is purely AC2's appended caveat (grill Q-T4).

- [ ] **Step 2: Write the updated test (RED — the old assertion is now false by design)**

Replace the existing `test_population_is_inert_classify_valuation_byte_identical` (lines 307-334) with:

```python
def test_population_consumes_consensus_upside_per_item_002(tmp_path, monkeypatch):
    """Item 002 (AC7) — EVOLVED from item 001's AC4 inertness lock.

    The 001 lock asserted classify_valuation(populated) == classify_valuation(bare).
    Item 002 INTENTIONALLY makes a populated `consensus_upside_pct` flow into the
    equity valuation reason, so that equality is now false BY DESIGN. This test is
    updated (not deleted) to assert the new specified behaviour and the all-None
    dormancy, per docs/2026-05-31-funding-analysis/items/002-spec.md (AC2/AC3/AC6/AC7)
    and ADR 0009 (degrade-to-None). Provenance preserved: stays in this file, keeps
    the population guard.

    Row anatomy (grill Q-T4): 510300/csi300 seeds a flat 300x100.0 price series, so
    `self_history_percentile` (inclusive count_le/len) gives percentile 1.0 →
    classify_valuation returns `very_expensive`. target_price=120 / close=100 →
    consensus_upside_pct=0.20 → signal `"cheap"`. AC3's one-notch adjustment fires
    only on a cheap/reasonable_low percentile, so for this very_expensive row the
    notch NEVER fires — the break is ANNOTATION-ONLY (AC2's appended caveat).
    """
    con = duckdb.connect(str(tmp_path / "consume.duckdb"))
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
    import dataclasses
    bare = dataclasses.replace(
        populated, pe_ttm=None, pb=None, dividend_yield=None,
        consensus_upside_pct=None,
    )
    assert populated.pe_ttm is not None  # guard: population actually happened
    assert populated.consensus_upside_pct == pytest.approx(0.20)

    pop_state, pop_reason = classify_valuation(populated)
    bare_state, bare_reason = classify_valuation(bare)

    # (i) Annotation-only break on THIS row: state unchanged at very_expensive
    # (percentile 1.0 → notch never fires), but the reason now carries the
    # equity fundamental caveat that the bare (all-None) row does not.
    assert pop_state == bare_state == "very_expensive"
    assert pop_reason != bare_reason
    assert "上行空间" in pop_reason
    assert "上行空间" not in bare_reason

    # (ii) All-None dormancy (AC6): the bare row is byte-identical to pre-002.
    assert classify_valuation(bare) == classify_valuation(
        dataclasses.replace(bare, consensus_upside_pct=None)
    )
    con.close()


def test_consensus_upside_notch_fires_on_genuinely_cheap_percentile(tmp_path, monkeypatch):
    """Item 002 (AC7) — SECOND row exercising the AC3 one-notch corroboration.

    Unlike the flat-series row above (percentile 1.0 → very_expensive), this seeds
    a deeply cheap percentile and a 'cheap' consensus-upside signal, so the AC3
    one-notch adjustment fires: reasonable_low → cheap / cheap → cheap. Cites
    docs/2026-05-31-funding-analysis/items/002-spec.md (AC3) and ADR 0009.
    """
    con = duckdb.connect(str(tmp_path / "notch.duckdb"))
    ensure_schema(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    # reasonable_low percentile: build a synthetic input directly (no DB price
    # path needed — the notch lives in classify_valuation, a pure function).
    base = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300", valuation_percentile_self=0.30,
    )
    without = classify_valuation(base)
    assert without[0] == "reasonable_low"  # baseline percentile band

    with_cheap_signal = classify_valuation(
        dataclasses_replace_upside(base, 0.25)  # 'cheap' signal
    )
    assert with_cheap_signal[0] == "cheap"  # AC3 corroboration notch fired

    # cheap percentile + cheap signal stays cheap (notch no-op)
    deeply_cheap = dataclasses_replace_upside(
        dataclasses_replace_self_pct(base, 0.10), 0.25
    )
    assert classify_valuation(deeply_cheap)[0] == "cheap"
    con.close()
```

Add these two tiny local helpers near the top of `tests/opportunity/test_inputs_loader.py` (after the imports, before `_make_db`). They keep the notch test readable without importing `dataclasses` twice:

```python
def dataclasses_replace_upside(inp: OpportunityInput, upside: float) -> OpportunityInput:
    import dataclasses
    return dataclasses.replace(inp, consensus_upside_pct=upside)


def dataclasses_replace_self_pct(inp: OpportunityInput, pct: float) -> OpportunityInput:
    import dataclasses
    return dataclasses.replace(inp, valuation_percentile_self=pct)
```

- [ ] **Step 3: Run the updated lock + notch test**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -k "consumes_consensus_upside or notch_fires_on_genuinely_cheap" -q`
Expected: PASS — 2 passed. (No source change in this task — the behaviour was implemented in Tasks 3-4; this task evolves the lock to assert it.)

- [ ] **Step 4: Run the full inputs_loader suite (no regression)**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -q`
Expected: PASS — all green (the old `test_population_is_inert_*` name is gone; the two new tests replace it; every other inputs_loader test is unchanged).

- [ ] **Step 5: Verify the old test name is fully removed (no orphaned reference)**

Run: `grep -rn "test_population_is_inert_classify_valuation_byte_identical" tests/ src/ docs/`
Expected: no matches (silent-deletion guard inverted — confirm it is gone from tests but the EVOLVED test carries its provenance comment).

- [ ] **Step 6: Verify ruff is clean**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add tests/opportunity/test_inputs_loader.py
git commit -m "test(opportunity): evolve item-001 inertness lock to consume consensus_upside (002, AC7)"
```

---

## Task 9: Invariant locks — no citation/partition/Policy-B/thesis_state change (AC8)

**Files:**
- Test: `tests/opportunity/test_valuation_fundamental_anchor.py`

- [ ] **Step 1: Write the AC8 structural lock test**

Append to `tests/opportunity/test_valuation_fundamental_anchor.py`:

```python
from irc.opportunity.states import build_opportunity_row


def test_fundamental_block_emits_no_thesis_evidence_or_gap(monkeypatch):
    """AC8: the valuation/core_dca path emits NO new ThesisEvidence and NO new
    gap code; H3 partition (evidence_gaps), SAME-3 (citation set), Policy B,
    and thesis_state derivation are structurally untouched.

    Compare a rich-blocked row against the same row with the fundamental input
    cleared: thesis_evidence, evidence_gaps, expected_omissions, advisory_gaps,
    contributing_dimensions, and thesis_state must be IDENTICAL (only
    opportunity_state / opportunity_reason may differ)."""
    import dataclasses

    base = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        theme="semiconductor", tracked_index="csi300",
        valuation_percentile_self=0.15,  # cheap percentile
        ret_3m=0.02, ret_6m=0.05, expense_ratio=0.0015, aum_cny=20e9,
    )
    rich = dataclasses.replace(base, consensus_upside_pct=-0.30)  # 'rich' block
    none_row = build_opportunity_row(base, theme_thesis={"semiconductor": "intact"})
    rich_row = build_opportunity_row(rich, theme_thesis={"semiconductor": "intact"})

    # The block changes opportunity_state + reason ONLY.
    assert none_row.opportunity_state == "core_dca"
    assert rich_row.opportunity_state == "small_watch"
    # Everything citation/gap/thesis-shaped is byte-identical.
    assert rich_row.thesis_evidence == none_row.thesis_evidence == ()
    assert rich_row.evidence_gaps == none_row.evidence_gaps
    assert rich_row.expected_omissions == none_row.expected_omissions
    assert rich_row.advisory_gaps == none_row.advisory_gaps
    assert rich_row.thesis_state == none_row.thesis_state  # owned by derive_thesis_from_evidence
    # valuation_state stays cheap on both (AC3-preserving).
    assert rich_row.valuation_state == none_row.valuation_state == "cheap"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py -k emits_no_thesis_evidence -q`
Expected: PASS — 1 passed. (Regression lock — no source change; the invariants already hold from Tasks 3-6.)

- [ ] **Step 3: Commit**

```bash
git add tests/opportunity/test_valuation_fundamental_anchor.py
git commit -m "test(opportunity): lock AC8 no-citation/partition/Policy-B change (002)"
```

---

## Task 10: Full-suite + lint verification + size-budget check (AC9)

**Files:** none (verification only)

- [ ] **Step 1: Run the entire opportunity test suite (AC9 no-network correctness)**

Run: `uv run pytest tests/opportunity -q`
Expected: PASS — full opportunity suite green (existing tests + the new anchor module tests + the evolved lock).

- [ ] **Step 2: Run the forbidden-indicator acceptance grep guard (must stay green)**

Run: `uv run pytest -k "基金概况 or forbidden" -q` (if no such test id matches, fall back to a direct grep)
Then: `grep -rn "基金概况" src/irc/opportunity/`
Expected: no `基金概况` reference introduced by item 002 (no fetch code touched).

- [ ] **Step 3: Lint clean (AC9)**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 4: Confirm the new module is under the 200-line budget (AC9)**

Run: `wc -l src/irc/opportunity/valuation_fundamental.py`
Expected: well under 200 (the module holds two constants + two small functions + one tiny helper).

- [ ] **Step 5: Confirm new functions are under the ~20-line ideal (AC9)**

Run: `grep -n "def " src/irc/opportunity/valuation_fundamental.py`
Inspect: `valuation_fundamental_signal` (~9 lines), `_fundamental_reason_phrase` (~11 lines), `_pe_pb_fragment` (~7 lines) — each under 20.

- [ ] **Step 6: Final commit (if any uncommitted formatting)**

```bash
git status --short
# If anything is uncommitted from verification (should be nothing):
git add -A && git commit -m "chore(opportunity): item 002 verification pass (002)" || true
```

---

## Self-review against the spec

| Spec AC | Task(s) | Notes |
|---|---|---|
| AC1 — pure `valuation_fundamental_signal` + named constants, 4 branches + None | Task 1 | Constants `CHEAP_UPSIDE_THRESHOLD=0.20`, `RICH_UPSIDE_THRESHOLD=-0.10`; 5 branch tests incl. all-None. |
| AC2 — equity reason annotation; bonds unaffected | Tasks 2, 3 | Caveat appended after earnings-yield block; bond/None negative-path tests. |
| AC3 — one-notch, cheap-direction, corroboration-only | Task 4 | `_NOTCHABLE_VALUATION_STATES`; (a)(b)(c)(d) table all covered. |
| AC4 — `core_dca` gated, fundamental-aware via explicit composer param | Tasks 5, 6 | `valuation_fundamental` param (NO `fundamental_blocks_core_dca` predicate — struck out); `valuation_state` stays cheap, only opportunity_state falls through; threaded once in `build_opportunity_row`. |
| AC5 — bonds/gold/QDII byte-identical | Task 7 | classify + compose locks. |
| AC6 — degrade-to-None dormancy | Tasks 4, 6, 8 | all-None → byte-identical; locked at classify + build levels. |
| AC7 — evolve (not delete) item-001 lock; annotation-only on the very_expensive row + add a cheap-percentile row | Task 8 | Renamed-evolved test asserts annotation-only break; second test exercises the notch; provenance + ADR 0009 comment preserved; old name fully removed. |
| AC8 — no citation/partition/Policy-B/thesis_state change | Task 9 | Structural lock: thesis_evidence/gaps/thesis_state identical across rich-vs-none. |
| AC9 — no-network correctness, ruff clean, size budget | Tasks 2, 4, 5, 6, 10 | New module under 200 lines; functions under 20; full suite + ruff. |

**Placeholder scan:** none — every code/test step is copy-pasteable; no TBD/TODO.

**Type consistency:** `valuation_fundamental_signal` / `ValuationFundamental` / `_fundamental_reason_phrase` / `_pe_pb_fragment` / `_NOTCHABLE_VALUATION_STATES` / `compose_opportunity_state(..., valuation_fundamental=...)` are used identically across Tasks 1-9. The composer param name `valuation_fundamental` matches CONTEXT.md `Fundamental-aware core_dca gate`.

**Non-goals honoured:** no fetchers/Tushare (no `populate_inputs`/AkShare/`settings.py` change beyond reading the already-wired field); no Policy B / `thesis_state` redefinition; no new `ThesisEvidence`/citation; no absolute pe/pb threshold (reason-only); no `fundamental_blocks_core_dca` predicate (struck out by grill Q-T2); no `classify_valuation` move toward more-expensive (AC3).

**CONTEXT.md / ADR:** already updated by the grill (CONTEXT.md terms at :131-135; ADR 0009 owns degrade-to-None — no ADR 0010 per grill Q-T3). This plan introduces NO further doc edits.
