# Item 001 plan — contributing-dimensions (Slice A0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Source spec:** `items/001-spec.md`
**Grill verdict:** PASS-WITH-EDITS — note new AC #6 requiring `isinstance(result, frozenset)` (`items/001-grill.md`)
**Branch:** to be created as `autodev/thesis-evidence-001-contributing-dimensions` off `autodev/thesis-cards-evidence-gap`

**Goal:** Add pure function `derive_contributing_dimensions(...) -> frozenset[str]` next to `compose_opportunity_state`, add matching `contributing_dimensions` field to `OpportunityRow`, and populate it from `build_opportunity_row`.

**Architecture:** New deterministic downstream reader over the four sub-states + composed `opportunity_state`. Inline if-chain mirrors `compose_opportunity_state` branches; `small_watch` priority mirrors `_weak_link_label` priority chain but returns dimension keys (not Chinese labels). No I/O, no mutation, no calls to `_weak_link_label`.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`.

---

## File structure

| File | Action | Responsibility |
| --- | --- | --- |
| `src/irc/opportunity/states.py` | Modify | Add `derive_contributing_dimensions` between `compose_opportunity_state` (ends line 343) and `_structural_evidence_gaps` (starts line 346); call it from `build_opportunity_row` after the existing `compose_opportunity_state(...)` call (line 409) and pass result into `OpportunityRow(...)` constructor. |
| `src/irc/opportunity/types.py` | Modify | Add trailing defaulted field `contributing_dimensions: frozenset[str] = field(default_factory=frozenset)` to `OpportunityRow` (line 117-132). |
| `tests/opportunity/test_states.py` | Modify | Append new tests at end of file (existing file already has 470+ lines but follows a flat import-then-test idiom; appending stays consistent and avoids a new test module). |

**Judgment call:** Spec §"Open questions for the planner" Q3 offered either appending to `test_states.py` or creating `test_contributing_dimensions.py`. Choosing append because (a) existing tests for `compose_opportunity_state` and `build_opportunity_row` are already there and the new tests share the same `_make` / `_make_full_input` helpers, (b) keeping branch-table enumeration next to the composer it mirrors aids reviewer navigation. Grill explicitly marks both as acceptable.

**Judgment call:** Spec §"Open questions for the planner" Q2 offered inline if-chain vs a private `_weak_link_dimension` helper mirroring `_weak_link_label`. Choosing inline because the chain is five lines, only one caller, and a helper would invite drift between the two priority orderings. Grill marks both as acceptable.

---

## Preflight (no code changes)

- [ ] **Step 1: Confirm branch + clean tree**

Run: `git status`
Expected: clean working tree on `autodev/thesis-evidence-001-contributing-dimensions` (created by the orchestrator before this plan executes). If branch missing, create it: `git checkout -b autodev/thesis-evidence-001-contributing-dimensions autodev/thesis-cards-evidence-gap`.

- [ ] **Step 2: Confirm baseline tests are green**

Run: `uv run pytest tests/opportunity/ -x -q`
Expected: all green. If red on `main`, stop and surface — this plan assumes a green baseline.

---

## Task 1 — Add failing test for `derive_contributing_dimensions`

**Files:**
- Modify: `tests/opportunity/test_states.py` (append at end of file)

- [ ] **Step 1: Append the parametrized branch-table test**

Add this block at the end of `tests/opportunity/test_states.py`:

```python
# ---------------------------------------------------------------------------
# derive_contributing_dimensions — branch-table enumeration (Slice A0)
# ---------------------------------------------------------------------------

from irc.opportunity.states import derive_contributing_dimensions


@pytest.mark.parametrize(
    "valuation,heat,thesis,product,opportunity_state,expected",
    [
        # exclude branch — thesis and/or product trigger
        ("cheap", "cold", "falsified", "acceptable", "exclude", frozenset({"thesis"})),
        ("cheap", "cold", "intact", "poor", "exclude", frozenset({"product_quality"})),
        ("cheap", "cold", "falsified", "poor", "exclude", frozenset({"thesis", "product_quality"})),
        # core_dca branch — all four dimensions are drivers
        (
            "cheap", "normal", "intact", "strong", "core_dca",
            frozenset({"valuation", "heat", "thesis", "product_quality"}),
        ),
        # pause_wait branch — subset of {valuation, heat}
        ("expensive", "normal", "intact", "acceptable", "pause_wait", frozenset({"valuation"})),
        ("cheap", "crowded", "intact", "acceptable", "pause_wait", frozenset({"heat"})),
        (
            "expensive", "overheated", "intact", "acceptable", "pause_wait",
            frozenset({"valuation", "heat"}),
        ),
        # small_watch branch — priority chain: product_quality → thesis → valuation → heat → conflict
        ("fair", "normal", "intact", "weak", "small_watch", frozenset({"product_quality"})),
        (
            "fair", "normal", "evidence_insufficient", "acceptable", "small_watch",
            frozenset({"thesis"}),
        ),
        (
            "evidence_insufficient", "normal", "intact", "acceptable", "small_watch",
            frozenset({"valuation"}),
        ),
        (
            "fair", "evidence_insufficient", "intact", "acceptable", "small_watch",
            frozenset({"heat"}),
        ),
        # small_watch conflict — no single weak link
        ("fair", "normal", "intact", "acceptable", "small_watch", frozenset()),
    ],
)
def test_derive_contributing_dimensions_branch_table(
    valuation, heat, thesis, product, opportunity_state, expected,
):
    result = derive_contributing_dimensions(
        valuation, heat, thesis, product, opportunity_state,
    )
    assert result == expected


