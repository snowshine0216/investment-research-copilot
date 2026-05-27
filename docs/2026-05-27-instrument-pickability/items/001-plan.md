# Item 001 — `broker_empty` propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `broker_empty:<symbol>` markers on `ActiveFundSnapshot` Top-5 holdings load-bearing — surface a new advisory gap `top_holdings_broker_thin` in memo §6 风险提示 and demote affected picks in the §5 table, without mutating `thesis_state` or perturbing the H3 partition predicate.

**Architecture:** Add a new `advisory_gaps: tuple[str, ...] = ()` field to `OpportunityRow` / `ThesisCard` / `PickRow`. A new helper module `src/irc/opportunity/advisory_gaps.py` computes the gap from `ActiveFundSnapshot`; `derive_thesis_from_evidence`'s active-fund branch emits the code via its existing `gaps` return slot; `_partition_gaps` becomes a 3-way split routing the code to `advisory_gaps` instead of `evidence_gaps`. Renderers (memo §6 marker block, picks-table stable partition, discipline header suffix) read the new field. The H3 partition predicate (`evidence_gaps == ()`) and the `thesis_state` setter invariant are preserved verbatim.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, uv. Pure functions only; effects stay at the CLI/I/O edges.

**Project constraints (from CLAUDE.md + CONTEXT.md + ADR 0005):**
- TDD mandatory: red → green → refactor. Tests written **before** production code.
- Functional / immutable: `dataclasses.replace`, tuple concat, spread; never mutate `OpportunityRow` / `ActiveFundSnapshot`.
- Files <200 lines (ideal); functions <20 lines (ideal). `thesis_evidence.py` is already at 454 lines — DO NOT enlarge it; extract helpers.
- `thesis_state` setter invariant: only `derive_thesis_from_evidence` writes `thesis_state`. The new gap goes through the existing `gaps` return slot (tuple position 4).
- H3 invariant: `evidence_gaps == ()` predicate is untouched. `advisory_gaps` is orthogonal.
- Citation ID format `\[ref:[0-9a-f]{16}\]` is unchanged — this item adds no citations.
- Deterministic memo markers: new `<!-- IRC_EVIDENCE_GAP_BEGIN -->` / `<!-- IRC_EVIDENCE_GAP_END -->` block lives inside §6, follows the existing pattern, and the synthesizer prompt is updated to leave the block verbatim.
- Do NOT use `find` from `/` for searches. Do NOT introduce `基金概况` indicator usage.

---

## File Structure

**New files:**
- `src/irc/opportunity/advisory_gaps.py` — helpers + threshold constants + code (≤ 80 lines).
- `tests/opportunity/test_advisory_gaps.py` — pure-logic tests for the threshold/helpers.
- `tests/opportunity/test_top_holdings_broker_thin.py` — end-to-end tests for `derive_thesis_from_evidence` + `build_opportunity_row` emitting the gap.
- `tests/memo/test_evidence_gap_risk_note.py` — renderer test for the §6 marker block.
- `tests/memo/test_picks_table_advisory_partition.py` — stable-partition test for pick ordering.

**Modified files:**
- `src/irc/opportunity/types.py` — add `advisory_gaps` field to `OpportunityRow`, `ThesisCard`, `DisciplineRow`.
- `src/irc/opportunity/states.py` — `_partition_gaps` becomes 3-way; `ADVISORY_GAP_CODES` re-export; `build_opportunity_row` passes new field; `derive_fetch_types_attempted` untouched.
- `src/irc/opportunity/thesis_evidence.py` — active-fund branch imports `should_emit_top_holdings_broker_thin` and appends to its `gaps` return.
- `src/irc/opportunity/cards.py` — propagate `advisory_gaps` from row to card.
- `src/irc/opportunity/report.py` — `_row_to_dict` adds `advisory_gaps`; `_card_to_dict` adds `advisory_gaps`; `_render_section` extends per-fund header line.
- `src/irc/memo/template.py` — add `EVIDENCE_GAP_MARKER_BEGIN/END` constants; threading via `MemoInputs.evidence_gap_lines`.
- `src/irc/memo/picks_table.py` — `PickRow` gains `advisory_gaps: tuple[str, ...] = ()`.
- `src/irc/commands/memo_cmd.py` — `_build_pick_rows` reads `op.get("advisory_gaps")`; after pick_rows is built, apply stable partition; `_compose_evidence_gap_lines` helper builds the §6 marker block; `risk_notes` tuple prepends it.
- `src/irc/memo/synthesizer.py` — add the verbatim-lock instruction for the new marker.
- `CONTEXT.md` — (already updated in grill commit 43a61bf; no further changes required).

---

## Task 1: Add `advisory_gaps` field to `OpportunityRow` / `ThesisCard` / `DisciplineRow`

**Files:**
- Modify: `src/irc/opportunity/types.py`
- Test: `tests/opportunity/test_states.py` (existing — extend with one new test)

- [ ] **Step 1: Write a failing test for the new field default**

Append to `tests/opportunity/test_states.py` (end of file):

```python
def test_opportunity_row_default_advisory_gaps_is_empty_tuple():
    """ADR 0005: `advisory_gaps` is a tuple[str, ...] that defaults to ()."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    row = OpportunityRow(
        instrument_id="x", name_cn="x", asset_class="cn_etf", theme=None,
        lookthrough_target=LookthroughTarget(
            kind="broad_index", key="x", display_cn="x", provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(),
    )
    assert row.advisory_gaps == ()


def test_thesis_card_default_advisory_gaps_is_empty_tuple():
    from irc.opportunity.types import ThesisCard

    card = ThesisCard(
        instrument_id="x", name_cn="x", asset_class="cn_etf", theme=None,
        role="", lookthrough_target="x", entry_reason="",
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        dca_action="normal_dca", risk_action="none",
        falsification_triggers=(), trim_triggers=(),
        do_not_sell_just_because=(), review_cadence="weekly_light_monthly_full",
        evidence_gaps=(),
    )
    assert card.advisory_gaps == ()


def test_discipline_row_default_advisory_gaps_is_empty_tuple():
    from irc.opportunity.types import DisciplineRow

    drow = DisciplineRow(
        instrument_id="x", name_cn="x", asset_class="cn_etf", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
    )
    assert drow.advisory_gaps == ()
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/opportunity/test_states.py -k "advisory_gaps" -x
```
Expected: 3 failures with `AttributeError: 'OpportunityRow' object has no attribute 'advisory_gaps'` (or equivalent).

- [ ] **Step 3: Add the field to all three dataclasses**

In `src/irc/opportunity/types.py`, edit `OpportunityRow` (lines 142–163), `ThesisCard` (lines 166–190), `DisciplineRow` (lines 193–208). For each, add `advisory_gaps: tuple[str, ...] = ()` immediately after the existing `evidence_gaps` field.

For `OpportunityRow` change the existing block:
```python
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()
```
to:
```python
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()
    advisory_gaps: tuple[str, ...] = ()
```

For `ThesisCard` change the block ending:
```python
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()
    # Item 003: per-constituent structured evidence (threaded from OpportunityRow).
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```
to:
```python
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()
    advisory_gaps: tuple[str, ...] = ()
    # Item 003: per-constituent structured evidence (threaded from OpportunityRow).
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

For `DisciplineRow` change the block ending:
```python
    evidence_gaps: tuple[str, ...] = ()
    fetch_types_attempted: tuple[str, ...] = ()
