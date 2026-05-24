# Item 001 verify — contributing-dimensions (Slice A0)

## Verdict
PASS

## Smoke results
- **Import smoke**: `imports OK` printed; `derive_contributing_dimensions`, `compose_opportunity_state`, `build_opportunity_row` all importable from `irc.opportunity.states`; `OpportunityRow` importable from `irc.opportunity.types`. No errors.
- **Behavioral spot-checks (12 branches)**:
  - `exclude` × thesis=falsified, product=poor → `frozenset({'product_quality', 'thesis'})` ✅
  - `exclude` × thesis=falsified, product=acceptable → `frozenset({'thesis'})` ✅
  - `exclude` × thesis=intact, product=poor → `frozenset({'product_quality'})` ✅
  - `core_dca` × (cheap, normal, intact, strong) → `frozenset({'valuation','heat','thesis','product_quality'})` ✅
  - `pause_wait` × (expensive, normal, intact, acceptable) → `frozenset({'valuation'})` ✅
  - `pause_wait` × (cheap, crowded, intact, acceptable) → `frozenset({'heat'})` ✅
  - `pause_wait` × (expensive, overheated, intact, acceptable) → `frozenset({'valuation','heat'})` ✅
  - `small_watch` × product=weak (other states evidence_insufficient) → `frozenset({'product_quality'})` ✅
  - `small_watch` × thesis=evidence_insufficient, product=acceptable → `frozenset({'thesis'})` ✅
  - `small_watch` × valuation=evidence_insufficient, thesis=intact, product=acceptable → `frozenset({'valuation'})` ✅
  - `small_watch` × heat=evidence_insufficient, valuation=fair, thesis=intact, product=acceptable → `frozenset({'heat'})` ✅
  - `small_watch` × conflict (under_pressure, no evidence_insufficient) → `frozenset()` ✅
- **`isinstance(result, frozenset)` check**: True ✅
- **OpportunityRow integration**: `uv run pytest tests/opportunity/test_states.py -x -v -k 'contributing'` — 14 tests collected, 14 passed. Includes `test_derive_contributing_dimensions_branch_table` (12 branch-table rows), `test_derive_contributing_dimensions_returns_frozenset_not_set`, and `test_build_opportunity_row_populates_contributing_dimensions_for_core_dca`.
- **`irc --help`**: exits cleanly; CLI loads without import errors. ✅
- **Full suite** (`uv run pytest tests/opportunity/`): 194 passed, 0 failed. ✅

## Acceptance criteria walkthrough
| AC | Verified by | Result |
|----|-------------|--------|
| 1  | `types.py:133` — `contributing_dimensions: frozenset[str] = field(default_factory=frozenset)` present as trailing defaulted field on `OpportunityRow` | ✅ |
| 2  | `states.py:346-387` — `derive_contributing_dimensions` defined between `compose_opportunity_state` (line 311) and `_structural_evidence_gaps` (line 390); returns frozenset; no I/O or mutations | ✅ |
| 3  | `states.py:456` — `dimensions = derive_contributing_dimensions(valuation, heat, thesis, product, state)` called immediately after `compose_opportunity_state` (line 453); passed to `OpportunityRow` as `contributing_dimensions=dimensions` (line 476) | ✅ |
| 4  | `test_states.py:475-525` — branch-table test `test_derive_contributing_dimensions_branch_table` covers all 12 required cases (exclude×3, core_dca×1, pause_wait×3, small_watch×4, conflict×1); all 12 pass | ✅ |
| 5  | `test_states.py:537-546` — `test_build_opportunity_row_populates_contributing_dimensions_for_core_dca` builds a row, asserts `row.contributing_dimensions == frozenset({"valuation","heat","thesis","product_quality"})` and `isinstance(row.contributing_dimensions, frozenset)` | ✅ |
| 6  | `test_states.py:527-534` — dedicated test `test_derive_contributing_dimensions_returns_frozenset_not_set` asserts `isinstance(result, frozenset)` explicitly | ✅ |
| 7  | `grep -rn derive_contributing_dimensions src/` returns exactly 2 hits: the function definition and the call inside `build_opportunity_row`; no audit/serializer/renderer references | ✅ |
| 8  | `uv run pytest tests/opportunity/` — 194 passed, 0 failed | ✅ |

## Notes
- `OpportunityRow.contributing_dimensions` uses `field(default_factory=frozenset)` (idiomatic for frozen dataclasses) rather than `= frozenset()` directly, which is equivalent and correct.
- Behavioral spot-checks were run with 12 cases (more than the 5 called out in the task spec) to exercise every documented branch including all `small_watch` priority sub-cases.
- `derive_contributing_dimensions` is placed at lines 346-387, between `compose_opportunity_state` (311-343) and `_structural_evidence_gaps` (390-407), matching the spec placement requirement.

## Recommendation
Ready for merge