def test_derive_contributing_dimensions_returns_frozenset_not_set():
    """AC #6: equality is blind to set-vs-frozenset because `set({"a"}) ==
    frozenset({"a"})` is True. OpportunityRow is a frozen dataclass, so a
    mutable set field would silently break hashability."""
    result = derive_contributing_dimensions(
        "cheap", "normal", "intact", "strong", "core_dca",
    )
    assert isinstance(result, frozenset)
```

- [ ] **Step 2: Run test to verify it fails with ImportError**

Run: `uv run pytest tests/opportunity/test_states.py -x -q`
Expected: collection error / ImportError — `cannot import name 'derive_contributing_dimensions' from 'irc.opportunity.states'`.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/opportunity/test_states.py
git commit -m "test(opportunity): add failing tests for derive_contributing_dimensions"
```

---

## Task 2 — Implement `derive_contributing_dimensions` to make tests green

**Files:**
- Modify: `src/irc/opportunity/states.py:343-346` (insert new function between `compose_opportunity_state` and `_structural_evidence_gaps`)

- [ ] **Step 1: Insert the function**

Insert immediately after line 343 (the closing `)` of `compose_opportunity_state`'s return) and immediately before the existing blank line that precedes `def _structural_evidence_gaps`:

```python


def derive_contributing_dimensions(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product: ProductQualityState,
    opportunity_state: OpportunityState,
) -> frozenset[str]:
    """Return the subset of {valuation, heat, thesis, product_quality} that
    drove `opportunity_state`. Pure; mirrors `compose_opportunity_state`'s
    branches. Used by the per-driver citation gate (Slice D2a, item 009).

    `small_watch` priority chain mirrors `_weak_link_label` but returns
    dimension keys, not Chinese labels — calling `_weak_link_label` and
    reverse-mapping would couple us to a display-string lookup table.
    """
    if opportunity_state == "exclude":
        dims: set[str] = set()
        if thesis == "falsified":
            dims.add("thesis")
        if product == "poor":
            dims.add("product_quality")
        return frozenset(dims)
    if opportunity_state == "core_dca":
        return frozenset({"valuation", "heat", "thesis", "product_quality"})
    if opportunity_state == "pause_wait":
        dims = set()
        if valuation in ("expensive", "very_expensive"):
            dims.add("valuation")
        if heat in ("crowded", "overheated"):
            dims.add("heat")
        return frozenset(dims)
    if opportunity_state == "small_watch":
        if product == "weak":
            return frozenset({"product_quality"})
        if thesis == "evidence_insufficient":
            return frozenset({"thesis"})
        if valuation == "evidence_insufficient":
            return frozenset({"valuation"})
        if heat == "evidence_insufficient":
            return frozenset({"heat"})
        return frozenset()
    return frozenset()
```

- [ ] **Step 2: Run the new tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_states.py::test_derive_contributing_dimensions_branch_table tests/opportunity/test_states.py::test_derive_contributing_dimensions_returns_frozenset_not_set -v`
Expected: 13 passed (12 parametrized + 1 frozenset-type).

- [ ] **Step 3: Run the full opportunity test module to verify nothing else regressed**

Run: `uv run pytest tests/opportunity/ -x -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add src/irc/opportunity/states.py
git commit -m "feat(opportunity): add derive_contributing_dimensions"
```

---

## Task 3 — Add `contributing_dimensions` field to `OpportunityRow`

**Files:**
- Modify: `src/irc/opportunity/types.py:117-132` (`OpportunityRow` dataclass)

- [ ] **Step 1: Add the trailing defaulted field**

Edit the `OpportunityRow` dataclass: append `contributing_dimensions` as the last field, after `expected_omissions`.

Before:
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

After:
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
    contributing_dimensions: frozenset[str] = field(default_factory=frozenset)
```

Note: `field` is already imported on line 3 (`from dataclasses import dataclass, field`). Use `default_factory=frozenset` rather than `default=frozenset()` to avoid the shared-default-instance trap; frozenset is immutable so either is safe in practice, but `default_factory` is the dataclass-idiomatic way and ruff-clean.

- [ ] **Step 2: Run full opportunity tests — existing constructors still work**

Run: `uv run pytest tests/opportunity/ -x -q`
Expected: all green. AC #1 says existing constructors that omit the new field must still instantiate; the default makes this so.

- [ ] **Step 3: Commit**

```bash
git add src/irc/opportunity/types.py
git commit -m "feat(opportunity): add contributing_dimensions field to OpportunityRow"
```

---

## Task 4 — Populate `contributing_dimensions` in `build_opportunity_row` (TDD)

**Files:**
- Modify: `tests/opportunity/test_states.py` (append integration test)
- Modify: `src/irc/opportunity/states.py:409-431` (`build_opportunity_row`)

- [ ] **Step 1: Append the failing integration test**

Add at the end of `tests/opportunity/test_states.py`:

```python
def test_build_opportunity_row_populates_contributing_dimensions_for_core_dca():
    """AC #5: end-to-end propagation through build_opportunity_row. A clean
    core_dca input must surface all four dimensions."""
    inp = _make_full_input(valuation_percentile_self=0.15)  # cheap → core_dca
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.opportunity_state == "core_dca"
    assert row.contributing_dimensions == frozenset(
        {"valuation", "heat", "thesis", "product_quality"},
    )
    assert isinstance(row.contributing_dimensions, frozenset)
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `uv run pytest tests/opportunity/test_states.py::test_build_opportunity_row_populates_contributing_dimensions_for_core_dca -v`
Expected: FAIL — `row.contributing_dimensions` is `frozenset()` (the default), not the expected four-element set.

- [ ] **Step 3: Wire `derive_contributing_dimensions` into `build_opportunity_row`**

In `src/irc/opportunity/states.py`, after the existing `compose_opportunity_state(...)` call (currently ends ~line 411) and before the `target = map_lookthrough(inp)` line, add:

```python
    dimensions = derive_contributing_dimensions(valuation, heat, thesis, product, state)
```

Then add `contributing_dimensions=dimensions,` to the `OpportunityRow(...)` constructor call as the final kwarg (after `thesis_evidence=evidence,`).

Resulting tail of `build_opportunity_row`:

```python
    state, state_reason = compose_opportunity_state(
        valuation, heat, thesis, product, inp.venue_compatible,
    )
    dimensions = derive_contributing_dimensions(valuation, heat, thesis, product, state)
    target = map_lookthrough(inp)
    reason = " | ".join([state_reason, val_reason, heat_reason, thesis_reason, product_reason])
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
    )
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `uv run pytest tests/opportunity/test_states.py::test_build_opportunity_row_populates_contributing_dimensions_for_core_dca -v`
Expected: PASS.