```
to:
```python
    evidence_gaps: tuple[str, ...] = ()
    fetch_types_attempted: tuple[str, ...] = ()
    advisory_gaps: tuple[str, ...] = ()
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
uv run pytest tests/opportunity/test_states.py -k "advisory_gaps" -x
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/types.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): add advisory_gaps field to OpportunityRow/ThesisCard/DisciplineRow"
```

---

## Task 2: Create `advisory_gaps.py` helper module with threshold constants + emission logic

**Files:**
- Create: `src/irc/opportunity/advisory_gaps.py`
- Test: `tests/opportunity/test_advisory_gaps.py`

- [ ] **Step 1: Write failing tests for the helpers**

Create `tests/opportunity/test_advisory_gaps.py`:

```python
"""Pure-logic tests for src/irc/opportunity/advisory_gaps.py."""
from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


def _analysis(symbol: str, weight_pct: float, failures: tuple[str, ...] = ()) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=symbol, weight_pct=weight_pct,
        evidence=(), failure_reasons=failures, one_line_view="",
    )


def _snap(*analyses: ConstituentAnalysis) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id="000001", source_report_date="", source_report_quarter="2026Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )


def test_count_broker_empty_top5_counts_only_top5_with_broker_empty():
    from irc.opportunity.advisory_gaps import count_broker_empty_top5
    snap = _snap(
        _analysis("A", 10.0, ("broker_empty:A",)),
        _analysis("B", 9.0, ("broker_empty:B",)),
        _analysis("C", 8.0, ()),
        _analysis("D", 7.0, ()),
        _analysis("E", 6.0, ()),
        _analysis("F", 1.0, ("broker_empty:F",)),  # outside Top-5
    )
    assert count_broker_empty_top5(snap) == 2


def test_weight_broker_empty_top5_sums_only_top5_with_broker_empty():
    from irc.opportunity.advisory_gaps import weight_broker_empty_top5
    snap = _snap(
        _analysis("A", 12.0, ("broker_empty:A",)),
        _analysis("B", 10.0, ("broker_empty:B",)),
        _analysis("C", 8.0, ()),
        _analysis("D", 7.0, ()),
        _analysis("E", 6.0, ()),
    )
    assert weight_broker_empty_top5(snap) == 22.0


