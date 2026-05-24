# Item 001 spec — contributing-dimensions (Slice A0)

## Goal

Add a deterministic pure function that derives the set of "contributing dimensions" — which of `{valuation, heat, thesis, product_quality}` actually drove a row's `opportunity_state` — and attach the result to every `OpportunityRow`. The future per-driver citation gate (Slice D2a, item 009) iterates this set to require ≥1 data + ≥1 information citation per contributing dimension. Without an explicit producer the field would always be empty and D2a would silently no-op (no dimensions to check → trivially passes). This slice MUST land before item 002 (D0), which serializes `contributing_dimensions` through `_row_to_dict`.

Source row (verbatim, from `docs/diagnosis-thesis-cards-evidence-gap.md` §3 Slice A, row A0): "New pure function `derive_contributing_dimensions(valuation, heat, thesis, product, opportunity_state) -> frozenset[str]` placed next to `compose_opportunity_state`. … Add `contributing_dimensions: frozenset[str] = frozenset()` field to `OpportunityRow`; populated in `build_opportunity_row` immediately after `compose_opportunity_state`."

## In scope

- `src/irc/opportunity/states.py` — add pure function `derive_contributing_dimensions(valuation: ValuationState, heat: HeatState, thesis: ThesisState, product: ProductQualityState, opportunity_state: OpportunityState) -> frozenset[str]` placed immediately below `compose_opportunity_state`.
- `src/irc/opportunity/types.py` — add field `contributing_dimensions: frozenset[str] = frozenset()` to `OpportunityRow` (frozen dataclass), as a trailing defaulted field so existing constructors keep working.
- `src/irc/opportunity/states.py::build_opportunity_row` — call `derive_contributing_dimensions(...)` immediately after `compose_opportunity_state(...)` returns, and pass the result into the `OpportunityRow(...)` constructor.
- `tests/opportunity/test_states.py` (or a new sibling file) — branch-table enumeration test for `derive_contributing_dimensions`.

## Out of scope

- Do **NOT** modify `compose_opportunity_state` logic. The new function is a strict downstream reader of its outputs.
- Do **NOT** add new dimensions. The universe is exactly `{"valuation", "heat", "thesis", "product_quality"}`.
- Do **NOT** modify `_weak_link_label`. Its labels are Chinese display strings (see Detailed mapping rules §small_watch); they are not dimension keys and must not be conflated.
- Do **NOT** change any other dataclass (`ThesisCard`, `DisciplineRow`, etc.). Propagation to those types is the job of item 002 (D0) and later slices.
- Do **NOT** wire `contributing_dimensions` into any renderer, serializer, audit gate, or memo path. This slice strictly produces the field; downstream readers come in items 002 / 009.

## Detailed mapping rules

The mapping is a pure function over `(valuation, heat, thesis, product, opportunity_state)`. The branch table mirrors `compose_opportunity_state` (`src/irc/opportunity/states.py:311-343`) and `_weak_link_label` (`src/irc/opportunity/states.py:287-308`).

### Branch 1: `opportunity_state == "exclude"`

`compose_opportunity_state` triggers `exclude` on `thesis == "falsified" OR product_quality == "poor"` (line 323). Both conditions can hold simultaneously; the source does not pick one. Return the set of triggers:

| `thesis == "falsified"` | `product == "poor"` | Returns |
| --- | --- | --- |
| true  | true  | `frozenset({"thesis", "product_quality"})` |
| true  | false | `frozenset({"thesis"})` |
| false | true  | `frozenset({"product_quality"})` |
| false | false | `frozenset()` — defensive; shouldn't occur because `compose_opportunity_state` would not have returned `"exclude"` |

The "defensive false/false" case is unreachable given a consistent `(thesis, product, opportunity_state)` tuple from `compose_opportunity_state`; the function returns `frozenset()` rather than raising so it stays a total pure function over its declared input domain.

### Branch 2: `opportunity_state == "core_dca"`

`compose_opportunity_state` line 333 returns `"core_dca"` only when **all four** conditions hold simultaneously: `cheap_or_low AND quiet_heat AND intact_thesis AND decent_product`. All four are therefore drivers:

Return `frozenset({"valuation", "heat", "thesis", "product_quality"})` unconditionally.

### Branch 3: `opportunity_state == "pause_wait"`

`compose_opportunity_state` line 336 returns `"pause_wait"` on `expensive OR hot_heat` where `expensive = valuation in {"expensive", "very_expensive"}` and `hot_heat = heat in {"crowded", "overheated"}`. Thesis and product are *not* drivers here — they were merely "not exclude-triggering" (i.e., `thesis != "falsified"` and `product != "poor"`).