- [ ] **Step 5: Run the full opportunity test module — no regressions**

Run: `uv run pytest tests/opportunity/ -x -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): populate contributing_dimensions in build_opportunity_row"
```

---

## Task 5 — Lint + full test sweep

- [ ] **Step 1: Run ruff on touched paths**

Run: `uv run ruff check src/irc/opportunity/ tests/opportunity/`
Expected: zero diagnostics. If the new function or test trips a rule, fix in-place before proceeding (do not add `# noqa`).

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -x -q`
Expected: all green across the entire repo. If anything outside `tests/opportunity/` breaks, that is drift — stop, surface the failure, do not silently widen scope.

- [ ] **Step 3: No commit needed unless ruff made changes**

If ruff made fixes, commit them: `git add -u && git commit -m "chore(opportunity): ruff fixes for contributing_dimensions"`.

---

## Acceptance check (post-impl)

Map each spec AC to its verifying step:

| AC | Verified by |
| --- | --- |
| #1 — `OpportunityRow.contributing_dimensions` field with default | Task 3 Step 2 (full opportunity tests still green with no constructor changes elsewhere) |
| #2 — `derive_contributing_dimensions` pure, placed between `compose_opportunity_state` and `_structural_evidence_gaps`, returns `frozenset[str]` | Task 2 Step 1 (placement) + Task 1 (signature, purity by inspection) |
| #3 — `build_opportunity_row` calls deriver immediately after composer, passes result to constructor | Task 4 Step 3 + Step 4 |
| #4 — Branch-table enumeration test for all required cases | Task 1 Step 1 (12 parametrized cases covering all 12 spec rows) |
| #5 — End-to-end propagation test through `build_opportunity_row` for `core_dca` | Task 4 Step 1 |
| #6 — At least one test asserts `isinstance(result, frozenset)` | Task 1 (`test_derive_contributing_dimensions_returns_frozenset_not_set`) + Task 4 (integration test also asserts isinstance) |
| #7 — Function not referenced from any production module other than `build_opportunity_row` | Verify via `git diff --stat` against the spec's "Files touched" list. Only `states.py` and `types.py` modified in production; only `build_opportunity_row` calls the new function. |
| #8 — Full `pytest tests/opportunity/` passes | Task 4 Step 5 + Task 5 Step 2 |

---

## Out-of-band

- No changes outside the three files listed in §"File structure" (`states.py`, `types.py`, `test_states.py`). If you discover you need to touch another file, **STOP**, surface in the drift check, do not silently expand scope.
- No comments added beyond the two WHY-non-obvious docstrings already specified: (a) deriver-function docstring explaining why we don't call `_weak_link_label`, (b) test docstring explaining the `set != frozenset` invariant. The spec explicitly forbids touching `_weak_link_label` or `compose_opportunity_state` logic.
- No new dimensions. Universe is exactly `{"valuation", "heat", "thesis", "product_quality"}`.
- No wiring into renderers, serializers, audit gates, or memo paths — those are items 002 and 009.
