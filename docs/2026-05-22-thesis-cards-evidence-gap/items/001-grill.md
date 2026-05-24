# Item 001 grill verdict — contributing_dimensions (Slice A0)

## Verdict

PASS-WITH-EDITS

## Questions raised & resolved

1. **Does the spec use domain terms consistent with `CONTEXT.md`?** Yes. `CONTEXT.md` already defines "Contributing dimensions" (line 17) and names `derive_contributing_dimensions` as the canonical producer. No glossary edit needed.
2. **Is the §Branch mapping consistent with `compose_opportunity_state` (states.py:311-343) and `_weak_link_label` (states.py:287-308)?** Yes. All four branches and the small_watch priority chain (product_quality=="weak" → thesis=="evidence_insufficient" → valuation=="evidence_insufficient" → heat=="evidence_insufficient" → conflict) match the source exactly. The original diagnosis row omitted `product_quality=="weak"` as priority 1; the spec correctly corrects this.
3. **Open question Q2 (call `_weak_link_label` vs re-derive priority)** — resolved in favour of re-derive. The five-line priority chain duplicates trivially, and re-derive avoids a Chinese-string-to-dimension-key lookup table. Document the choice in spec; planner does not need to pick.
4. **Hidden coupling: does `ThesisCard` need the field for item 002 to serialize?** No. Item 002 (`_row_to_dict`) operates on `OpportunityRow` directly, and `ThesisCard` propagation is explicitly deferred. Confirmed by reading `types.py` (ThesisCard at line 136-157 has no such field today).
5. **Is `frozenset()` the right semantic for `small_watch` × conflict, vs a `{"conflict"}` sentinel?** Yes, `frozenset()` is correct. A sentinel would force D2a (item 009) to look up `"conflict"` in the per-dimension evidence-type table where no such entry exists. The diagnosis row explicitly states "coarse dual-leg gate still applies; no per-dimension requirement"—`frozenset()` is the literal encoding of that.
6. **Do the acceptance criteria catch a `set`-instead-of-`frozenset` regression?** **No** — `set({"a"}) == frozenset({"a"})` is `True` in Python, so equality assertions are blind to the type. **Edit applied** to add explicit `isinstance(..., frozenset)` requirement (new AC #6). This matters because `OpportunityRow` is a frozen dataclass; a mutable `set` field would break hashability silently.

## Spec edits applied

- Added new acceptance criterion #6: require at least one test to assert `isinstance(result, frozenset)`. Renumbered the trailing two ACs (production-module-isolation, pytest-passes) accordingly. Rationale captured inline.

## CONTEXT.md changes

None. `CONTEXT.md` already contains the canonical glossary entry for "Contributing dimensions" (line 17).

## ADR created

None. This slice is small, mechanical, and reversible. Adding a new defaulted field and a deterministic derivation function does not meet the ADR bar (hard-to-reverse + surprising-without-context + genuine trade-off).

## Residual open questions

None blocking. Planner judgment calls remaining: (a) put tests in `test_states.py` vs new `test_contributing_dimensions.py` (either acceptable); (b) helper-function style for the small_watch priority chain (inline if/elif vs a private `_weak_link_dimension` mirroring `_weak_link_label`)—both produce identical behaviour and either is fine.
