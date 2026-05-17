# Item 005 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/005-spec.md`. Base branch: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-005-evidence-gaps-cleanup`.

**Goal:** `constituent_not_applicable` for non-indexable asset classes (`gold`, `cn_bond_fund`, `cn_equity_fund`) goes into a new `expected_omissions` field on `OpportunityRow`/`ThesisCard` instead of polluting `evidence_gaps`.

**Architecture:** Add a small partition step that runs once at the boundary where `evidence_gaps` is assigned to the row. Avoids modifying the existing `derive_thesis_from_evidence` / `_classify_constituent_gap` return signatures (those are reused elsewhere).

---

## Task 1: Add `expected_omissions` field to the two dataclasses

**Files:** `src/irc/opportunity/types.py:105-143`

### Step 1.1: Write the failing test
- [ ] Add to `tests/opportunity/test_types.py` (create file if absent):

```python
from irc.opportunity.types import OpportunityRow, ThesisCard, LookthroughTarget


def _row(**over):
    base = dict(
        instrument_id="X", name_cn="X", asset_class="gold", theme=None,
        lookthrough_target=LookthroughTarget(kind="index", key="GOLD", display_cn="GOLD"),
        valuation_state="neutral", heat_state="neutral", thesis_state="evidence_insufficient",
        product_quality_state="ok", opportunity_state="small_watch", opportunity_reason="r",
        evidence_gaps=(),
    )
    base.update(over)
    return OpportunityRow(**base)


def test_opportunity_row_has_expected_omissions_default_empty():
    r = _row()
    assert r.expected_omissions == ()


def test_opportunity_row_accepts_expected_omissions_kwarg():
    r = _row(expected_omissions=("constituent_not_applicable",))
    assert r.expected_omissions == ("constituent_not_applicable",)
```

### Step 1.2: Run test
- [ ] Run: `pytest tests/opportunity/test_types.py -v`
- [ ] Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'expected_omissions'`

### Step 1.3: Add the field to both dataclasses
- [ ] In `src/irc/opportunity/types.py`, change the `OpportunityRow` class (lines 105-119):

```python
@dataclass(frozen=True)
class OpportunityRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    lookthrough_target: LookthroughTarget
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    opportunity_reason: str
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()
```

And `ThesisCard` (lines 122-143):

```python
@dataclass(frozen=True)
class ThesisCard:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    role: str
    lookthrough_target: str
    entry_reason: str
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    falsification_triggers: tuple[str, ...]
    trim_triggers: tuple[str, ...]
    do_not_sell_just_because: tuple[str, ...]
    review_cadence: str
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()
```

### Step 1.4: Run test, verify pass
- [ ] Run: `pytest tests/opportunity/test_types.py -v`
- [ ] Expected: PASS.

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/opportunity/types.py tests/opportunity/test_types.py
git commit -m "feat(opportunity): add expected_omissions field to OpportunityRow and ThesisCard"
```

---

## Task 2: Partition `constituent_not_applicable` into `expected_omissions`

**Files:** `src/irc/opportunity/states.py:325-326`, `src/irc/opportunity/cards.py:60` (where ThesisCard is built)

### Step 2.1: Write the failing test
- [ ] Add to `tests/opportunity/test_states.py` (or create `test_evidence_gaps_partition.py`):

```python
from irc.opportunity.states import build_opportunity_row, EXPECTED_OMISSION_CODES
from irc.opportunity.types import OpportunityInput


def _gold_input(**over):
    base = dict(
        instrument_id="518880", name_cn="黄金ETF", asset_class="gold",
        theme=None, venue_compatible=True,
        expense_ratio=0.005, aum_cny=1e10,
        # ... add whatever else the dataclass requires; use defaults where allowed
    )
    base.update(over)
    return OpportunityInput(**base)


def test_constituent_not_applicable_lives_in_expected_omissions_for_gold():
    inp = _gold_input()
    row = build_opportunity_row(inp, theme_thesis=None, snapshot=None, theme_report=None)
    assert "constituent_not_applicable" not in row.evidence_gaps
    assert "constituent_not_applicable" in row.expected_omissions


def test_real_gaps_stay_in_evidence_gaps_for_indexable_asset_class():
    inp = _gold_input(asset_class="cn_etf", theme="broad")  # indexable
    row = build_opportunity_row(inp, theme_thesis=None, snapshot=None, theme_report=None)
    # For an indexable asset_class with no snapshot, 'constituent_missing' is a real gap
    assert "constituent_not_applicable" not in row.expected_omissions
    assert "constituent_not_applicable" not in row.evidence_gaps


def test_expected_omission_codes_constant_documented():
    assert "constituent_not_applicable" in EXPECTED_OMISSION_CODES
```

> The `OpportunityInput` constructor will need fields not shown here — when implementing, read `src/irc/opportunity/types.py` to find the required fields and fill them with minimal sentinel values. If a particular field has no clear sentinel, ask before guessing.

