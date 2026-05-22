# Item 001 drift check — contributing-dimensions (Slice A0)

## Verdict
**PASS-WITH-NOTES** — All plan tasks and spec ACs are satisfied. One pre-existing ruff
F401 (`ThesisEvidence` unused in `states.py`) was already present on the base branch and
is not caused by this work. The E402 mid-file import at line 478 of `test_states.py`
follows the pre-existing idiom of the file (7 prior E402s on the base branch); the plan
explicitly chose to append. Neither warrants a fix loop.

## Files in diff vs. plan

- `src/irc/opportunity/states.py` — in plan ✅
- `src/irc/opportunity/types.py` — in plan ✅
- `tests/opportunity/test_states.py` — in plan ✅
- No files outside the plan's "File structure" table were touched.

## Per-task verification

1. ✅ **Task 1** — Failing test appended at lines 475–535 of `test_states.py` (commit 6a9b565); 12 parametrized branch-table cases + frozenset-type assertion. All plan-specified cases present.
2. ✅ **Task 2** — `derive_contributing_dimensions` added at `states.py:346–393` (commit 1e74da2); placed between `compose_opportunity_state` (ends line 345) and `_structural_evidence_gaps`; implementation matches plan exactly.
3. ✅ **Task 3** — `contributing_dimensions: frozenset[str] = field(default_factory=frozenset)` appended at `types.py:133` (commit df3a4b4); trailing defaulted field, `field` already imported.
4. ✅ **Task 4** — `dimensions = derive_contributing_dimensions(...)` wired at `states.py:456` immediately after `compose_opportunity_state`; `contributing_dimensions=dimensions` passed to `OpportunityRow` constructor (commit c95f964); integration test added at lines 537–546 of `test_states.py`.
5. ✅ **Task 5** — No code changes in diff (expected); pytest and ruff were run (see results below). One pre-existing F401 present but not introduced by this item.

## Per-AC verification

1. ✅ AC 1 — `OpportunityRow.contributing_dimensions: frozenset[str] = field(default_factory=frozenset)` at `types.py:133`; all 194 existing tests still pass with no constructor changes.
2. ✅ AC 2 — `derive_contributing_dimensions` exported from `states.py:346`, placed between `compose_opportunity_state` and `_structural_evidence_gaps`; pure (no I/O, no mutation), returns `frozenset[str]`.
3. ✅ AC 3 — `build_opportunity_row` calls deriver at `states.py:456` immediately after `compose_opportunity_state`, passes result as `contributing_dimensions=dimensions` to constructor.
4. ✅ AC 4 — Branch-table test `test_derive_contributing_dimensions_branch_table` at `test_states.py:518` covers all 12 required spec cases across exclude (3), core_dca (1), pause_wait (3), small_watch (5 including conflict).
5. ✅ AC 5 — End-to-end test `test_build_opportunity_row_populates_contributing_dimensions_for_core_dca` at `test_states.py:537`; asserts `row.contributing_dimensions == frozenset({"valuation","heat","thesis","product_quality"})`.
6. ✅ AC 6 — `isinstance(result, frozenset)` asserted in `test_derive_contributing_dimensions_returns_frozenset_not_set` (line 534) and in the integration test (line 546).
7. ✅ AC 7 — `derive_contributing_dimensions` referenced only in `build_opportunity_row` (`states.py:456`); no other production module imports or calls it (`git diff --stat` confirms only three files changed).
8. ✅ AC 8 — `pytest tests/opportunity/` passes: 194 passed, 0 failed.

## Pre-existing failures (excluded from drift)

`git diff autodev/thesis-cards-evidence-gap..HEAD -- tests/commands/ tests/integration/` returns empty — confirmed neither `tests/commands/test_run_cmd.py::test_only_stage_runs_single` nor `tests/integration/test_thesis_coverage.py::test_thesis_coverage_meets_threshold` was touched by this branch.

## Test + lint results

- `pytest tests/opportunity/ -x`: **194 passed in 0.37s**
- `ruff check src/irc/opportunity/ tests/opportunity/`: 19 errors, **0 introduced by this item**
  - `src/irc/opportunity/states.py:17` F401 `ThesisEvidence` unused — pre-existing on base branch (import present before this item; this item added no new imports to `states.py`).
  - All E402 errors in `test_states.py` (lines 58, 107, 145, 200, 305, 443) — pre-existing mid-file import idiom; line 478 (`from irc.opportunity.states import derive_contributing_dimensions`) is the only new E402, consistent with the established pattern the plan chose to follow.
  - All other errors (`test_bond_valuation.py`, `test_discipline.py`, etc.) — pre-existing, not in files touched by this item.

## Drift signals found

- None. All code changes are justified by a plan task. No plan tasks are missing. No files outside the plan's scope were modified. Test assertions match or exceed spec strength (12 branch-table cases exactly as specced; frozenset type check present in both unit and integration test).

## Recommendation

Ready to ship.