def test_should_emit_returns_true_when_count_threshold_met():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(
        _analysis("A", 5.0, ("broker_empty:A",)),
        _analysis("B", 4.0, ("broker_empty:B",)),
        _analysis("C", 3.0, ()),
    )
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_should_emit_returns_true_when_weight_threshold_met():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    # Single 25%-weight Top-1 with broker_empty triggers the weight disjunct.
    snap = _snap(
        _analysis("A", 25.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_should_emit_false_when_neither_threshold_met():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(
        _analysis("A", 10.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    assert should_emit_top_holdings_broker_thin(snap) is False


def test_should_emit_false_on_empty_snapshot():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap()
    assert should_emit_top_holdings_broker_thin(snap) is False


def test_should_emit_count_boundary_inclusive():
    """`>=2` is boundary-inclusive (mirrors FOREIGN_HEAVY_THRESHOLD precedent)."""
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(
        _analysis("A", 5.0, ("broker_empty:A",)),
        _analysis("B", 4.0, ("broker_empty:B",)),
    )
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_should_emit_weight_boundary_inclusive():
    """`>=20.0` is boundary-inclusive."""
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(_analysis("A", 20.0, ("broker_empty:A",)))
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_advisory_gap_codes_contains_top_holdings_broker_thin():
    from irc.opportunity.advisory_gaps import ADVISORY_GAP_CODES
    assert "top_holdings_broker_thin" in ADVISORY_GAP_CODES


def test_threshold_constants_are_named():
    """ADR 0005 + spec AC3: magic numbers must have names."""
    from irc.opportunity.advisory_gaps import (
        TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD,
        TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD,
    )
    assert TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD == 2
    assert TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD == 20.0
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/opportunity/test_advisory_gaps.py -x
```
Expected: all tests fail with `ModuleNotFoundError: No module named 'irc.opportunity.advisory_gaps'`.

- [ ] **Step 3: Create the helper module**

Create `src/irc/opportunity/advisory_gaps.py`:

```python
"""Advisory gap emission for `OpportunityRow.advisory_gaps`.

See ADR 0005 and CONTEXT.md "Failure-mode + audit policy" for the
`advisory_gaps` semantic. First (and currently only) member:
`top_holdings_broker_thin` — fires when an `ActiveFundSnapshot`'s Top-5
holdings have weak broker coverage.

Pure module. No I/O. Imported by `thesis_evidence.py`'s active-fund branch
(via the existing `gaps` return slot) and re-exported by `states.py` for
the 3-way `_partition_gaps` split.
"""
from __future__ import annotations

from typing import Final

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD: Final[int] = 2
TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD: Final[float] = 20.0
_TOP_N: Final[int] = 5

ADVISORY_GAP_CODES: Final[frozenset[str]] = frozenset({
    "top_holdings_broker_thin",
})


def _has_broker_empty(analysis: ConstituentAnalysis) -> bool:
    """True when any failure_reason matches `broker_empty:*`."""
    return any(r.startswith("broker_empty:") for r in analysis.failure_reasons)


def _top_n_by_weight(
    snapshot: ActiveFundSnapshot, n: int = _TOP_N,
) -> tuple[ConstituentAnalysis, ...]:
    """Return the Top-N constituents by weight_pct descending."""
    ranked = sorted(
        snapshot.constituent_analyses,
        key=lambda c: -c.weight_pct,
    )
    return tuple(ranked[:n])


def count_broker_empty_top5(snapshot: ActiveFundSnapshot) -> int:
    """Number of Top-5 holdings with `broker_empty:*` in failure_reasons."""
    return sum(1 for c in _top_n_by_weight(snapshot) if _has_broker_empty(c))


def weight_broker_empty_top5(snapshot: ActiveFundSnapshot) -> float:
    """Sum of weight_pct over Top-5 holdings with `broker_empty:*` (0–100)."""
    return sum(c.weight_pct for c in _top_n_by_weight(snapshot) if _has_broker_empty(c))


def should_emit_top_holdings_broker_thin(snapshot: ActiveFundSnapshot) -> bool:
    """Disjunctive OR — count >= 2 OR weight_pct sum >= 20.0. Boundary inclusive."""
    return (
        count_broker_empty_top5(snapshot) >= TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD
        or weight_broker_empty_top5(snapshot) >= TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD
    )
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
uv run pytest tests/opportunity/test_advisory_gaps.py -x
```
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/advisory_gaps.py tests/opportunity/test_advisory_gaps.py
git commit -m "feat(opportunity): add advisory_gaps helper module with broker-thin threshold"
```

---

## Task 3: `_partition_gaps` becomes 3-way; `ADVISORY_GAP_CODES` re-export

**Files:**
- Modify: `src/irc/opportunity/states.py`
- Test: `tests/opportunity/test_states.py`

- [ ] **Step 1: Write failing tests for the 3-way split**

Append to `tests/opportunity/test_states.py`:

```python
def test_partition_gaps_returns_3_tuple_with_advisory():
    from irc.opportunity.states import _partition_gaps
    real, expected, advisory = _partition_gaps((
        "missing_broker_coverage",
        "constituent_not_applicable",
        "top_holdings_broker_thin",
    ))
    assert real == ("missing_broker_coverage",)
    assert expected == ("constituent_not_applicable",)
    assert advisory == ("top_holdings_broker_thin",)


def test_partition_gaps_empty_input_returns_three_empty_tuples():
    from irc.opportunity.states import _partition_gaps
    assert _partition_gaps(()) == ((), (), ())


def test_advisory_gap_codes_re_exported_from_states():
    from irc.opportunity.states import ADVISORY_GAP_CODES
    assert "top_holdings_broker_thin" in ADVISORY_GAP_CODES
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/opportunity/test_states.py -k "partition_gaps or advisory_gap_codes_re_exported" -x
```
Expected: 3 failures (`_partition_gaps` returns 2-tuple; `ADVISORY_GAP_CODES` not importable from `states`).

- [ ] **Step 3: Update `_partition_gaps` and re-export `ADVISORY_GAP_CODES`**

Replace in `src/irc/opportunity/states.py` lines 27–48:

```python
EXPECTED_OMISSION_CODES: frozenset[str] = frozenset({
    "constituent_not_applicable",
})


def _partition_gaps(
    gaps: tuple[str, ...] | list[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a flat gap list into (real_gaps, expected_omissions).

    Real gaps are signals the operator can act on. Expected omissions are
    structural non-features (e.g. an asset class that has no constituents
    by design) that we surface separately so they don't pollute the
    actionable list.
    """
    real, expected = [], []
    for g in gaps:
        if g in EXPECTED_OMISSION_CODES:
            expected.append(g)
        else:
            real.append(g)
    return tuple(real), tuple(expected)
```

with:

```python
from irc.opportunity.advisory_gaps import ADVISORY_GAP_CODES

EXPECTED_OMISSION_CODES: frozenset[str] = frozenset({
    "constituent_not_applicable",
})


def _partition_gaps(
    gaps: tuple[str, ...] | list[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Split a flat gap list into (real_gaps, expected_omissions, advisory_gaps).

    - real_gaps: row-blocking signals (H3 routes any non-empty value to gapped_rows).
    - expected_omissions: structural non-features by design (e.g.
      `constituent_not_applicable` for asset classes without constituents).
    - advisory_gaps: non-blocking advisories that publishable rows still surface
      (ADR 0005). H3 partition predicate stays `evidence_gaps == ()` — orthogonal.
    """
    real, expected, advisory = [], [], []
    for g in gaps:
        if g in EXPECTED_OMISSION_CODES:
            expected.append(g)
        elif g in ADVISORY_GAP_CODES:
            advisory.append(g)
        else:
            real.append(g)
    return tuple(real), tuple(expected), tuple(advisory)
```

Add the import near the existing imports (after `from irc.opportunity.thesis_evidence import ...`).

- [ ] **Step 4: Update `build_opportunity_row` to consume the 3-tuple and pass `advisory_gaps`**

In `src/irc/opportunity/states.py`, replace lines 537–557:

```python
    combined_gaps = tuple(structural_gaps) + tuple(thesis_gaps)
    evidence_gaps_filtered, expected_omissions = _partition_gaps(combined_gaps)
    return OpportunityRow(
        instrument_id=inp.instrument_id,
        name_cn=inp.name_cn,
        asset_class=inp.asset_class,
        theme=inp.theme,
        lookthrough_target=target,
        valuation_state=valuation,
        heat_state=heat,
        thesis_state=thesis,
        product_quality_state=product,
        opportunity_state=state,
        opportunity_reason=reason,
        evidence_gaps=evidence_gaps_filtered,
        expected_omissions=expected_omissions,
        thesis_evidence=evidence,
        contributing_dimensions=dimensions,
        fetch_types_attempted=derive_fetch_types_attempted(snapshot),
        constituent_analyses=constituent_analyses,
    )
```

with:

```python
    combined_gaps = tuple(structural_gaps) + tuple(thesis_gaps)
    evidence_gaps_filtered, expected_omissions, advisory_gaps = (
        _partition_gaps(combined_gaps)
    )
    return OpportunityRow(
        instrument_id=inp.instrument_id,
        name_cn=inp.name_cn,
        asset_class=inp.asset_class,
        theme=inp.theme,
        lookthrough_target=target,
        valuation_state=valuation,
        heat_state=heat,
        thesis_state=thesis,
        product_quality_state=product,
        opportunity_state=state,
        opportunity_reason=reason,
        evidence_gaps=evidence_gaps_filtered,
        expected_omissions=expected_omissions,
        advisory_gaps=advisory_gaps,
        thesis_evidence=evidence,
        contributing_dimensions=dimensions,
        fetch_types_attempted=derive_fetch_types_attempted(snapshot),
        constituent_analyses=constituent_analyses,
    )
```

- [ ] **Step 5: Run the new tests AND the existing states tests to confirm no regression**

```bash
uv run pytest tests/opportunity/test_states.py -x
```
Expected: all tests pass (the 3-way return shape is the only behavioral change; old 2-tuple callers must not exist anywhere — verify next step).

- [ ] **Step 6: Verify no other callers of `_partition_gaps` exist**

```bash
grep -rn "_partition_gaps" /Users/snow/Documents/Repository/investment-research-copilot/src /Users/snow/Documents/Repository/investment-research-copilot/tests
```
Expected output: matches only in `src/irc/opportunity/states.py` (definition + one call inside `build_opportunity_row`) and `tests/opportunity/test_states.py` (the new tests). If any other call site appears, update it to consume the 3-tuple before continuing.

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "refactor(opportunity): _partition_gaps becomes 3-way for advisory_gaps"
```

---

## Task 4: `derive_thesis_from_evidence` active-fund branch emits the gap

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py`
- Test: `tests/opportunity/test_top_holdings_broker_thin.py` (new)

- [ ] **Step 1: Write failing tests for the active-fund gap emission**

Create `tests/opportunity/test_top_holdings_broker_thin.py`:

```python
"""End-to-end tests for the `top_holdings_broker_thin` advisory gap.

Covers AC1 (gap code in advisory_gaps), AC2 (emitted by derive_thesis_from_evidence),
AC3 (threshold), AC4 (active-fund only), AC6 (H3 predicate unchanged).
"""
from __future__ import annotations

from irc.fundamentals.types import (
    ActiveFundSnapshot,
    ConstituentAnalysis,
    FundLevelSnapshot,
)


def _analysis(symbol: str, weight: float, failures: tuple[str, ...] = ()) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=symbol, weight_pct=weight,
        evidence=(), failure_reasons=failures, one_line_view="",
    )


def _active_snap(*analyses: ConstituentAnalysis) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2026Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )


def test_active_fund_with_2_broker_empty_in_top5_emits_advisory_gap():
    """AC1+AC3: count_broker_empty_top5 >= 2 triggers the gap."""
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert "top_holdings_broker_thin" in gaps


def test_active_fund_with_25pct_single_holding_broker_empty_emits_gap():
    """AC3: weight_broker_empty_top5 >= 20.0 alone is sufficient."""
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = _active_snap(
        _analysis("A", 25.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert "top_holdings_broker_thin" in gaps


def test_active_fund_below_threshold_no_gap():
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = _active_snap(
        _analysis("A", 5.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert "top_holdings_broker_thin" not in gaps


def test_fund_level_snapshot_never_emits_advisory_gap():
    """AC4: FundLevelSnapshot (passive ETF / gold / bond / QDII) is exempt."""
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = FundLevelSnapshot(
        fund_id="518880", source_report_date="", source_report_quarter="2026Q1",
        cache_probed_at="", nav_report=None, announcements=(),
        evidence=(), evidence_gaps=(),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="gold", owner_instrument_id="518880",
    )
    assert "top_holdings_broker_thin" not in gaps


def test_active_fund_advisory_gap_goes_to_advisory_gaps_not_evidence_gaps():
    """AC6: H3 partition predicate is preserved — gap routes through advisory_gaps,
    NOT evidence_gaps. Row stays publishable."""
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    assert "top_holdings_broker_thin" in row.advisory_gaps
    assert "top_holdings_broker_thin" not in row.evidence_gaps
    # H3 publishability predicate stays exactly `evidence_gaps == ()`.
    # Other unrelated structural gaps may still be present (e.g.
    # missing_valuation_data) — the assertion that matters is the advisory
    # gap does NOT leak into evidence_gaps.
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -x
```
Expected: 5 failures — the active-fund branch does not yet append `top_holdings_broker_thin` to its `gaps`.

- [ ] **Step 3: Wire the helper into `derive_thesis_from_evidence`**

In `src/irc/opportunity/thesis_evidence.py` add the import (near line 26, after the existing imports):

```python
from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
```

In the active-fund branch (lines 374–387), replace:

```python
    if isinstance(snapshot, ActiveFundSnapshot):
        analyses = snapshot.constituent_analyses
        flattened = _flatten_analyses(analyses)
        # Item 003: do NOT stamp evidence_gaps yet; item 006 H2 owns that.
        gaps: tuple[str, ...] = ()
        if flattened:
            state: ThesisState = "intact"
            reason = (
                f"主动基金 {len(analyses)} 个核心持仓的成分股证据已收集。"
            )
        else:
            state = "evidence_insufficient"
            reason = "主动基金未能收集到任何成分股证据。"
        return state, reason, flattened, gaps, tuple(analyses)  # type: ignore[return-value]
```

with:

```python
    if isinstance(snapshot, ActiveFundSnapshot):
        analyses = snapshot.constituent_analyses
        flattened = _flatten_analyses(analyses)
        # Item 003: do NOT stamp evidence_gaps yet; item 006 H2 owns that.
        # ADR 0005: emit advisory `top_holdings_broker_thin` through the existing
        # gaps return slot; states._partition_gaps routes it to advisory_gaps
        # (NOT evidence_gaps — H3 predicate stays unchanged).
        gaps: tuple[str, ...] = ()
        if should_emit_top_holdings_broker_thin(snapshot):
            gaps = gaps + ("top_holdings_broker_thin",)
        if flattened:
            state: ThesisState = "intact"
            reason = (
                f"主动基金 {len(analyses)} 个核心持仓的成分股证据已收集。"
            )
        else:
            state = "evidence_insufficient"
            reason = "主动基金未能收集到任何成分股证据。"
        return state, reason, flattened, gaps, tuple(analyses)  # type: ignore[return-value]
```

- [ ] **Step 4: Run the new tests and verify they pass**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -x
```
Expected: `5 passed`.

- [ ] **Step 5: Run the full opportunity test suite to confirm no regression**

```bash
uv run pytest tests/opportunity/ -x
```
Expected: all green. If `test_thesis_evidence.py` fails because some existing test fixture incidentally crosses the new threshold, audit the fixture — the `broker_empty:*` failure_reasons are only set explicitly in test fixtures, so no incidental triggers should exist.

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/thesis_evidence.py tests/opportunity/test_top_holdings_broker_thin.py
git commit -m "feat(opportunity): derive_thesis_from_evidence emits top_holdings_broker_thin"
```

---

## Task 5: Serialize `advisory_gaps` in `opportunity_report.json` + `thesis_cards.yaml`

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Modify: `src/irc/opportunity/cards.py`
- Test: `tests/opportunity/test_top_holdings_broker_thin.py` (extend)

- [ ] **Step 1: Write failing tests for serialization**

Append to `tests/opportunity/test_top_holdings_broker_thin.py`:

```python
def test_row_to_dict_serializes_advisory_gaps():
    from irc.opportunity.report import _row_to_dict
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    d = _row_to_dict(row)
    assert d["advisory_gaps"] == ["top_holdings_broker_thin"]


def test_card_to_dict_serializes_advisory_gaps():
    from irc.opportunity.cards import build_thesis_card
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.report import _card_to_dict
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    pos = PositionContext(is_holding=False, drawdown_since_entry=None,
                         portfolio_weight=None, target_band_low=None,
                         target_band_high=None)
    card = build_thesis_card(row, pos, role="", entry_reason="")
    d = _card_to_dict(card)
    assert d["advisory_gaps"] == ["top_holdings_broker_thin"]
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -k "to_dict" -x
```
Expected: 2 failures — `KeyError: 'advisory_gaps'` (the dict has no such key yet).

- [ ] **Step 3: Add `advisory_gaps` to `_row_to_dict`**

In `src/irc/opportunity/report.py` line 17–41, change the dict to include `"advisory_gaps": list(row.advisory_gaps),` immediately after `"expected_omissions": list(row.expected_omissions),`:

```python
def _row_to_dict(row: OpportunityRow) -> dict[str, Any]:
    return {
        "instrument_id": row.instrument_id,
        "name_cn": row.name_cn,
        "asset_class": row.asset_class,
        "theme": row.theme,
        "lookthrough_target": row.lookthrough_target.display_cn,
        "lookthrough_kind": row.lookthrough_target.kind,
        "lookthrough_key": row.lookthrough_target.key,
        "valuation_state": row.valuation_state,
        "heat_state": row.heat_state,
        "thesis_state": row.thesis_state,
        "product_quality_state": row.product_quality_state,
        "opportunity_state": row.opportunity_state,
        "opportunity_reason": row.opportunity_reason,
        "evidence_gaps": list(row.evidence_gaps),
        "expected_omissions": list(row.expected_omissions),
        "advisory_gaps": list(row.advisory_gaps),
        # New schema (item 002):
        "thesis_evidence": [asdict(e) for e in row.thesis_evidence],
        "contributing_dimensions": sorted(row.contributing_dimensions),
        "constituent_analyses": [
            asdict(c) for c in getattr(row, "constituent_analyses", ())
        ],
        "fetch_types_attempted": list(row.fetch_types_attempted),
    }
```

- [ ] **Step 4: Add `advisory_gaps` to `_card_to_dict`**

In `src/irc/opportunity/report.py` lines 63–83, update the for-loop tuple to include `"advisory_gaps"`:

Replace:
```python
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions"):
        d[key] = list(d.get(key, []))
```

with:

```python
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions", "advisory_gaps"):
        d[key] = list(d.get(key, []))
```

- [ ] **Step 5: Propagate `advisory_gaps` in `build_thesis_card`**

In `src/irc/opportunity/cards.py` line 41–64, add `advisory_gaps=row.advisory_gaps,` after `expected_omissions=row.expected_omissions,`:

```python
    return ThesisCard(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        role=role,
        lookthrough_target=row.lookthrough_target.display_cn,
        entry_reason=entry_reason,
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        falsification_triggers=_FALSIFICATION_TRIGGERS,
        trim_triggers=_TRIM_TRIGGERS,
        do_not_sell_just_because=_DO_NOT_SELL_JUST_BECAUSE,
        review_cadence=review_cadence,
        evidence_gaps=row.evidence_gaps,
        thesis_evidence=row.thesis_evidence,
        expected_omissions=row.expected_omissions,
        advisory_gaps=row.advisory_gaps,
        constituent_analyses=row.constituent_analyses,
    )
```

- [ ] **Step 6: Run the new tests and verify they pass**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -x
```
Expected: `7 passed` (5 existing + 2 new).

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/report.py src/irc/opportunity/cards.py tests/opportunity/test_top_holdings_broker_thin.py
git commit -m "feat(opportunity): serialize advisory_gaps in report + cards"
```

---

## Task 6: Discipline report header suffix (`AC9`)

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Test: `tests/opportunity/test_top_holdings_broker_thin.py` (extend)

- [ ] **Step 1: Write failing test for the discipline header suffix**

Append to `tests/opportunity/test_top_holdings_broker_thin.py`:

```python
def test_discipline_section_header_appends_advisory_gap_suffix():
    """AC9: the `## 今日可定投` per-fund line gains a 证据缺口 suffix when the
    row carries top_holdings_broker_thin. Append-only — does not perturb
    existing column positions.
    """
    from irc.opportunity.report import _render_section
    from irc.opportunity.types import DisciplineRow
    drow = DisciplineRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", note_cn="证据偏薄",
        advisory_gaps=("top_holdings_broker_thin",),
    )
    rendered = _render_section("今日可定投", [drow])
    assert "证据缺口：核心持仓券商覆盖不足" in rendered
    # Suffix appears AFTER asset state markers but BEFORE note_cn.
    assert rendered.index("证据缺口：核心持仓券商覆盖不足") < rendered.index("证据偏薄")


def test_discipline_section_header_no_suffix_when_advisory_gaps_empty():
    from irc.opportunity.report import _render_section
    from irc.opportunity.types import DisciplineRow
    drow = DisciplineRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="买入候选",
    )
    rendered = _render_section("今日可定投", [drow])
    assert "证据缺口" not in rendered
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -k "discipline_section_header" -x
```
Expected: first test fails — string not found.

- [ ] **Step 3: Extend `_render_section` in `report.py`**

In `src/irc/opportunity/report.py` lines 214–231, replace `_render_section`:

```python
def _render_section(title: str, rows: list[DisciplineRow]) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action} "
            f"｜ {r.note_cn}"
        )
        # Item 007 D3a: nested thesis_evidence bullets (top-3 via select_citations).
        lines.extend(_render_thesis_evidence_bullets(r.thesis_evidence))
        # Item 007 D3b: inline top-5 holdings for active-fund rows.
        lines.extend(_render_inline_holdings_block(
            getattr(r, "constituent_analyses", ()),
        ))
    lines.append("")
    return "\n".join(lines)
```

with:

```python
def _render_section(title: str, rows: list[DisciplineRow]) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        advisory_suffix = (
            " ｜ 证据缺口：核心持仓券商覆盖不足"
            if "top_holdings_broker_thin" in getattr(r, "advisory_gaps", ())
            else ""
        )
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action}"
            f"{advisory_suffix} "
            f"｜ {r.note_cn}"
        )
        # Item 007 D3a: nested thesis_evidence bullets (top-3 via select_citations).
        lines.extend(_render_thesis_evidence_bullets(r.thesis_evidence))
        # Item 007 D3b: inline top-5 holdings for active-fund rows.
        lines.extend(_render_inline_holdings_block(
            getattr(r, "constituent_analyses", ()),
        ))
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the new tests and verify they pass**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -k "discipline_section_header" -x
```
Expected: `2 passed`.

- [ ] **Step 5: Run the full opportunity test suite to confirm no regression**

```bash
uv run pytest tests/opportunity/ -x
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_top_holdings_broker_thin.py
git commit -m "feat(opportunity): append 证据缺口 suffix to discipline header on top_holdings_broker_thin"
```

---

## Task 7: `PickRow.advisory_gaps` field + memo_cmd populates it

**Files:**
- Modify: `src/irc/memo/picks_table.py`
- Modify: `src/irc/commands/memo_cmd.py`
- Test: `tests/memo/test_picks_table_advisory_partition.py` (new)

- [ ] **Step 1: Write failing test for `PickRow.advisory_gaps` field**

Create `tests/memo/test_picks_table_advisory_partition.py`:

```python
"""Stable-partition test for §5 picks-table advisory demotion (AC8)."""
from __future__ import annotations

from irc.memo.picks_table import PickRow, render_picks_table


def _pick(iid: str, *, advisory: tuple[str, ...] = ()) -> PickRow:
    return PickRow(
        instrument_id=iid, name_cn=iid, asset_class="cn_equity_fund",
        role="alpha", target_weight=0.05, composite_score=70.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        advisory_gaps=advisory,
    )


def test_pickrow_default_advisory_gaps_is_empty_tuple():
    row = _pick("005827")
    assert row.advisory_gaps == ()


def test_pickrow_accepts_advisory_gaps_keyword():
    row = _pick("005827", advisory=("top_holdings_broker_thin",))
    assert row.advisory_gaps == ("top_holdings_broker_thin",)
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/memo/test_picks_table_advisory_partition.py -x
```
Expected: failures — `TypeError: __init__() got an unexpected keyword argument 'advisory_gaps'`.

- [ ] **Step 3: Add the field to `PickRow`**

In `src/irc/memo/picks_table.py` lines 53–75, append the field:

```python
@dataclass(frozen=True)
class PickRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    role: str
    target_weight: float
    composite_score: float
    opportunity_state: str
    dca_action: str
    risk_action: str
    one_line_reason: str
    valuation_state: str = ""
    venue_note: str = ""
    citations: tuple[ThesisEvidence, ...] = field(default_factory=tuple)
    decision_status: str = "watch_only"
    tranche_cap_pct: float | None = None
    trigger_status: str = ""
    advisory_gaps: tuple[str, ...] = ()
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
uv run pytest tests/memo/test_picks_table_advisory_partition.py -x
```
Expected: `2 passed`.

- [ ] **Step 5: Write the failing stable-partition test**

Append to `tests/memo/test_picks_table_advisory_partition.py`:

```python
def test_stable_partition_demotes_advisory_rows_to_tail():
    """AC8: a stable partition over pick_rows puts non-advisory rows first.

    Trade-plan iteration order is preserved within each partition.
    """
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [
        _pick("A"),  # non-advisory
        _pick("B", advisory=("top_holdings_broker_thin",)),  # advisory
        _pick("C"),  # non-advisory
        _pick("D", advisory=("top_holdings_broker_thin",)),  # advisory
    ]
    partitioned = _apply_advisory_partition(rows)
    assert [r.instrument_id for r in partitioned] == ["A", "C", "B", "D"]


def test_stable_partition_preserves_order_when_no_advisory():
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [_pick("A"), _pick("B"), _pick("C")]
    partitioned = _apply_advisory_partition(rows)
    assert [r.instrument_id for r in partitioned] == ["A", "B", "C"]


def test_stable_partition_preserves_order_when_all_advisory():
    from irc.commands.memo_cmd import _apply_advisory_partition

    rows = [
        _pick("A", advisory=("top_holdings_broker_thin",)),
        _pick("B", advisory=("top_holdings_broker_thin",)),
    ]
    partitioned = _apply_advisory_partition(rows)
    assert [r.instrument_id for r in partitioned] == ["A", "B"]
```

- [ ] **Step 6: Run the tests and verify they fail**

```bash
uv run pytest tests/memo/test_picks_table_advisory_partition.py -k "stable_partition" -x
```
Expected: 3 failures — `_apply_advisory_partition` is not defined.

- [ ] **Step 7: Implement `_apply_advisory_partition` + populate `advisory_gaps` in `_build_pick_rows`**

In `src/irc/commands/memo_cmd.py`, near the existing pure helpers (just before `_build_pick_rows` at line 501), add:

```python
def _apply_advisory_partition(pick_rows: list[PickRow]) -> list[PickRow]:
    """Stable partition: rows without advisory_gaps first, then rows with.

    Trade-plan iteration order is preserved within each partition (AC8). Pure.
    """
    non_advisory = [r for r in pick_rows if not r.advisory_gaps]
    advisory = [r for r in pick_rows if r.advisory_gaps]
    return non_advisory + advisory
```

In `_build_pick_rows` at line 577–594, add `advisory_gaps` to the `PickRow(...)` kwargs (after `trigger_status=trigger_status,`):

```python
        pick_rows.append(PickRow(
            instrument_id=iid_raw,
            name_cn=name,
            asset_class=op.get("asset_class") or t.get("asset_class", ""),
            role=t.get("role") or "",
            target_weight=target_weight,
            composite_score=float(score),
            opportunity_state=opp_state,
            dca_action=dca,
            risk_action="none",
            one_line_reason=reason,
            valuation_state=op.get("valuation_state", ""),
            venue_note=str(t.get("venue_note", "")),
            citations=citations,
            decision_status=decision_status,
            tranche_cap_pct=tranche_cap_pct,
            trigger_status=trigger_status,
            advisory_gaps=tuple(op.get("advisory_gaps") or ()),
        ))
```

In `run_memo` at line 646–652, apply the partition after `_build_pick_rows`:

```python
    pick_rows, absent_targets, gapped_targets = _build_pick_rows(
        trades, opportunity, scoring, fallback_names,
        qdii_max_premium_pct=_qdii_max,
        build_mode=build_mode,
        macro_snapshot=macro_snapshot,
        weekly_return_by_id=weekly_return_by_id,
    )
    pick_rows = _apply_advisory_partition(pick_rows)
```

- [ ] **Step 8: Run the tests and verify they pass**

```bash
uv run pytest tests/memo/test_picks_table_advisory_partition.py -x
```
Expected: `5 passed`.

- [ ] **Step 9: Commit**

```bash
git add src/irc/memo/picks_table.py src/irc/commands/memo_cmd.py tests/memo/test_picks_table_advisory_partition.py
git commit -m "feat(memo): PickRow.advisory_gaps + stable partition demotes broker-thin picks"
```

---

## Task 8: §6 风险提示 marker block + synthesizer lock (`AC7`)

**Files:**
- Modify: `src/irc/memo/template.py`
- Modify: `src/irc/commands/memo_cmd.py`
- Modify: `src/irc/memo/synthesizer.py`
- Test: `tests/memo/test_evidence_gap_risk_note.py` (new)

- [ ] **Step 1: Write failing tests for the §6 marker block**

Create `tests/memo/test_evidence_gap_risk_note.py`:

```python
"""AC7: memo §6 风险提示 emits a deterministic 证据缺口 bullet inside
<!-- IRC_EVIDENCE_GAP_BEGIN/END --> markers when ≥1 pick carries
top_holdings_broker_thin."""
from __future__ import annotations

from irc.memo.picks_table import PickRow


def _pick(iid: str, name: str, *, advisory: tuple[str, ...] = ()) -> PickRow:
    return PickRow(
        instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
        role="alpha", target_weight=0.05, composite_score=70.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        advisory_gaps=advisory,
    )


def test_compose_evidence_gap_lines_returns_empty_when_no_qualifying_picks():
    from irc.commands.memo_cmd import _compose_evidence_gap_lines
    rows = [_pick("A", "甲"), _pick("B", "乙")]
    assert _compose_evidence_gap_lines(rows) == ()


def test_compose_evidence_gap_lines_emits_marker_block_when_one_pick_qualifies():
    from irc.commands.memo_cmd import _compose_evidence_gap_lines
    rows = [
        _pick("005827", "易方达蓝筹精选", advisory=("top_holdings_broker_thin",)),
        _pick("510300", "沪深300ETF"),
    ]
    lines = _compose_evidence_gap_lines(rows)
    assert lines
    joined = "\n".join(lines)
    assert "<!-- IRC_EVIDENCE_GAP_BEGIN -->" in joined
    assert "<!-- IRC_EVIDENCE_GAP_END -->" in joined
    assert "证据缺口（Top-5 经纪覆盖不足）" in joined
    assert "005827 易方达蓝筹精选" in joined
    # 510300 must NOT appear (it does not carry the advisory gap).
    assert "510300" not in joined


def test_compose_evidence_gap_lines_sorts_picks_by_instrument_id_ascending():
    from irc.commands.memo_cmd import _compose_evidence_gap_lines
    rows = [
        _pick("510300", "B", advisory=("top_holdings_broker_thin",)),
        _pick("005827", "A", advisory=("top_holdings_broker_thin",)),
    ]
    lines = _compose_evidence_gap_lines(rows)
    joined = "\n".join(lines)
    # 005827 must appear before 510300 (ASCII sort, all-digit ids).
    assert joined.index("005827") < joined.index("510300")


def test_evidence_gap_lines_render_through_skeleton_into_section_6():
    """Integration: a non-empty evidence_gap_lines tuple flows through
    `MemoInputs.risk_notes` (prepended) and renders inside §6."""
    from irc.memo.template import MemoInputs, render_skeleton
    inputs = MemoInputs(
        date_str="2026-05-27", gold_regime="—", gold_zone="—", gold_tilt="—",
        allocation_mode="build", macro_summary="—", top_picks=(),
        risk_notes=(
            "<!-- IRC_EVIDENCE_GAP_BEGIN -->",
            "证据缺口（Top-5 经纪覆盖不足）：005827 易方达蓝筹精选。",
            "<!-- IRC_EVIDENCE_GAP_END -->",
            "其他风险条目。",
        ),
        tldr_lines=(),
    )
    md = render_skeleton(inputs)
    # The marker block + the regular risk note both appear in §6.
    assert "## 6. 风险提示" in md
    assert "<!-- IRC_EVIDENCE_GAP_BEGIN -->" in md
    assert "其他风险条目" in md
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
uv run pytest tests/memo/test_evidence_gap_risk_note.py -x
```
Expected: 4 failures — `_compose_evidence_gap_lines` is not defined.

- [ ] **Step 3: Add marker constants to `template.py`**

In `src/irc/memo/template.py` after line 37 (after `PICKS_SECTION_MARKER_END`), add:

```python
EVIDENCE_GAP_MARKER_BEGIN = "<!-- IRC_EVIDENCE_GAP_BEGIN -->"
EVIDENCE_GAP_MARKER_END = "<!-- IRC_EVIDENCE_GAP_END -->"
```

- [ ] **Step 4: Add `_compose_evidence_gap_lines` to `memo_cmd.py`**

In `src/irc/commands/memo_cmd.py` after `_compose_risk_notes` (after line 233), add:

```python
def _compose_evidence_gap_lines(pick_rows: list[PickRow]) -> tuple[str, ...]:
    """Compose the §6 risk-notes 证据缺口 marker block (AC7).

    When ≥1 pick row carries `top_holdings_broker_thin` in its `advisory_gaps`,
    emit a deterministic 3-line tuple wrapped in IRC_EVIDENCE_GAP_BEGIN/END
    markers. Picks sorted by `instrument_id` ASC.

    Empty result when no row qualifies — no markers emitted. Pure.
    """
    from irc.memo.template import EVIDENCE_GAP_MARKER_BEGIN, EVIDENCE_GAP_MARKER_END

    affected = sorted(
        (r for r in pick_rows if "top_holdings_broker_thin" in r.advisory_gaps),
        key=lambda r: r.instrument_id,
    )
    if not affected:
        return ()
    targets_str = "、".join(f"{r.instrument_id} {r.name_cn}" for r in affected)
    body = (
        "证据缺口（Top-5 经纪覆盖不足）：以下候选标的的核心持仓中至少 2 只"
        "（或合计权重 ≥ 20%）缺少券商研报覆盖，证据强度弱于其余候选，"
        f"触发条件成立时建议优先选择证据更完整的标的：{targets_str}。"
    )
    return (EVIDENCE_GAP_MARKER_BEGIN, body, EVIDENCE_GAP_MARKER_END)
```

- [ ] **Step 5: Run the pure-helper tests**

```bash
uv run pytest tests/memo/test_evidence_gap_risk_note.py -k "compose_evidence_gap_lines or sorts" -x
```
Expected: `3 passed`.

- [ ] **Step 6: Wire `_compose_evidence_gap_lines` into `run_memo`**

In `src/irc/commands/memo_cmd.py` line 724 (just after `risk_notes = _compose_risk_notes(cutoff)`), add the prepend:

Replace the block at lines 724–746:

```python
    cutoff = extract_evidence_cutoff(raw_ref_pool)
    risk_notes = _compose_risk_notes(cutoff)
    # Deterministic diagnostics injected into risk_notes so the LLM can't
    # omit them and the audit gate can verify presence
    # (adversarial-review items 013, 014).
    cash_target_center = float(
        getattr(bundle.preferences.asset_class_targets.get("cash", None), "center", 0.05) or 0.05
    )
    drift_lines = compose_execution_drift_lines(alloc, cash_target_center)
    if drift_lines:
        risk_notes = tuple(drift_lines) + risk_notes
    usd_tol_pair: tuple[float, float] | None = None
    _usd_tol = getattr(bundle.preferences.currency_tolerance, "usd", None)
    if _usd_tol and len(_usd_tol) >= 2:
        usd_tol_pair = (float(_usd_tol[0]), float(_usd_tol[1]))
    fx_policy = getattr(getattr(bundle.preferences, "fx_hedge", None), "policy", None)
    fx_lines = compose_fx_qdii_lines(alloc, usd_tol_pair, fx_hedge_policy=fx_policy)
    if fx_lines:
        risk_notes = tuple(fx_lines) + risk_notes
    # Role-bucket banner (item 010): adversarial review §E.
    diag_rows = _load_discovery_diagnostics(out_today)
    role_lines = compose_role_bucket_banner(diag_rows)
    if role_lines:
        risk_notes = tuple(role_lines) + risk_notes
```

with:

```python
    cutoff = extract_evidence_cutoff(raw_ref_pool)
    risk_notes = _compose_risk_notes(cutoff)
    # Deterministic diagnostics injected into risk_notes so the LLM can't
    # omit them and the audit gate can verify presence
    # (adversarial-review items 013, 014).
    cash_target_center = float(
        getattr(bundle.preferences.asset_class_targets.get("cash", None), "center", 0.05) or 0.05
    )
    drift_lines = compose_execution_drift_lines(alloc, cash_target_center)
    if drift_lines:
        risk_notes = tuple(drift_lines) + risk_notes
    usd_tol_pair: tuple[float, float] | None = None
    _usd_tol = getattr(bundle.preferences.currency_tolerance, "usd", None)
    if _usd_tol and len(_usd_tol) >= 2:
        usd_tol_pair = (float(_usd_tol[0]), float(_usd_tol[1]))
    fx_policy = getattr(getattr(bundle.preferences, "fx_hedge", None), "policy", None)
    fx_lines = compose_fx_qdii_lines(alloc, usd_tol_pair, fx_hedge_policy=fx_policy)
    if fx_lines:
        risk_notes = tuple(fx_lines) + risk_notes
    # Role-bucket banner (item 010): adversarial review §E.
    diag_rows = _load_discovery_diagnostics(out_today)
    role_lines = compose_role_bucket_banner(diag_rows)
    if role_lines:
        risk_notes = tuple(role_lines) + risk_notes
    # ADR 0005 + Item 001 (instrument-pickability): top_holdings_broker_thin
    # advisory marker block. Prepended last so it renders FIRST in §6.
    evidence_gap_lines = _compose_evidence_gap_lines(pick_rows)
    if evidence_gap_lines:
        risk_notes = tuple(evidence_gap_lines) + risk_notes
```

- [ ] **Step 7: Run the integration test that exercises `render_skeleton`**

```bash
uv run pytest tests/memo/test_evidence_gap_risk_note.py -x
```
Expected: `4 passed`.

- [ ] **Step 8: Add the synthesizer verbatim-lock instruction**

In `src/irc/memo/synthesizer.py` after the §5 picks-table lock block (line 127–133), add a new block:

```python
    # ADR 0005 lock for the §6 advisory-gap marker block.
    if "<!-- IRC_EVIDENCE_GAP_BEGIN -->" in skeleton:
        locked_section_lines.append(
            "第6节『风险提示』在 IRC_EVIDENCE_GAP_BEGIN/END 标记之间的 bullet 必须**原样保留**："
            "该 bullet 由系统根据 Top-5 持仓券商覆盖证据自动生成，禁止改写、合并、"
            "新增或删除其中的任何条目，亦禁止改写其中的标的代码与名称。"
        )
```

- [ ] **Step 9: Run the memo test suite to confirm no regression**

```bash
uv run pytest tests/memo/ -x
```
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add src/irc/memo/template.py src/irc/commands/memo_cmd.py src/irc/memo/synthesizer.py tests/memo/test_evidence_gap_risk_note.py
git commit -m "feat(memo): emit §6 证据缺口 marker block when picks carry top_holdings_broker_thin"
```

---

## Task 9: SAME-3 / citation-gate invariant proof (AC10–AC11)

**Files:**
- Test: `tests/opportunity/test_top_holdings_broker_thin.py` (extend)

- [ ] **Step 1: Write the SAME-3 / citation-shape invariance test**

Append to `tests/opportunity/test_top_holdings_broker_thin.py`:

```python
def test_advisory_gap_does_not_add_to_thesis_evidence():
    """AC10 + AC11: the new gap MUST NOT contribute to thesis_evidence,
    citation_id format, or the data/information leg shape."""
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput, ThesisEvidence

    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a",
        date="2026-04-15", summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=6.2,
    )
    analyses = (
        ConstituentAnalysis(
            symbol="A", name_cn="A", weight_pct=8.0,
            evidence=(ev,), failure_reasons=("broker_empty:A",),
            one_line_view="",
        ),
        ConstituentAnalysis(
            symbol="B", name_cn="B", weight_pct=7.0,
            evidence=(), failure_reasons=("broker_empty:B",),
            one_line_view="",
        ),
    )
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2026Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    # The advisory gap is set:
    assert "top_holdings_broker_thin" in row.advisory_gaps
    # ...and thesis_evidence remains exactly the original constituent evidence:
    assert row.thesis_evidence == (ev,)
```

- [ ] **Step 2: Run the new test and verify it passes (the field plumbing from Tasks 4-5 already makes this true)**

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py -k "does_not_add_to_thesis_evidence" -x
```
Expected: `1 passed`. (This is a lockdown — it should pass on the current implementation; the test exists to prevent future drift.)

- [ ] **Step 3: Commit**

```bash
git add tests/opportunity/test_top_holdings_broker_thin.py
git commit -m "test(opportunity): lock SAME-3 invariance for advisory_gaps"
```

---

## Task 10: Determinism / two-run byte equality + existing lockdown (AC12)

**Files:**
- Read: `tests/integration/test_publishable_set_lockdown.py` (no edits expected — the existing two-run byte-equality test should absorb the change automatically once the helpers are deterministic)

- [ ] **Step 1: Run the publishable-set lockdown to verify it still passes**

```bash
uv run pytest tests/integration/test_publishable_set_lockdown.py -x
```
Expected: all green. The lockdown writes outputs from scratch each run and compares two consecutive runs — since our additions are deterministic (helpers are pure, sorted ASC, no time/random), byte equality should hold.

If a failure surfaces (e.g. a key-order change in `_row_to_dict`), inspect the diff and adjust ordering — `advisory_gaps` was inserted in a stable position (right after `expected_omissions`), so insertion order matches dict-literal order in CPython 3.7+ and JSON serialization is deterministic.

- [ ] **Step 2: Run the entire unit + integration suite**

```bash
uv run pytest -x
```
Expected: all green. If anything fails, fix the root cause before continuing.

- [ ] **Step 3: Commit (only if any fixes were required)**

If no edits were needed, skip this commit. Otherwise:

```bash
git add <fixed files>
git commit -m "fix(memo|opportunity): preserve byte-equality lockdown after advisory_gaps wiring"
```

---

## Task 11: End-to-end verification on cached evidence

**Files:**
- No file edits — this is a smoke run against today's date partition.

- [ ] **Step 1: Re-run the opportunity + memo stages on cached evidence**

```bash
uv run irc run --from opportunity
```
Expected: pipeline completes; `outputs/2026-05-27/opportunity_report.json` and `outputs/2026-05-27/memo.md` (or whatever today's partition is) are regenerated.

If `uv run irc run --from opportunity` reports the cache is stale or no input data exists, run instead:

```bash
uv run irc opportunity
uv run irc decision
```

(The exact CLI surface to invoke is captured in `CLAUDE.md` under "Commands"; the goal is to land at a regenerated `opportunity_report.json` + `memo.md` in today's partition.)

- [ ] **Step 2: Inspect today's `opportunity_report.json` for the new field**

```bash
python -c "import json,sys; r=json.load(open('outputs/2026-05-27/opportunity_report.json')); print([row['instrument_id'] for row in r['rows'] if row.get('advisory_gaps')])"
```
Expected: either an empty list (no fund's cached evidence trips the threshold today) OR a list of `instrument_id`s — both outcomes are valid. The KEY signal is the `advisory_gaps` key is present on every row.

- [ ] **Step 3: Inspect today's `memo.md` §6 风险提示**

```bash
grep -n "IRC_EVIDENCE_GAP\|证据缺口" outputs/2026-05-27/memo.md
```
Expected: if Step 2 returned a non-empty list, the marker block + 证据缺口 bullet appear inside §6. If Step 2 returned an empty list, no marker block is emitted (correct empty-case behaviour per AC7).

- [ ] **Step 4: Two-run byte-equality smoke check**

```bash
cp outputs/2026-05-27/memo.md /tmp/memo_run1.md
uv run irc run --only memo
diff /tmp/memo_run1.md outputs/2026-05-27/memo.md
```
Expected: empty diff (byte-identical between two consecutive `irc run --only memo` runs).

Caveat: if `irc run --only memo` re-calls the LLM, the deterministic surfaces (picks table, §2 macro pillar, §3 gold evidence, §6 evidence-gap marker, §7 execution lines) MUST be byte-identical between runs. Variations in LLM-generated prose outside markers are expected and acceptable — the test is for the locked surfaces only.

- [ ] **Step 5: Final commit (only if any minor renderer drift surfaces)**

If everything checks out (the common case), no commit is needed for this task — Tasks 1–10 already delivered all behavior. If the smoke run surfaced any tiny issue, fix and commit before declaring done.

---

## Self-Review (already applied during plan authoring)

**1. Spec coverage check:**
- AC1 (gap code) → Task 2 (helper module + ADVISORY_GAP_CODES).
- AC2 (emitter is `derive_thesis_from_evidence`) → Task 4.
- AC3 (threshold ≥2 OR ≥20%) → Task 2.
- AC4 (active-fund only) → Task 4 (`test_fund_level_snapshot_never_emits_advisory_gap`).
- AC5 (foreign-heavy interaction) → emergent — both Rule 2.5 acceptance and the advisory gap coexist; covered structurally because `derive_thesis_from_evidence` emits BEFORE Policy B runs.
- AC6 (H3 preserved) → Task 3 (`_partition_gaps` 3-way) + Task 4 (`test_advisory_gap_goes_to_advisory_gaps_not_evidence_gaps`).
- AC7 (§6 marker block) → Task 8.
- AC8 (stable partition) → Task 7.
- AC9 (discipline header suffix) → Task 6.
- AC10 (SAME-3 unchanged) → Task 9.
- AC11 (citation gate v1 unchanged) → Task 9 (same test covers shape invariance).
- AC12 (two-run byte equality) → Task 10.
- AC13 (TDD) → enforced by every Task ordering: red test first, then green code.

**2. Placeholder scan:** No "TBD", no "TODO", no placeholders. Every code block is complete.

**3. Type consistency:** `advisory_gaps: tuple[str, ...]` used uniformly across `OpportunityRow`, `ThesisCard`, `DisciplineRow`, `PickRow`. `_partition_gaps` signature change is propagated to its single caller. `_compose_evidence_gap_lines` returns `tuple[str, ...]` (matching the existing diagnostic-helper convention in `diagnostics.py`).

---

## Judgment calls made during planning

- **Spec AC9 / §"Foreign-heavy interaction"** is covered as an emergent property of the architecture rather than its own task — Policy B and `derive_thesis_from_evidence` are already orthogonal in the existing pipeline, so adding the gap to the latter does not perturb the former. No new explicit test is added (the existing `tests/opportunity/test_policy_b.py` rule-2.5 tests still pass; combined coverage is implicit).
- **Step 5 of Task 10 / Two-run byte equality smoke check** is best-effort. The existing lockdown integration test (`tests/integration/test_publishable_set_lockdown.py`) is the canonical assertion; the smoke step is operational confirmation only.
- **`compose_role_bucket_banner` / `compose_fx_qdii_lines` ordering** with the new `evidence_gap_lines`: the spec says "deterministic" but not where the marker block lands within `risk_notes`. Choice made: prepended LAST (so it renders FIRST in §6 — most prominent placement). The spec wording "prepends a deterministic bullet" supports this.