Return the subset of `{"valuation", "heat"}` whose sub-state is bad:

| `valuation in {expensive, very_expensive}` | `heat in {crowded, overheated}` | Returns |
| --- | --- | --- |
| true  | true  | `frozenset({"valuation", "heat"})` |
| true  | false | `frozenset({"valuation"})` |
| false | true  | `frozenset({"heat"})` |
| false | false | `frozenset()` — defensive; unreachable given `opportunity_state == "pause_wait"` |

### Branch 4: `opportunity_state == "small_watch"`

`compose_opportunity_state` falls through to `small_watch` when none of `exclude` / `core_dca` / `pause_wait` matched, then computes a `weak_link` label via `_weak_link_label` for the prose reason. Map that label back to a dimension key:

`_weak_link_label` priority order (lines 300-308, verbatim):
1. `product_quality == "weak"` → label `"产品质量薄弱"` → dimension `"product_quality"`
2. `thesis == "evidence_insufficient"` → label `"主题逻辑证据不足"` → dimension `"thesis"`
3. `valuation == "evidence_insufficient"` → label `"估值数据缺失"` → dimension `"valuation"`
4. `heat == "evidence_insufficient"` → label `"热度信号不足"` → dimension `"heat"`
5. else → label `"信号方向冲突"` → `frozenset()` (conflict case has no single driver)

`derive_contributing_dimensions` re-derives this priority by inspecting the raw sub-states (does **not** call `_weak_link_label` — that function returns Chinese display strings, not dimension keys). Implementation:

```
if opportunity_state == "small_watch":
    if product == "weak":
        return frozenset({"product_quality"})
    if thesis == "evidence_insufficient":
        return frozenset({"thesis"})
    if valuation == "evidence_insufficient":
        return frozenset({"valuation"})
    if heat == "evidence_insufficient":
        return frozenset({"heat"})
    return frozenset()  # conflict / no single weak link
```

The conflict case (`frozenset()`) is intentional: the source row notes that D2a's coarse dual-leg gate still applies to the row, but no per-dimension citation requirement is imposed. Returning a sentinel like `frozenset({"conflict"})` would force D2a to look up `"conflict"` in the evidence-type table, which has no such entry.

### Defensive: `opportunity_state` outside `{"exclude", "core_dca", "pause_wait", "small_watch"}`

`OpportunityState` is `Literal[...]` constrained to those four values (`src/irc/opportunity/types.py:34`). The function returns `frozenset()` via an `else` branch rather than raising, on the principle that this is a *deriver* function — its job is to characterise an upstream decision, not to validate the type system. A future unknown opportunity state should degrade gracefully (no per-dimension gate applied) rather than crashing the entire opportunity pipeline.

## Acceptance criteria

1. `src/irc/opportunity/types.py::OpportunityRow` has a new trailing field `contributing_dimensions: frozenset[str] = frozenset()`. Existing constructors that omit this field still type-check and instantiate.
2. `src/irc/opportunity/states.py` exports `derive_contributing_dimensions(valuation, heat, thesis, product, opportunity_state)` placed between `compose_opportunity_state` and `_structural_evidence_gaps`. It is pure (no I/O, no logging, no mutation of inputs) and returns a `frozenset[str]`.
3. `build_opportunity_row` (`src/irc/opportunity/states.py:375-431`) calls `derive_contributing_dimensions(valuation, heat, thesis, product, state)` immediately after the existing `compose_opportunity_state(...)` call on line 409, and passes the result to the `OpportunityRow(...)` constructor as `contributing_dimensions=...`.
4. A unit test in `tests/opportunity/test_states.py` enumerates representative tuples from every branch of `compose_opportunity_state`'s output and asserts the expected `contributing_dimensions` set. Required cases at minimum:
   - `exclude` × `thesis=falsified, product=acceptable` → `{"thesis"}`
   - `exclude` × `thesis=intact, product=poor` → `{"product_quality"}`
   - `exclude` × `thesis=falsified, product=poor` → `{"thesis", "product_quality"}`
   - `core_dca` × `(cheap, normal, intact, strong)` → `{"valuation", "heat", "thesis", "product_quality"}`
   - `pause_wait` × `(expensive, normal, intact, acceptable)` → `{"valuation"}`
   - `pause_wait` × `(cheap, crowded, intact, acceptable)` → `{"heat"}`
   - `pause_wait` × `(expensive, overheated, intact, acceptable)` → `{"valuation", "heat"}`
   - `small_watch` × `product=weak` (other sub-states arbitrary non-conflict) → `{"product_quality"}`
   - `small_watch` × `thesis=evidence_insufficient, product!=weak` → `{"thesis"}`
   - `small_watch` × `valuation=evidence_insufficient, thesis intact, product acceptable, heat normal` → `{"valuation"}`
   - `small_watch` × `heat=evidence_insufficient, valuation fair, thesis intact, product acceptable` → `{"heat"}`
   - `small_watch` × signal-conflict (no `evidence_insufficient`, product not `weak`, but not a clean `core_dca`/`pause_wait`/`exclude`) → `frozenset()`