### Step 2.2: Run tests
- [ ] Run: `pytest tests/opportunity/test_states.py -k "expected_omissions or expected_omission" -v`
- [ ] Expected: FAILs — `EXPECTED_OMISSION_CODES` not defined.

### Step 2.3: Add the partition logic in `states.py`
- [ ] In `src/irc/opportunity/states.py`, near the top (after imports, before `_structural_evidence_gaps`):

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

### Step 2.4: Wire the partition into `build_opportunity_row`
- [ ] In `src/irc/opportunity/states.py:325-326`, change:

```python
        evidence_gaps=tuple(structural_gaps + list(thesis_gaps)),
```

to:

```python
        evidence_gaps=evidence_gaps_filtered,
        expected_omissions=expected_omissions,
```

and, just before the `return OpportunityRow(`, compute the two:

```python
    combined_gaps = tuple(structural_gaps) + tuple(thesis_gaps)
    evidence_gaps_filtered, expected_omissions = _partition_gaps(combined_gaps)
```

### Step 2.5: Run tests, verify pass
- [ ] Run: `pytest tests/opportunity/test_states.py -k "expected_omission" -v`
- [ ] Expected: PASS.
- [ ] Run: `pytest tests/opportunity/ -v`
- [ ] Expected: all opportunity tests still PASS.

### Step 2.6: Mirror the partition in `cards.py`
- [ ] Read `src/irc/opportunity/cards.py` to find where `ThesisCard` is built from an `OpportunityRow`. The line currently is `evidence_gaps=row.evidence_gaps`; add a matching `expected_omissions=row.expected_omissions` line. Because the row already carries both fields (Task 2.4), the card just forwards.

### Step 2.7: Run all opportunity tests
- [ ] Run: `pytest tests/opportunity/ -v`
- [ ] Expected: all PASS.

### Step 2.8: Commit
- [ ] Run:

```bash
git add src/irc/opportunity/states.py src/irc/opportunity/cards.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): partition constituent_not_applicable into expected_omissions"
```

---

## Task 3: Serialize `expected_omissions` in the opportunity report

**Files:** `src/irc/opportunity/report.py:15-31`

### Step 3.1: Write the failing test
- [ ] Add to `tests/opportunity/test_report.py`:

```python
from irc.opportunity.report import _row_to_dict
from irc.opportunity.types import OpportunityRow, LookthroughTarget


def test_row_to_dict_includes_expected_omissions():
    row = OpportunityRow(
        instrument_id="518880", name_cn="黄金ETF", asset_class="gold", theme=None,
        lookthrough_target=LookthroughTarget(kind="index", key="GOLD", display_cn="GOLD"),
        valuation_state="neutral", heat_state="neutral",
        thesis_state="evidence_insufficient", product_quality_state="ok",
        opportunity_state="small_watch", opportunity_reason="r",
        evidence_gaps=("missing_recent_news",),
        expected_omissions=("constituent_not_applicable",),
    )
    d = _row_to_dict(row)
    assert d["expected_omissions"] == ["constituent_not_applicable"]
    assert d["evidence_gaps"] == ["missing_recent_news"]
```

### Step 3.2: Run test
- [ ] Run: `pytest tests/opportunity/test_report.py::test_row_to_dict_includes_expected_omissions -v`
- [ ] Expected: FAIL — `KeyError: 'expected_omissions'`.

### Step 3.3: Add the field to `_row_to_dict`
- [ ] In `src/irc/opportunity/report.py`, append to the dict returned by `_row_to_dict` (line 30):

```python
        "evidence_gaps": list(row.evidence_gaps),
        "expected_omissions": list(row.expected_omissions),
```

- [ ] In `_card_to_dict` (line 53-58), extend the tuple-to-list normalization:

```python
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions"):
        d[key] = list(d.get(key, []))
```

### Step 3.4: Run tests
- [ ] Run: `pytest tests/opportunity/test_report.py -v`
- [ ] Expected: all PASS.

### Step 3.5: Run full opportunity suite for safety
- [ ] Run: `pytest tests/opportunity/ -v`
- [ ] Expected: all PASS.

### Step 3.6: Commit
- [ ] Run:

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_report.py
git commit -m "feat(opportunity): serialize expected_omissions in report and cards"
```

---

## Task 4: End-to-end smoke verification

**Files:** none (verification only)

### Step 4.1: Run the full opportunity test module
- [ ] Run: `pytest tests/opportunity/ -q`
- [ ] Expected: all PASS, no regressions.

### Step 4.2: Run the broader pre-merge suite
- [ ] Run: `pytest -q -x`
- [ ] Expected: all PASS. If anything unrelated fails, stop and report.

### Step 4.3: Run ruff
- [ ] Run: `ruff check src/irc/opportunity/ tests/opportunity/`
- [ ] Expected: no findings (or only pre-existing ones).
