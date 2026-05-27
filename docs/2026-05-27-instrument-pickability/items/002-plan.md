# Item 002 — Holdings overlap / concentration panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic "持仓集中度" sub-block to memo §6 风险提示 that lists every pair of active-fund picks whose weighted Top-10 holdings overlap ≥ 30%, so the operator can avoid unknowingly buying multiple funds that express the same underlying bet.

**Architecture:** A new pure module `src/irc/memo/concentration.py` defines (a) the `weighted_overlap_pct` metric, (b) the frozen `ConcentrationPair` dataclass with canonical `(min_iid, max_iid)` ordering, (c) `compute_concentration_pairs(active_picks)` enumerating overlap pairs ≥ threshold, and (d) the `IRC_CONCENTRATION_BEGIN/END` marker constants. A new helper `_compose_concentration_lines(pick_rows, op_rows_by_id)` in `src/irc/commands/memo_cmd.py` is the dependency-injection edge that builds the marker-wrapped tuple from picks + the in-scope opportunity rows. The synthesizer prompt gains a verbatim-lock instruction for the new marker. No changes to `OpportunityRow` shape, no new `advisory_gaps` codes, no on-disk state, no AkShare/LLM calls.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, uv. Pure functions only; I/O stays at the CLI/edge.

**Project constraints (from CLAUDE.md + CONTEXT.md + 002-spec.md):**
- TDD mandatory: red → green → refactor. Tests written **before** production code.
- Functional / immutable: tuples, `dataclass(frozen=True)`, factory functions for invariant enforcement. Never mutate `OpportunityRow` / `PickRow` / `ConstituentAnalysis` / `ActiveFundSnapshot`.
- Files <200 lines; functions <20 lines (ideal). `concentration.py` budget: <200 lines.
- **Determinism / two-run byte equality (AC11/AC13).** Two nondeterminism sources are pinned: (a) frozenset/set iteration via `sorted(...)` on all symbol and pair traversals; (b) float comparison via `round(overlap_pct, 1)` set ONCE at construction (never re-rounded) AND used as the primary sort key at render time. Coverage absorbed by existing `tests/integration/test_publishable_set_lockdown.py::test_two_run_byte_equality_memo_after_run_memo` — no new lockdown fixture.
- **H3 invariant.** `evidence_gaps == ()` predicate untouched. Concentration is memo-only; it does NOT touch `evidence_gaps`, `advisory_gaps`, `thesis_state`, or `OpportunityRow` shape.
- **SAME-3 invariant.** `thesis_evidence`, citation_ids, and the 3-way citation-set equality across picks-table / evidence-pool / discipline are unaffected — the concentration block emits no `[ref:...]` markers.
- **Renderer tier-1 import contract.** `concentration.py` imports from `irc.opportunity.types` (and `irc.fundamentals.types` for `ConstituentAnalysis`) **only**. No imports from `irc.memo.*` siblings, no `irc.commands.*` imports — mirrors `aliases.py`. `_compose_concentration_lines` lives in `memo_cmd.py` (the edge).
- **`CONCENTRATION_OVERLAP_PCT_THRESHOLD = 30.0` is in PERCENT UNITS (0–100), matching `weight_pct`. NOT a fraction.**
- **5 existing `IRC_*_BEGIN/END` marker pairs in src/** (verified via grep): `IRC_PICKS_TABLE_*`, `IRC_EVIDENCE_GAP_*`, `IRC_EXECUTION_LINES_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*`. Concentration becomes the 6th. `memo/auditor.py` is an LLM content reviewer with no structural-marker awareness — do NOT touch it.
- Citation ID format `\[ref:[0-9a-f]{16}\]` unchanged.
- Do NOT introduce `基金概况` indicator usage. Do NOT push.

---

## File Structure

**New files:**
- `src/irc/memo/concentration.py` — pure metric + `ConcentrationPair` frozen dataclass + `compute_concentration_pairs` + marker constants (≤ 160 lines).
- `tests/memo/test_concentration.py` — pure-logic tests for metric, pair generation, ordering, threshold boundary, and the `_compose_concentration_lines` renderer hook.

**Modified files:**
- `src/irc/memo/synthesizer.py` — append a 6th `if "<!-- IRC_CONCENTRATION_BEGIN -->" in skeleton:` clause to `synthesize_memo` so the LLM leaves the block verbatim.
- `src/irc/commands/memo_cmd.py` — import `_compose_concentration_lines` (or define it locally), build `op_rows_by_id` from `opportunity.get("rows")`, prepend the marker-wrapped tuple onto `risk_notes` next to the existing `_compose_evidence_gap_lines` call.

**Not modified (cross-check):**
- `src/irc/opportunity/types.py` — `OpportunityRow` shape unchanged.
- `src/irc/opportunity/advisory_gaps.py` — no new codes.
- `src/irc/memo/template.py` — marker constants live in the producing module per Q9; template.py is for skeleton-level markers only.
- `src/irc/memo/auditor.py` — not a structural gate; nothing to add.
- `tests/integration/test_publishable_set_lockdown.py` — existing two-run byte-equality coverage absorbs AC13.

---

## Task 1: Create `concentration.py` skeleton + marker constants + `CONCENTRATION_TOP_N` / `CONCENTRATION_OVERLAP_PCT_THRESHOLD`

**Files:**
- Create: `src/irc/memo/concentration.py`
- Test: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write the failing test for module-level constants (AC2 + AC3 + marker constants).**

Create `tests/memo/test_concentration.py`:

```python
"""Pure-logic tests for src/irc/memo/concentration.py (item 002).

Covers AC1–AC9 + AC13 of docs/2026-05-27-instrument-pickability/items/002-spec.md.
AC11 (no row-level state change) is verified by the absence of changes to
opportunity/types.py and is asserted indirectly by the existing
test_publishable_set_lockdown.py two-run byte equality.
"""
from __future__ import annotations


def test_concentration_top_n_constant():
    """AC2: CONCENTRATION_TOP_N is a module-level Final[int] = 10."""
    from irc.memo.concentration import CONCENTRATION_TOP_N
    assert CONCENTRATION_TOP_N == 10


def test_concentration_overlap_pct_threshold_constant():
    """AC3: CONCENTRATION_OVERLAP_PCT_THRESHOLD is 30.0 (percent units, NOT fraction)."""
    from irc.memo.concentration import CONCENTRATION_OVERLAP_PCT_THRESHOLD
    assert CONCENTRATION_OVERLAP_PCT_THRESHOLD == 30.0


def test_concentration_marker_constants():
    """AC9: marker constants live at module-top in concentration.py."""
    from irc.memo.concentration import (
        CONCENTRATION_MARKER_BEGIN,
        CONCENTRATION_MARKER_END,
    )
    assert CONCENTRATION_MARKER_BEGIN == "<!-- IRC_CONCENTRATION_BEGIN -->"
    assert CONCENTRATION_MARKER_END == "<!-- IRC_CONCENTRATION_END -->"
```

- [ ] **Step 2: Run the tests and verify they fail.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `ModuleNotFoundError: No module named 'irc.memo.concentration'` (3 errors).

- [ ] **Step 3: Create `concentration.py` with constants only.**

Create `src/irc/memo/concentration.py`:

```python
"""Holdings overlap / concentration analytic for memo §6 风险提示.

Pure module. Tier-1 import contract: imports from `irc.opportunity.types`
and `irc.fundamentals.types` only — no imports from `irc.memo.*` siblings,
no `irc.commands.*` imports. Mirrors `aliases.py` per CONTEXT.md
"Renderer tier-1 import contract".

Produces `ConcentrationPair` records summarising Top-N weighted-overlap
between every pair of active-fund picks. Memo-only — does NOT mutate
`OpportunityRow`, does NOT touch `evidence_gaps` / `advisory_gaps` /
`thesis_state`, does NOT emit `[ref:...]` markers.

See `docs/2026-05-27-instrument-pickability/items/002-spec.md` AC1–AC15
and CONTEXT.md entries for `IRC_CONCENTRATION_BEGIN/END`,
`weighted_overlap_pct`, `ConcentrationPair`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


# AC2 / spec Q2: Top-10 chosen because the 2026-05-27 CPO cluster extends
# through weight rank 6–8 in several active funds.
CONCENTRATION_TOP_N: Final[int] = 10

# AC3 / spec Q3+Q5: 30.0 percent units (0–100), matches ConstituentAnalysis
# .weight_pct unit per ADR 0002 §4. NOT a fraction. Boundary inclusive (>=)
# mirrors FOREIGN_HEAVY_THRESHOLD precedent.
CONCENTRATION_OVERLAP_PCT_THRESHOLD: Final[float] = 30.0

# AC9 / spec Q9: marker constants live at module-top in concentration.py
# (producing-module pattern, mirrors macro_pillar.py's MACRO_SECTION_MARKER_*).
CONCENTRATION_MARKER_BEGIN: Final[str] = "<!-- IRC_CONCENTRATION_BEGIN -->"
CONCENTRATION_MARKER_END: Final[str] = "<!-- IRC_CONCENTRATION_END -->"
```

- [ ] **Step 4: Run the tests and verify they pass.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `3 passed`.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/concentration.py tests/memo/test_concentration.py
git commit -m "feat(memo): scaffold concentration module with marker + threshold constants"
```

---

## Task 2: Implement `weighted_overlap_pct` metric (AC1)

**Files:**
- Modify: `src/irc/memo/concentration.py`
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write failing tests for the metric (AC1 + cardinality clarification).**

Append to `tests/memo/test_concentration.py`:

```python
def _analysis(symbol: str, weight: float):
    """Helper: build a minimal ConstituentAnalysis fixture."""
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=symbol, weight_pct=weight,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def test_weighted_overlap_pct_symmetric():
    """AC1: weighted_overlap_pct(A, B) == weighted_overlap_pct(B, A)."""
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0), _analysis("Y", 8.0), _analysis("Z", 4.0))
    b = (_analysis("X", 6.0), _analysis("Y", 12.0), _analysis("W", 5.0))
    assert weighted_overlap_pct(a, b) == weighted_overlap_pct(b, a)


def test_weighted_overlap_pct_known_intersection():
    """AC1: Σ min(w_A[s], w_B[s]) over shared symbols.

    A: X=10, Y=8, Z=4 | B: X=6, Y=12, W=5 | shared = {X, Y}
    Expected: min(10, 6) + min(8, 12) = 6 + 8 = 14.0
    """
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0), _analysis("Y", 8.0), _analysis("Z", 4.0))
    b = (_analysis("X", 6.0), _analysis("Y", 12.0), _analysis("W", 5.0))
    assert weighted_overlap_pct(a, b) == 14.0


def test_weighted_overlap_pct_no_overlap_returns_zero():
    """AC1: Σ over empty intersection is 0.0."""
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0),)
    b = (_analysis("Y", 10.0),)
    assert weighted_overlap_pct(a, b) == 0.0


def test_weighted_overlap_pct_empty_input_returns_zero():
    """Defensive: empty constituent_analyses on either side → 0.0."""
    from irc.memo.concentration import weighted_overlap_pct
    a = (_analysis("X", 10.0),)
    assert weighted_overlap_pct(a, ()) == 0.0
    assert weighted_overlap_pct((), a) == 0.0
    assert weighted_overlap_pct((), ()) == 0.0


def test_weighted_overlap_pct_truncates_to_top_n():
    """AC1: topN ranks by weight_pct desc, symbol asc tiebreaker; tail ignored.

    With Top-10 cap, an 11th holding with the same symbol on both sides must
    NOT contribute to the overlap.
    """
    from irc.memo.concentration import weighted_overlap_pct
    a = tuple(
        _analysis(f"S{i:02d}", 50.0 - i) for i in range(11)
    )  # S00..S10, weights 50,49,...,40
    b = (
        _analysis("S10", 100.0),  # would dominate if Top-N were unbounded
    )
    # S10 is rank 11 in `a` after topN truncation (Top-10), so intersection
    # with `b` is empty → 0.0.
    assert weighted_overlap_pct(a, b) == 0.0


def test_weighted_overlap_pct_handles_cardinality_below_top_n():
    """AC1 cardinality clarification (grill Q4): when len(A) < CONCENTRATION_TOP_N,
    topN(A) = A.constituent_analyses after the rank sort with no padding;
    symmetry preserved."""
    from irc.memo.concentration import weighted_overlap_pct
    # A has 4 holdings (< Top-10).
    a = (
        _analysis("X", 20.0), _analysis("Y", 15.0),
        _analysis("Z", 10.0), _analysis("W", 5.0),
    )
    b = (_analysis("X", 18.0), _analysis("Y", 12.0))
    # Intersection {X, Y}: min(20,18) + min(15,12) = 18 + 12 = 30.0.
    assert weighted_overlap_pct(a, b) == 30.0
    # Symmetry under asymmetric cardinality.
    assert weighted_overlap_pct(a, b) == weighted_overlap_pct(b, a)


def test_weighted_overlap_pct_tiebreak_by_symbol_ascending():
    """AC1: when two constituents share weight_pct, symbol ASC breaks the tie
    so two reordered inputs produce the same topN slice."""
    from irc.memo.concentration import weighted_overlap_pct
    # Both sides have 11 holdings with weight 10.0 each — only Top-10 by
    # symbol-asc tiebreaker should participate.
    syms_a = [f"S{i:02d}" for i in range(11)]  # S00..S10
    syms_b = [f"S{i:02d}" for i in range(11)]
    a = tuple(_analysis(s, 10.0) for s in syms_a)
    b = tuple(_analysis(s, 10.0) for s in syms_b)
    # Both topN slices are S00..S09 (symbol-asc tiebreaker drops S10);
    # intersection = S00..S09; overlap = 10 * 10.0 = 100.0.
    assert weighted_overlap_pct(a, b) == 100.0
```

- [ ] **Step 2: Run the tests and verify they fail.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `ImportError: cannot import name 'weighted_overlap_pct' from 'irc.memo.concentration'`.

- [ ] **Step 3: Implement `weighted_overlap_pct` and the `_top_n_by_weight` helper.**

Append to `src/irc/memo/concentration.py`:

```python
from irc.fundamentals.types import ConstituentAnalysis


def _top_n_by_weight(
    analyses: tuple[ConstituentAnalysis, ...],
    n: int = CONCENTRATION_TOP_N,
) -> tuple[ConstituentAnalysis, ...]:
    """Top-N constituents by weight_pct DESC, symbol ASC on tie.

    The secondary `c.symbol` key pins AC1's deterministic topN slice — two
    AkShare DataFrames with equal-weight holdings reordered must produce
    identical topN slices and thus identical pair overlaps.

    When len(analyses) < n, the full list (after sort) is returned with
    no padding (AC1 cardinality clarification / grill Q4).
    """
    ranked = sorted(analyses, key=lambda c: (-c.weight_pct, c.symbol))
    return tuple(ranked[:n])


def weighted_overlap_pct(
    a: tuple[ConstituentAnalysis, ...],
    b: tuple[ConstituentAnalysis, ...],
) -> float:
    """Σ_{s ∈ topN(A) ∩ topN(B)} min(w_A[s], w_B[s]).

    AC1: result in **percent units** (0.0–100.0), NOT a fraction. Symmetric:
    weighted_overlap_pct(A, B) == weighted_overlap_pct(B, A). Empty input
    on either side returns 0.0 (defensive — `OpportunityRow` with no
    constituent_analyses cannot participate per AC6).
    """
    top_a = {c.symbol: c.weight_pct for c in _top_n_by_weight(a)}
    top_b = {c.symbol: c.weight_pct for c in _top_n_by_weight(b)}
    shared = top_a.keys() & top_b.keys()
    return sum(min(top_a[s], top_b[s]) for s in shared)
```

- [ ] **Step 4: Run the tests and verify they pass.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `10 passed`.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/concentration.py tests/memo/test_concentration.py
git commit -m "feat(memo): implement weighted_overlap_pct metric (concentration AC1)"
```

---

## Task 3: `ConcentrationPair` frozen dataclass + factory with canonical ordering (AC5)

**Files:**
- Modify: `src/irc/memo/concentration.py`
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write failing tests for the dataclass + factory invariant.**

Append to `tests/memo/test_concentration.py`:

```python
def test_concentration_pair_is_frozen():
    """AC5: ConcentrationPair is a frozen dataclass."""
    from dataclasses import FrozenInstanceError
    from irc.memo.concentration import ConcentrationPair
    pair = ConcentrationPair(
        instrument_id_a="A", instrument_id_b="B",
        name_cn_a="a", name_cn_b="b",
        overlap_pct=50.0, shared_symbols=("X",),
    )
    try:
        pair.overlap_pct = 60.0  # type: ignore[misc]
        raise AssertionError("expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_make_concentration_pair_sorts_instrument_ids_alphabetically():
    """AC5: factory enforces instrument_id_a < instrument_id_b (strict)."""
    from irc.memo.concentration import make_concentration_pair
    pair = make_concentration_pair(
        iid_x="510300", name_x="沪深300",
        iid_y="005827", name_y="易方达蓝筹",
        overlap_pct_raw=42.5, shared_symbols=("000001", "600519"),
    )
    assert pair.instrument_id_a == "005827"
    assert pair.instrument_id_b == "510300"
    assert pair.name_cn_a == "易方达蓝筹"
    assert pair.name_cn_b == "沪深300"


def test_make_concentration_pair_argument_order_invariant():
    """AC5: passing the two funds in either order produces byte-identical pairs."""
    from irc.memo.concentration import make_concentration_pair
    p1 = make_concentration_pair(
        iid_x="A", name_x="甲", iid_y="B", name_y="乙",
        overlap_pct_raw=64.27, shared_symbols=("X", "Y"),
    )
    p2 = make_concentration_pair(
        iid_x="B", name_x="乙", iid_y="A", name_y="甲",
        overlap_pct_raw=64.27, shared_symbols=("Y", "X"),
    )
    assert p1 == p2


def test_make_concentration_pair_rounds_overlap_to_one_decimal():
    """AC5 / grill Q6: overlap_pct is set ONCE at construction via round(_, 1)."""
    from irc.memo.concentration import make_concentration_pair
    pair = make_concentration_pair(
        iid_x="A", name_x="甲", iid_y="B", name_y="乙",
        overlap_pct_raw=64.27, shared_symbols=("X",),
    )
    assert pair.overlap_pct == 64.3


def test_make_concentration_pair_sorts_shared_symbols_ascending():
    """AC5: shared_symbols sorted ASC (pins determinism on render)."""
    from irc.memo.concentration import make_concentration_pair
    pair = make_concentration_pair(
        iid_x="A", name_x="甲", iid_y="B", name_y="乙",
        overlap_pct_raw=50.0, shared_symbols=("ZZZ", "AAA", "MMM"),
    )
    assert pair.shared_symbols == ("AAA", "MMM", "ZZZ")
```

- [ ] **Step 2: Run the tests and verify they fail.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `ImportError: cannot import name 'ConcentrationPair'` (and `make_concentration_pair`).

- [ ] **Step 3: Add `ConcentrationPair` + `make_concentration_pair` to `concentration.py`.**

Append to `src/irc/memo/concentration.py`:

```python
@dataclass(frozen=True)
class ConcentrationPair:
    """One pairwise Top-N weighted-overlap record between two active-fund picks.

    Class-level invariant `instrument_id_a < instrument_id_b` (strict,
    alphabetical) — the factory `make_concentration_pair` sorts the two
    IDs before assignment so the two argument-orderings of the same fund
    pair produce byte-identical records.

    `overlap_pct` is `round(weighted_overlap_pct, 1)` set ONCE at
    construction (never re-rounded downstream — pins determinism by
    construction per grill Q6). `shared_symbols` sorted ASC.
    """
    instrument_id_a: str
    instrument_id_b: str
    name_cn_a: str
    name_cn_b: str
    overlap_pct: float
    shared_symbols: tuple[str, ...]


def make_concentration_pair(
    *,
    iid_x: str, name_x: str,
    iid_y: str, name_y: str,
    overlap_pct_raw: float,
    shared_symbols: tuple[str, ...],
) -> ConcentrationPair:
    """Factory enforcing AC5 invariants: alphabetic ID ordering, rounded
    overlap_pct (1dp), symbol-ASC sorted shared_symbols.
    """
    if iid_x < iid_y:
        a_id, a_name, b_id, b_name = iid_x, name_x, iid_y, name_y
    else:
        a_id, a_name, b_id, b_name = iid_y, name_y, iid_x, name_x
    return ConcentrationPair(
        instrument_id_a=a_id,
        instrument_id_b=b_id,
        name_cn_a=a_name,
        name_cn_b=b_name,
        overlap_pct=round(overlap_pct_raw, 1),
        shared_symbols=tuple(sorted(shared_symbols)),
    )
```

- [ ] **Step 4: Run the tests and verify they pass.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `15 passed`.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/concentration.py tests/memo/test_concentration.py
git commit -m "feat(memo): add ConcentrationPair frozen dataclass + canonical-ordering factory"
```

---

## Task 4: `compute_concentration_pairs` enumerator (AC4 + AC6 + AC8)

**Files:**
- Modify: `src/irc/memo/concentration.py`
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write failing tests for the enumerator.**

Append to `tests/memo/test_concentration.py`:

```python
def _op_row(iid: str, name: str, analyses: tuple = ()):
    """Helper: minimal OpportunityRow with constituent_analyses."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid, display_cn=name, provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(),
        constituent_analyses=analyses,
    )


def test_compute_concentration_pairs_returns_empty_below_threshold():
    """AC4: when no pair crosses the 30.0% threshold, result is empty tuple."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (
            _analysis("X", 10.0), _analysis("Y", 5.0),
        )),
        _op_row("B", "乙", (
            _analysis("Z", 10.0), _analysis("W", 5.0),
        )),
    )
    assert compute_concentration_pairs(rows) == ()


def test_compute_concentration_pairs_emits_one_pair_above_threshold():
    """AC4: a single qualifying pair is surfaced exactly once."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (
            _analysis("X", 20.0), _analysis("Y", 15.0),
        )),
        _op_row("B", "乙", (
            _analysis("X", 18.0), _analysis("Y", 12.0),
        )),
    )
    # Overlap = min(20,18) + min(15,12) = 18 + 12 = 30.0 → boundary inclusive.
    pairs = compute_concentration_pairs(rows)
    assert len(pairs) == 1
    assert pairs[0].instrument_id_a == "A"
    assert pairs[0].instrument_id_b == "B"
    assert pairs[0].overlap_pct == 30.0
    assert pairs[0].shared_symbols == ("X", "Y")


def test_compute_concentration_pairs_threshold_strict_below_excluded():
    """AC3: pairs strictly below 30.0% are NOT surfaced."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 9.0))),
        _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 11.0))),
    )
    # Overlap = min(20,18) + min(9,11) = 18 + 9 = 27.0 → below threshold.
    assert compute_concentration_pairs(rows) == ()


def test_compute_concentration_pairs_skips_rows_with_empty_constituents():
    """AC6: rows with constituent_analyses=() are silently skipped.

    A passive ETF (FundLevelSnapshot path) has empty constituent_analyses
    and cannot participate in a holdings-level overlap.
    """
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        _op_row("B", "乙", ()),  # passive — empty constituents
        _op_row("C", "丙", (_analysis("X", 18.0), _analysis("Y", 12.0))),
    )
    pairs = compute_concentration_pairs(rows)
    # Only A↔C is eligible (B is skipped).
    assert len(pairs) == 1
    assert (pairs[0].instrument_id_a, pairs[0].instrument_id_b) == ("A", "C")


def test_compute_concentration_pairs_three_funds_three_qualifying_pairs():
    """AC4: a fully-overlapping 3-fund set produces C(3,2) = 3 pairs."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 14.0))),
        _op_row("C", "丙", (_analysis("X", 17.0), _analysis("Y", 13.0))),
    )
    pairs = compute_concentration_pairs(rows)
    assert len(pairs) == 3
    pair_ids = [(p.instrument_id_a, p.instrument_id_b) for p in pairs]
    # AC4: each unordered pair appears exactly once (never (A,B) AND (B,A)).
    assert pair_ids == sorted(set(pair_ids), key=lambda t: t)


def test_compute_concentration_pairs_render_order_overlap_desc_then_id_asc():
    """AC8: pairs in result sorted by (overlap_pct DESC, id_a ASC, id_b ASC).

    Build three distinct pairs (no ties) using unique per-pair shared symbols so
    only intended pairs qualify. Tiebreaker exercised in a separate test below.

    [AMENDED: original fixture A,B,C,D all sharing X+Y produced C(4,2)=6 qualifying
    pairs, not 3 as asserted. Replaced with chain-fixture using unique shared symbols;
    separate tiebreak test added. — drift review claude/instrument-pickability-002]
    """
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("AB", 40.0),)),
        _op_row("B", "乙", (_analysis("AB", 38.0), _analysis("BC", 35.0))),
        _op_row("C", "丙", (_analysis("BC", 33.0), _analysis("CD", 32.0))),
        _op_row("D", "丁", (_analysis("CD", 30.0),)),
    )
    pairs = compute_concentration_pairs(rows)
    # A↔B=38.0, B↔C=33.0, C↔D=30.0; A↔C/A↔D/B↔D share no symbols → excluded.
    ids = [(p.overlap_pct, p.instrument_id_a, p.instrument_id_b) for p in pairs]
    assert ids == [(38.0, "A", "B"), (33.0, "B", "C"), (30.0, "C", "D")]


def test_compute_concentration_pairs_render_order_tiebreak_by_id():
    """AC8 tiebreaker: when overlap_pct ties, sort by id_a ASC then id_b ASC.

    [AMENDED: extracted from the original render-order test as a separate fixture
    after the original fixture was replaced. — drift review claude/instrument-pickability-002]
    """
    from irc.memo.concentration import compute_concentration_pairs
    # B↔C and A↔D both overlap at exactly 32.0 (using distinct shared symbols).
    rows = (
        _op_row("A", "甲", (_analysis("AD", 32.0),)),
        _op_row("B", "乙", (_analysis("BC", 32.0),)),
        _op_row("C", "丙", (_analysis("BC", 32.0),)),
        _op_row("D", "丁", (_analysis("AD", 32.0),)),
    )
    pairs = compute_concentration_pairs(rows)
    ids = [(p.overlap_pct, p.instrument_id_a, p.instrument_id_b) for p in pairs]
    # Both pairs tie at 32.0; A↔D comes before B↔C alphabetically by id_a.
    assert ids == [(32.0, "A", "D"), (32.0, "B", "C")]


def test_compute_concentration_pairs_two_argument_orderings_byte_equal():
    """AC5 + AC13: input rows in two orderings produce byte-identical pair tuples."""
    from irc.memo.concentration import compute_concentration_pairs
    a = _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0)))
    b = _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0)))
    assert compute_concentration_pairs((a, b)) == compute_concentration_pairs((b, a))
```

- [ ] **Step 2: Run the tests and verify they fail.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `ImportError: cannot import name 'compute_concentration_pairs'`.

- [ ] **Step 3: Implement `compute_concentration_pairs` and the renderer-facing sort.**

Append to `src/irc/memo/concentration.py`:

```python
from irc.opportunity.types import OpportunityRow


def _eligible_rows(
    rows: tuple[OpportunityRow, ...] | list[OpportunityRow],
) -> tuple[OpportunityRow, ...]:
    """AC6: only rows with non-empty constituent_analyses participate.

    Sorted by instrument_id ASC so the pair-enumeration loop's `i < j`
    canonicalisation (AC4) emits each unordered pair exactly once.
    """
    eligible = [r for r in rows if r.constituent_analyses]
    return tuple(sorted(eligible, key=lambda r: r.instrument_id))


def _shared_symbols(
    a: tuple[ConstituentAnalysis, ...],
    b: tuple[ConstituentAnalysis, ...],
) -> tuple[str, ...]:
    """Symbols present in both topN slices, sorted ASC for renderer determinism."""
    top_a = {c.symbol for c in _top_n_by_weight(a)}
    top_b = {c.symbol for c in _top_n_by_weight(b)}
    return tuple(sorted(top_a & top_b))


def compute_concentration_pairs(
    active_picks: tuple[OpportunityRow, ...] | list[OpportunityRow],
) -> tuple[ConcentrationPair, ...]:
    """Enumerate every pair of eligible rows; surface pairs whose
    weighted_overlap_pct >= CONCENTRATION_OVERLAP_PCT_THRESHOLD.

    Pure function. AC4: pairs deduplicated by sorting input by
    instrument_id ASC and iterating `i < j`. AC8: result sorted by
    (overlap_pct DESC, instrument_id_a ASC, instrument_id_b ASC). The
    round-then-sort sequence (NOT the inverse) ensures stability across
    float-equal pairs.
    """
    eligible = _eligible_rows(active_picks)
    pairs: list[ConcentrationPair] = []
    for i in range(len(eligible)):
        for j in range(i + 1, len(eligible)):
            row_a, row_b = eligible[i], eligible[j]
            overlap = weighted_overlap_pct(
                row_a.constituent_analyses, row_b.constituent_analyses,
            )
            if overlap < CONCENTRATION_OVERLAP_PCT_THRESHOLD:
                continue
            shared = _shared_symbols(
                row_a.constituent_analyses, row_b.constituent_analyses,
            )
            pairs.append(make_concentration_pair(
                iid_x=row_a.instrument_id, name_x=row_a.name_cn,
                iid_y=row_b.instrument_id, name_y=row_b.name_cn,
                overlap_pct_raw=overlap, shared_symbols=shared,
            ))
    return tuple(sorted(
        pairs,
        key=lambda p: (-p.overlap_pct, p.instrument_id_a, p.instrument_id_b),
    ))
```

- [ ] **Step 4: Run the tests and verify they pass.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `22 passed`.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/concentration.py tests/memo/test_concentration.py
git commit -m "feat(memo): implement compute_concentration_pairs with canonical render order"
```

---

## Task 5: Renderer helper `_compose_concentration_lines` in `memo_cmd.py` (AC7 + AC9)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write failing tests for the renderer hook.**

Append to `tests/memo/test_concentration.py`:

```python
def _pick(iid: str, name: str):
    """Helper: minimal PickRow."""
    from irc.memo.picks_table import PickRow
    return PickRow(
        instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
        role="alpha", target_weight=0.05, composite_score=70.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
    )


def test_compose_concentration_lines_returns_empty_when_no_pair_qualifies():
    """AC9 empty case: no marker block emitted, no §6 lines at all."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("A", "甲"), _pick("B", "乙")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (_analysis("X", 5.0),)),
        "B": _op_row("B", "乙", (_analysis("Y", 5.0),)),
    }
    assert _compose_concentration_lines(pick_rows, op_rows_by_id) == ()


def test_compose_concentration_lines_emits_marker_block_when_pair_qualifies():
    """AC9: marker-wrapped tuple with header + one bullet per pair."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("008382", "融通产业趋势股票"),
                 _pick("008555", "华商龙头优势混合")]
    op_rows_by_id = {
        "008382": _op_row("008382", "融通产业趋势股票", (
            _analysis("300502", 20.0), _analysis("300308", 15.0),
        )),
        "008555": _op_row("008555", "华商龙头优势混合", (
            _analysis("300502", 18.0), _analysis("300308", 14.0),
        )),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    assert lines
    joined = "\n".join(lines)
    assert "<!-- IRC_CONCENTRATION_BEGIN -->" in joined
    assert "<!-- IRC_CONCENTRATION_END -->" in joined
    assert "持仓集中度（Top-10 加权重合 ≥ 30%）" in joined
    assert "008382 融通产业趋势股票" in joined
    assert "008555 华商龙头优势混合" in joined
    assert "加权重合" in joined
    # Body bullet format per AC9.
    assert "↔" in joined
    assert "共同持仓" in joined


def test_compose_concentration_lines_skips_picks_missing_from_op_rows():
    """AC7: pick lookup tolerates missing op rows (e.g. venue proxy that
    doesn't appear in opportunity_report.json) — they cannot contribute."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("A", "甲"), _pick("missing", "缺失")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (_analysis("X", 20.0),)),
    }
    assert _compose_concentration_lines(pick_rows, op_rows_by_id) == ()


def test_compose_concentration_lines_caps_shared_symbols_at_5_with_ellipsis():
    """AC9: sym_list capped at 5 symbols with `...` when more than 5 exist."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    # Six shared symbols, each weighted heavily on both sides.
    syms = ["A1", "A2", "A3", "A4", "A5", "A6"]
    analyses_a = tuple(_analysis(s, 6.0) for s in syms)
    analyses_b = tuple(_analysis(s, 6.0) for s in syms)
    pick_rows = [_pick("X", "甲"), _pick("Y", "乙")]
    op_rows_by_id = {
        "X": _op_row("X", "甲", analyses_a),
        "Y": _op_row("Y", "乙", analyses_b),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    joined = "\n".join(lines)
    # First 5 ASC: A1/A2/A3/A4/A5; A6 elided.
    assert "A1/A2/A3/A4/A5..." in joined
    assert "（6 只）" in joined


def test_compose_concentration_lines_renders_at_top_of_six_bullets_format():
    """AC9: body bullet format exactly matches the spec template."""
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("A", "甲"), _pick("B", "乙")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (
            _analysis("X", 20.0), _analysis("Y", 15.0),
        )),
        "B": _op_row("B", "乙", (
            _analysis("X", 18.0), _analysis("Y", 12.0),
        )),
    }
    lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    body = [
        ln for ln in lines
        if ln.startswith("- ")
    ]
    assert len(body) == 1
    # Exact format: `- {id_a} {name_a} ↔ {id_b} {name_b}：加权重合 {pct:.1f}%，共同持仓 {syms}（{n} 只）`
    assert body[0] == "- A 甲 ↔ B 乙：加权重合 30.0%，共同持仓 X/Y（2 只）"
```

- [ ] **Step 2: Run the tests and verify they fail.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `ImportError: cannot import name '_compose_concentration_lines' from 'irc.commands.memo_cmd'`.

- [ ] **Step 3: Implement `_compose_concentration_lines` in `memo_cmd.py`.**

In `src/irc/commands/memo_cmd.py`, near the existing `_compose_evidence_gap_lines` helper (just after line 261, before `_today()` at line 264), add:

```python
def _compose_concentration_lines(
    pick_rows: list[PickRow],
    op_rows_by_id: dict[str, "OpportunityRow"],
) -> tuple[str, ...]:
    """Compose the §6 风险提示 持仓集中度 marker block (item 002 AC9).

    Looks up each `PickRow.instrument_id` in `op_rows_by_id` (built by the
    caller from the same `opportunity_rows` already in scope per AC7 /
    grill Q11 — NOT inside this helper, NOT cached on a module-level
    global). Active-fund-only because `compute_concentration_pairs`
    silently skips rows with empty `constituent_analyses` (AC6).

    Empty result (zero qualifying pairs) → no marker block emitted at all,
    mirroring the `IRC_EVIDENCE_GAP_*` empty-case (AC9). Pure.
    """
    from irc.memo.concentration import (
        CONCENTRATION_MARKER_BEGIN,
        CONCENTRATION_MARKER_END,
        CONCENTRATION_OVERLAP_PCT_THRESHOLD,
        compute_concentration_pairs,
    )
    candidates = tuple(
        op_rows_by_id[r.instrument_id]
        for r in pick_rows
        if r.instrument_id in op_rows_by_id
    )
    pairs = compute_concentration_pairs(candidates)
    if not pairs:
        return ()
    header = (
        f"持仓集中度（Top-10 加权重合 ≥ "
        f"{CONCENTRATION_OVERLAP_PCT_THRESHOLD:.0f}%）："
        "以下候选标的实质表达相近的底层敞口，触发条件成立后只应择一执行；"
        "同时持有将放大单一主题回撤风险。"
    )
    body_lines = [_format_concentration_bullet(p) for p in pairs]
    return (CONCENTRATION_MARKER_BEGIN, header, *body_lines, CONCENTRATION_MARKER_END)


def _format_concentration_bullet(pair) -> str:
    """One bullet per pair per AC9 template:
    `- {id_a} {name_a} ↔ {id_b} {name_b}：加权重合 {pct:.1f}%，共同持仓 {syms}（{n} 只）`.

    `syms` joins shared_symbols with `/`, capped at 5 followed by `...`
    when more exist (sorted ASC by AC5).
    """
    n = len(pair.shared_symbols)
    head = pair.shared_symbols[:5]
    suffix = "..." if n > 5 else ""
    syms = "/".join(head) + suffix
    return (
        f"- {pair.instrument_id_a} {pair.name_cn_a} ↔ "
        f"{pair.instrument_id_b} {pair.name_cn_b}："
        f"加权重合 {pair.overlap_pct:.1f}%，共同持仓 {syms}（{n} 只）"
    )
```

The forward reference `"OpportunityRow"` in the signature is a string literal (no new top-level import needed; the helper is dependency-injected at the call-site). The single intra-function import keeps the tier-1 contract clean.

- [ ] **Step 4: Run the tests and verify they pass.**

```bash
uv run pytest tests/memo/test_concentration.py -x
```

Expected: `27 passed`.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/commands/memo_cmd.py tests/memo/test_concentration.py
git commit -m "feat(memo): add _compose_concentration_lines renderer hook (concentration AC7+AC9)"
```

---

## Task 6: Wire `_compose_concentration_lines` into `run_memo` risk_notes (AC7 + AC9)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write failing integration test that flows the concentration block through `MemoInputs.risk_notes`.**

Append to `tests/memo/test_concentration.py`:

```python
def test_concentration_lines_render_through_skeleton_into_section_6():
    """Integration: a non-empty concentration tuple flows through
    `MemoInputs.risk_notes` (prepended) and renders inside §6."""
    from irc.memo.template import MemoInputs, render_skeleton
    inputs = MemoInputs(
        date_str="2026-05-27", gold_regime="—", gold_zone="—", gold_tilt="—",
        allocation_mode="build", macro_summary="—", top_picks=(),
        risk_notes=(
            "<!-- IRC_CONCENTRATION_BEGIN -->",
            "持仓集中度（Top-10 加权重合 ≥ 30%）：...",
            "- A 甲 ↔ B 乙：加权重合 50.0%，共同持仓 X/Y（2 只）",
            "<!-- IRC_CONCENTRATION_END -->",
            "其他风险条目。",
        ),
        tldr_lines=(),
    )
    md = render_skeleton(inputs)
    assert "## 6. 风险提示" in md
    assert "<!-- IRC_CONCENTRATION_BEGIN -->" in md
    assert "<!-- IRC_CONCENTRATION_END -->" in md
    assert "其他风险条目" in md
```

- [ ] **Step 2: Run the new test to confirm it passes (skeleton already renders any risk_notes lines).**

```bash
uv run pytest tests/memo/test_concentration.py::test_concentration_lines_render_through_skeleton_into_section_6 -x
```

Expected: `1 passed` (no changes needed to `template.py`; this test locks the integration shape).

- [ ] **Step 3: Wire the call into `run_memo` (the actual side-effectful wiring).**

In `src/irc/commands/memo_cmd.py`, locate the block beginning at line 820 (the existing `_compose_evidence_gap_lines` call) and append the concentration call IMMEDIATELY AFTER it. The exact location is:

```python
    # ADR 0005 + Item 001 (instrument-pickability): top_holdings_broker_thin
    # advisory marker block. Prepended last so it renders FIRST in §6.
    evidence_gap_lines = _compose_evidence_gap_lines(pick_rows)
    if evidence_gap_lines:
        risk_notes = tuple(evidence_gap_lines) + risk_notes
```

Replace with:

```python
    # ADR 0005 + Item 001 (instrument-pickability): top_holdings_broker_thin
    # advisory marker block. Prepended last so it renders FIRST in §6.
    evidence_gap_lines = _compose_evidence_gap_lines(pick_rows)
    if evidence_gap_lines:
        risk_notes = tuple(evidence_gap_lines) + risk_notes
    # Item 002 (instrument-pickability): 持仓集中度 marker block. Active-fund
    # picks with Top-10 weighted overlap >= 30% surface here. op_rows_by_id
    # is built once at this call-site per AC7 / grill Q11 (NOT inside the
    # pure helper) — dependency-injection edge.
    rebuilt_op_rows_typed = _reconstruct_opportunity_rows(rebuilt_op_rows)
    op_rows_by_id = {r.instrument_id: r for r in rebuilt_op_rows_typed}
    concentration_lines = _compose_concentration_lines(pick_rows, op_rows_by_id)
    if concentration_lines:
        risk_notes = tuple(concentration_lines) + risk_notes
```

Note: `_reconstruct_opportunity_rows` is already called later in the function (at the citation-gate block, line 892) for the same purpose. The extra call here is intentional — the concentration helper needs `OpportunityRow` instances now, and constructing them twice in the same `run_memo` invocation is acceptable (both calls are pure and the cost is negligible vs. the LLM round-trip that dominates the function's runtime). If file-size budget pressure later demands deduplication, lifting both call sites to a single early construction is a one-line refactor.

- [ ] **Step 4: Run the full memo suite to confirm no regression.**

```bash
uv run pytest tests/memo/ -x
```

Expected: all green (including the new 28 concentration tests). The `_apply_advisory_partition` and `_compose_evidence_gap_lines` paths are unchanged.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/commands/memo_cmd.py tests/memo/test_concentration.py
git commit -m "feat(memo): wire concentration marker block into run_memo §6 risk_notes"
```

---

## Task 7: Synthesizer prompt — lock the new marker block verbatim (AC10)

**Files:**
- Modify: `src/irc/memo/synthesizer.py`
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write a failing test asserting the new lock instruction appears in the synthesizer user prompt when the skeleton contains the marker.**

Append to `tests/memo/test_concentration.py`:

```python
def test_synthesizer_locks_concentration_block_when_marker_present():
    """AC10: synthesizer.py adds a verbatim-lock instruction for the
    IRC_CONCENTRATION_* marker pair — same pattern as the other 5 markers.

    [AMENDED: original plan used monkeypatch + ResolvedRoute(api_key=, retries=)
    kwargs that do not exist in the actual ResolvedRoute dataclass (which has only
    task/provider/model/base_url/api_key_env). Replaced with the project's
    established pattern: unittest.mock.patch + route=None, matching
    test_synthesizer_glossary.py. — drift review claude/instrument-pickability-002]
    """
    from unittest.mock import patch
    from irc.memo.synthesizer import synthesize_memo

    captured_messages: list = []

    def _fake_call_chat(route, messages, **kwargs):
        captured_messages.append(messages)

        class _Resp:
            text = "ok"
            prompt_tokens = 0
            completion_tokens = 0
        return _Resp()

    skeleton = "# memo\n<!-- IRC_CONCENTRATION_BEGIN -->\nbody\n<!-- IRC_CONCENTRATION_END -->\n"
    with patch("irc.memo.synthesizer.call_chat", side_effect=_fake_call_chat):
        synthesize_memo(skeleton, raw_ref_pool=[], route=None)  # type: ignore[arg-type]
    user_msg = next(m for m in captured_messages[0] if m["role"] == "user")["content"]
    assert "IRC_CONCENTRATION_BEGIN/END" in user_msg
    assert "原样保留" in user_msg  # the verbatim-lock keyword used by every other marker
```

- [ ] **Step 2: Run the test and verify it fails.**

```bash
uv run pytest tests/memo/test_concentration.py::test_synthesizer_locks_concentration_block_when_marker_present -x
```

Expected: `AssertionError` — the lock instruction is not yet emitted.

- [ ] **Step 3: Add the lock clause to `synthesize_memo`.**

In `src/irc/memo/synthesizer.py`, locate the existing block ending at line 140 (the `IRC_EVIDENCE_GAP_BEGIN` clause). Add a new clause immediately after it (right before `section_lock_instruction = "\n".join(locked_section_lines)`):

```python
    # Item 002 (instrument-pickability) lock for the §6 concentration block.
    if "<!-- IRC_CONCENTRATION_BEGIN -->" in skeleton:
        locked_section_lines.append(
            "第6节『风险提示』在 IRC_CONCENTRATION_BEGIN/END 标记之间的 bullet 必须**原样保留**："
            "该 bullet 由系统根据 Top-10 加权重合度自动生成，禁止改写、合并、"
            "新增或删除其中的任何条目，亦禁止改写其中的标的代码、名称、重合百分比或共同持仓清单。"
        )
```

- [ ] **Step 4: Run the new test to confirm it passes.**

```bash
uv run pytest tests/memo/test_concentration.py::test_synthesizer_locks_concentration_block_when_marker_present -x
```

Expected: `1 passed`.

- [ ] **Step 5: Run the full memo suite to confirm no regression in the existing synthesizer tests.**

```bash
uv run pytest tests/memo/ -x
```

Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add src/irc/memo/synthesizer.py tests/memo/test_concentration.py
git commit -m "feat(memo): synthesizer locks IRC_CONCENTRATION block verbatim (concentration AC10)"
```

---

## Task 8: Defensive boundary test — `compute_concentration_pairs` does NOT mutate inputs (AC11 + AC12)

**Files:**
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write tests asserting purity (no row mutation) + pick-ordering preservation.**

Append to `tests/memo/test_concentration.py`:

```python
def test_compute_concentration_pairs_does_not_mutate_input_rows():
    """AC11: pure transform — input OpportunityRows are not mutated.

    The frozen dataclass guarantee already enforces this at runtime; this
    test pins the expectation in case a future refactor adds a non-frozen
    wrapper.
    """
    from dataclasses import replace
    from irc.memo.concentration import compute_concentration_pairs
    a = _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0)))
    b = _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0)))
    snapshot_a = replace(a)
    snapshot_b = replace(b)
    _ = compute_concentration_pairs((a, b))
    # Equality on frozen dataclasses → field-wise equality.
    assert a == snapshot_a
    assert b == snapshot_b


def test_compose_concentration_lines_preserves_pick_row_order():
    """AC12: concentration analytic does NOT reorder pick_rows.

    The caller's `pick_rows` list is read-only (iterated in place). After
    the helper returns, pick ordering must be unchanged.
    """
    from irc.commands.memo_cmd import _compose_concentration_lines
    pick_rows = [_pick("B", "乙"), _pick("A", "甲")]
    op_rows_by_id = {
        "A": _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        "B": _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0))),
    }
    pre = [r.instrument_id for r in pick_rows]
    _ = _compose_concentration_lines(pick_rows, op_rows_by_id)
    post = [r.instrument_id for r in pick_rows]
    assert pre == post
```

- [ ] **Step 2: Run the tests and verify they pass (no production change required — frozen dataclasses + the pure helper guarantee this).**

```bash
uv run pytest tests/memo/test_concentration.py -k "does_not_mutate or preserves_pick_row_order" -x
```

Expected: `2 passed`.

- [ ] **Step 3: Commit.**

```bash
git add tests/memo/test_concentration.py
git commit -m "test(memo): pin concentration purity + pick-ordering invariants (AC11+AC12)"
```

---

## Task 9: Determinism regression — explicit two-run byte-equality test for `compute_concentration_pairs` (AC13)

**Files:**
- Modify: `tests/memo/test_concentration.py`

- [ ] **Step 1: Write a test that asserts byte-equal repr on two evaluations with shuffled inputs.**

Append to `tests/memo/test_concentration.py`:

```python
def test_compute_concentration_pairs_two_run_byte_equality_with_shuffled_inputs():
    """AC13: two calls on the same set with shuffled row order produce
    byte-identical pair tuples (locks the determinism contract that the
    existing test_publishable_set_lockdown.py::test_two_run_byte_equality_memo
    will then exercise via the full pipeline)."""
    from irc.memo.concentration import compute_concentration_pairs
    rows = (
        _op_row("A", "甲", (_analysis("X", 20.0), _analysis("Y", 15.0))),
        _op_row("B", "乙", (_analysis("X", 18.0), _analysis("Y", 12.0))),
        _op_row("C", "丙", (_analysis("X", 17.0), _analysis("Y", 13.0))),
        _op_row("D", "丁", ()),
    )
    shuffled = (rows[2], rows[0], rows[3], rows[1])  # deterministic shuffle
    a = compute_concentration_pairs(rows)
    b = compute_concentration_pairs(shuffled)
    assert a == b
    # Also assert repr-equality so any silent identity-vs-equality drift is caught.
    assert repr(a) == repr(b)
```

- [ ] **Step 2: Run the test and verify it passes.**

```bash
uv run pytest tests/memo/test_concentration.py::test_compute_concentration_pairs_two_run_byte_equality_with_shuffled_inputs -x
```

Expected: `1 passed`.

- [ ] **Step 3: Commit.**

```bash
git add tests/memo/test_concentration.py
git commit -m "test(memo): pin concentration two-run byte equality with shuffled inputs (AC13)"
```

---

## Task 10: Full-suite green check + lockdown regression sanity

**Files:** (none modified — verification only)

- [ ] **Step 1: Run the full memo + opportunity test suites.**

```bash
uv run pytest tests/memo/ tests/opportunity/ -x
```

Expected: all green. The new concentration tests (~30) all pass; no regression in the existing memo tests (test_evidence_gap_risk_note, test_picks_table_advisory_partition, test_synthesizer_glossary, etc.) or opportunity tests.

- [ ] **Step 2: Run the lockdown two-run byte-equality test specifically.**

```bash
uv run pytest tests/integration/test_publishable_set_lockdown.py::test_two_run_byte_equality_memo_after_run_memo -x
```

Expected: `1 passed` OR `skipped` (the test is gated on real-fixture availability; skip is acceptable). If the test runs and FAILS with a byte diff, audit the diff for `IRC_CONCENTRATION_*` content — any nondeterminism in pair ordering or shared_symbols ordering would surface here.

If the test skips on this machine due to fixture absence, document it: the lockdown is the regression gate per AC13, and CI runs it green. No fix-up is required at this layer; AC13 is locked by the unit test in Task 9 plus the pipeline-level coverage already in lockdown.

- [ ] **Step 3: Lint check.**

```bash
uv run ruff check src/irc/memo/concentration.py src/irc/commands/memo_cmd.py src/irc/memo/synthesizer.py tests/memo/test_concentration.py
```

Expected: no errors (line-length 100; target py312).

- [ ] **Step 4: Verify `concentration.py` is under the 200-line file budget.**

```bash
wc -l src/irc/memo/concentration.py
```

Expected: `< 200`. If at or above, extract one helper inline or reformat docstrings — do NOT split into a sibling module (that would break the single-file import contract for `compute_concentration_pairs`).

- [ ] **Step 5: Verify the renderer tier-1 import contract — `concentration.py` imports ONLY from `irc.opportunity.types` + `irc.fundamentals.types`.**

```bash
grep -E "^from irc\.|^import irc\." src/irc/memo/concentration.py
```

Expected output (exactly these two lines, in this order):

```
from irc.fundamentals.types import ConstituentAnalysis
from irc.opportunity.types import OpportunityRow
```

Any additional `irc.*` import is a violation of Constraints / grill Q10. Fix by moving the offending dependency to the caller in `memo_cmd.py`.

- [ ] **Step 6: Verify the marker pair is recognised exactly the same way as the other 5.**

```bash
grep -rno "IRC_CONCENTRATION_BEGIN\|IRC_CONCENTRATION_END" src/
```

Expected: 4 matches — one each in `src/irc/memo/concentration.py` (the two constant definitions) and one each in `src/irc/memo/synthesizer.py` and `src/irc/commands/memo_cmd.py` referring back to the constants (the synthesizer references the literal `<!-- IRC_CONCENTRATION_BEGIN -->` string per Task 7 Step 3 — that counts as 1 match). The exact count is `4–5` depending on whether the synthesizer uses the literal or the constant; either is acceptable as long as both files reference the marker pair.

---

## Task 11: Pipeline verification on cached evidence — empty case or live trigger?

**Files:** (none modified — verification only)

This is the final acceptance check called out in the orchestrator brief: "re-run the opportunity → memo pipeline on cached evidence; confirm if today's data triggers any concentration pair OR confirm the empty-case (no markers emitted)."

**Context:** `outputs/2026-05-27/trade_plan.yaml` contains 10 trade targets, of which all visible ones are ETFs or QDII proxies (518850, 161716, 017641, 019441, 003318, 519770, 159650, 511020, 511380, 513690). NONE of the spec's example CPO active funds (008382, 008555, 018956, 519770 sole exception — but 519770 in today's plan may or may not be an active fund) appear at full strength. Most picks have `constituent_analyses: []` in `opportunity_report.json` per the 50/79 empty-count check. The expected outcome is the **empty case: no marker block emitted**.

- [ ] **Step 1: Re-run only the memo stage on today's cached evidence.**

```bash
uv run irc run --only memo
```

Expected: exit code 0; `outputs/2026-05-27/memo.md` is written.

- [ ] **Step 2: Check whether the concentration marker block was emitted.**

```bash
grep -c "IRC_CONCENTRATION_BEGIN" outputs/2026-05-27/memo.md
```

Expected: `0` (empty case — no qualifying pair among picks) OR `1` (live trigger fired). EITHER outcome is acceptable. The two paths:

- **If `0`:** The empty-case path is confirmed working. Cross-check by inspecting the §6 风险提示 section — it should contain the usual bullets (real-yield risk, valuation pressure, venue/FX, timeliness, evidence gaps from item 001 if any) and NO 持仓集中度 sub-block.

  ```bash
  awk '/^## 6\./,/^## 7\./' outputs/2026-05-27/memo.md | head -40
  ```

  Expected: §6 风险提示 visible; no `持仓集中度` substring.

- **If `1`:** A live concentration trigger fired. Inspect the emitted block:

  ```bash
  awk '/IRC_CONCENTRATION_BEGIN/,/IRC_CONCENTRATION_END/' outputs/2026-05-27/memo.md
  ```

  Expected: a marker-wrapped block with the header `持仓集中度（Top-10 加权重合 ≥ 30%）：...` followed by one or more `- {id_a} {name_a} ↔ {id_b} {name_b}：加权重合 X.X%，共同持仓 ...（N 只）` bullets, sorted by overlap_pct DESC.

- [ ] **Step 3: Two-run byte equality on `memo.md` (AC13 production-path check).**

```bash
cp outputs/2026-05-27/memo.md /tmp/memo_run_a.md
uv run irc run --only memo
diff outputs/2026-05-27/memo.md /tmp/memo_run_a.md
```

Expected: empty diff (zero bytes different). If the diff is non-empty, the LLM was not deterministic in this re-run — that is a SEPARATE pre-existing concern (the synthesizer is `temperature=0.3`, so memo.md is byte-stable only when the marker blocks dominate the output). The concentration block is INSIDE markers and is locked by the synthesizer prompt instruction added in Task 7, so any diff inside the `<!-- IRC_CONCENTRATION_BEGIN -->`/`<!-- IRC_CONCENTRATION_END -->` region IS a regression that must be fixed before merging. A diff OUTSIDE the markers (LLM prose drift) is pre-existing and not in scope for item 002 — note it in the run report.

- [ ] **Step 4: Final integration sanity — full memo + opportunity test suites.**

```bash
uv run pytest tests/memo/ tests/opportunity/ -x
```

Expected: all green. If anything regressed, halt and investigate before committing further.

- [ ] **Step 5: NO commit at this step.** Verification only. The plan is complete after this task.

---

## Self-review checklist (run by plan author before handoff)

- [x] **AC1 (metric definition):** Tasks 2 — `weighted_overlap_pct` + cardinality sub-clause + symmetry test.
- [x] **AC2 (`CONCENTRATION_TOP_N`):** Task 1 + Task 2 (consumed by `_top_n_by_weight`).
- [x] **AC3 (`CONCENTRATION_OVERLAP_PCT_THRESHOLD` + unit clarification):** Task 1 (constant definition) + Task 4 (boundary-inclusive test).
- [x] **AC4 (symmetric pair generation, `i < j` after id-ASC sort):** Task 4 `compute_concentration_pairs` + dedup test.
- [x] **AC5 (`ConcentrationPair` shape + factory invariants):** Task 3.
- [x] **AC6 (active-fund only via `constituent_analyses != ()`):** Task 4 — `_eligible_rows` skips empty.
- [x] **AC7 (pick scope + `op_rows_by_id` origin):** Task 5 (helper) + Task 6 (call site).
- [x] **AC8 (render-order sort):** Task 4 — final `sorted(...)` key locks `(overlap_pct DESC, id_a ASC, id_b ASC)`.
- [x] **AC9 (marker block + body format + ≤5 symbol cap):** Task 5 — header text, bullet template, cap test.
- [x] **AC10 (synthesizer marker passthrough):** Task 7 — uses 5-existing-marker pattern verified via grill Q1.
- [x] **AC11 (no row-level state change):** No edits to `OpportunityRow` / `advisory_gaps` / etc; Task 8 pins purity.
- [x] **AC12 (no pick-ordering interaction):** Task 8 — pre/post `[r.instrument_id]` equality assertion.
- [x] **AC13 (two-run byte equality):** Task 9 (unit-level) + Task 11 Step 3 (pipeline-level). Existing `test_publishable_set_lockdown.py::test_two_run_byte_equality_memo_after_run_memo` absorbs the change automatically.
- [x] **AC14 (H3 / SAME-3 / citation gate v1 preserved):** No touches to `thesis_evidence`, citation_ids, dual-leg structural binding, or H3 predicate. Concentration emits no `[ref:...]` markers (Task 5 body format omits them entirely).
- [x] **AC15 (TDD coverage):** Every AC has at least one test written before production code; failing-test-first ordering enforced in every task.
- [x] **No placeholders:** Every code block is complete; no "TBD" / "implement later"; every shell command has expected output.
- [x] **Type consistency:** `ConcentrationPair`, `compute_concentration_pairs`, `make_concentration_pair`, `_compose_concentration_lines`, marker constants — names are used identically across Tasks 1–11.
- [x] **File budget:** `concentration.py` projected at ~140 lines (constants + dataclass + factory + `_top_n_by_weight` + `weighted_overlap_pct` + `_eligible_rows` + `_shared_symbols` + `compute_concentration_pairs`). Verified in Task 10 Step 4.
- [x] **Renderer tier-1 import contract:** Two and only two `irc.*` imports — `OpportunityRow`, `ConstituentAnalysis`. Verified in Task 10 Step 5.

---

## Spec gaps judgement-called by the plan author

1. **Where to call `_compose_concentration_lines` in `run_memo`.** Spec AC7 says "mirrors `_compose_evidence_gap_lines(pick_rows)` from item 001"; the plan places the call IMMEDIATELY AFTER the existing evidence-gap-lines call (Task 6 Step 3). This places the concentration block AFTER the evidence-gap block in §6 (which prepends, so concentration renders BEFORE evidence-gap). Rationale: concentration is the more actionable "pick-against" signal; evidence-gap is the more granular "this fund alone has weak coverage" signal. Operator reads concentration first. If the user prefers the inverse order, swap the two `if … : risk_notes = tuple(...) + risk_notes` blocks.

2. **`_reconstruct_opportunity_rows` is called twice in `run_memo`.** Already discussed in Task 6 Step 3 note. Accepted on the basis that the cost is negligible vs. LLM round-trip. A future refactor lifting both call sites to a single early construction is one-line; explicitly NOT in scope for item 002.

3. **AC10 lock instruction text.** Spec doesn't dictate exact wording. The plan uses the same boilerplate ("必须**原样保留**…禁止改写、合并、新增或删除") as the existing 5 marker locks, customised with concentration-specific keywords (Top-10, 加权重合度, 标的代码/名称/重合百分比/共同持仓清单). Matches the consistency hint in CONTEXT.md "Renderers + alias-builder" entry for `IRC_CONCENTRATION_BEGIN/END`.

4. **Today's data may produce zero concentration pairs.** As noted in Task 11: 2026-05-27's trade plan picks are mostly ETFs/QDII with empty `constituent_analyses` — empty-case is the EXPECTED outcome on this date. The plan handles both branches in Task 11 Step 2.