5. An additional test asserts the field is populated end-to-end through `build_opportunity_row`: build a row for an instrument that lands in `core_dca` (using the existing test helpers in `tests/opportunity/test_states.py`) and assert `row.contributing_dimensions == frozenset({"valuation", "heat", "thesis", "product_quality"})`.
6. At least one test asserts `isinstance(result, frozenset)` (not just `== frozenset(...)`). Rationale: `set({"a"}) == frozenset({"a"})` evaluates to `True` in Python, so equality-only assertions would not catch a regression where the function accidentally returned a mutable `set`. Required because downstream `OpportunityRow` is a frozen dataclass and a mutable `set` field would silently break hashability and immutability guarantees.
7. `derive_contributing_dimensions` is referenced from no production module other than `build_opportunity_row` (audit/serializer wiring is intentionally deferred to items 002 and 009).
8. The full test suite (`pytest tests/opportunity/`) passes.

## Edge cases

- **`opportunity_state` not in `{exclude, core_dca, pause_wait, small_watch}`** — return `frozenset()` via a defensive `else` (see Detailed mapping rules §Defensive). Justification: `OpportunityState` is a closed `Literal`; this branch is unreachable in practice but keeps the function total. We do not raise because D2a treats `frozenset()` as "coarse gate only", which is the safer no-op behaviour for an unrecognised state.
- **`opportunity_state == "exclude"` with neither trigger condition** (`thesis != "falsified"` AND `product != "poor"`) — defensively return `frozenset()`. Unreachable given a consistent input from `compose_opportunity_state`.
- **`opportunity_state == "pause_wait"` with neither valuation nor heat bad** — defensively return `frozenset()`. Unreachable given a consistent input from `compose_opportunity_state`.
- **`opportunity_state == "core_dca"` with one of the four sub-states off-spec** (e.g., `valuation == "fair"`) — return `frozenset({"valuation", "heat", "thesis", "product_quality"})` unconditionally. We trust `compose_opportunity_state`'s decision; reverse-engineering the four conditions inside this function would duplicate logic that the source row explicitly forbids changing.
- **`opportunity_state == "small_watch"` with `product_quality == "weak"` AND some other sub-state also `evidence_insufficient`** — return `{"product_quality"}` (priority 1 wins). This matches `_weak_link_label`'s priority order so the rendered Chinese label and the dimension set agree on which sub-state was named the weak link.

## Dependencies on other items

- Upstream: none. This is item 001 — the first slice of the run.
- Downstream consumers (do not implement here):
  - Item 002 (Slice D0a) — serializes `contributing_dimensions` through `_row_to_dict` so it reaches `opportunity_report.json`.
  - Item 009 (Slice D2a) — `find_uncited_opportunity_rows` iterates `row.contributing_dimensions` and requires per-dimension citations.

## Files touched (preview for planner)

- `src/irc/opportunity/states.py` — add `derive_contributing_dimensions`; call it from `build_opportunity_row`.
- `src/irc/opportunity/types.py` — add `contributing_dimensions: frozenset[str] = frozenset()` field on `OpportunityRow`.
- `tests/opportunity/test_states.py` — branch-table enumeration test + end-to-end propagation test. (May create a new file `tests/opportunity/test_contributing_dimensions.py` if the planner prefers isolation; either is acceptable.)

## Open questions for the planner

1. The diagnosis row hints at "`states.py:300`" for the priority chain, but the chain actually spans lines 300-308 (line 300 is the first `if`). This is descriptive, not a discrepancy that affects the implementation — the planner can ignore the exact line.
2. The diagnosis row uses the phrasing "`{weak_link}` derived from the priority order in `_weak_link_label`". `_weak_link_label` returns **Chinese display strings**, not dimension keys. The mapping in §Branch 4 above re-implements the priority chain over the raw sub-states rather than calling `_weak_link_label` and mapping its output — this avoids creating a Chinese-string-to-dimension-key lookup table. The planner should confirm this approach. (Alternative: introduce a parallel `_weak_link_dimension` helper that mirrors `_weak_link_label`'s priority order and returns a dimension key. Functionally equivalent; slightly more code but keeps the priority order defined in one place visually. Either is acceptable.)
3. Test file location: a new `tests/opportunity/test_contributing_dimensions.py` may be cleaner than appending to the already-large `test_states.py`. Planner's call.
