# Item 001 PR review — contributing-dimensions (Slice A0)

## PR
[#55](https://github.com/snowshine0216/investment-research-copilot/pull/55)

## Verdict
PASS-WITH-NITS

## High-confidence bugs
None.

## Latent bugs (not yet manifest but will bite later)
None.

## Style / pattern observations

**Nit 1 — parameter naming inconsistency across sibling functions.**
`_weak_link_label` and `compose_opportunity_state` both name the fourth parameter
`product_quality: ProductQualityState`; `derive_contributing_dimensions` names it
`product: ProductQualityState`. Since the three functions form a tight cluster
(derive was explicitly placed "immediately below" compose per the spec), the
divergence is a readability nit. The body correctly adds the string `"product_quality"`
to the dimension set regardless, so there is no functional defect. Non-blocking.

**Nit 2 — inline tuple literals duplicate the module-level constant `_EXPENSIVE_VALUATION_STATES`.**
`derive_contributing_dimensions` (line 372) writes `valuation in ("expensive",
"very_expensive")` rather than `valuation in _EXPENSIVE_VALUATION_STATES`. This is a
pre-existing pattern: `compose_opportunity_state` (line 327) also inlines the tuple
instead of reusing the constant. The new code inherits the same habit rather than
correcting it. Non-blocking (both callers are in the same file and the constant is
three lines above), but worth noting as technical debt shared across both functions.

**Nit 3 — `dims` re-declared without type annotation in the `pause_wait` branch.**
The `exclude` branch writes `dims: set[str] = set()` (annotated); the `pause_wait`
branch writes `dims = set()` (unannotated re-use of the same local name after an
early return). Pyright/mypy can infer the type, so this is purely cosmetic.

**Nit 4 — one new E402 mid-file import in `test_states.py`.**
`from irc.opportunity.states import derive_contributing_dimensions` at line 478 follows
the pre-established mid-file import pattern in the test file. The same pattern exists
at lines 58, 107, 145, 200, 305, and 443. The new import is stylistically consistent.
Incidentally, the new `@pytest.mark.parametrize` test activates the previously unused
`import pytest` at the top of the file, which removes a pre-existing F401 lint error
and keeps the total error count unchanged. Non-blocking.

## Coverage gaps

**Untested: `exclude` with `thesis="under_pressure"` + `product="poor"`.**
`compose_opportunity_state` fires `"exclude"` whenever `product_quality == "poor"`,
regardless of thesis state. This includes the case `thesis="under_pressure"` +
`product="poor"`. The derive function correctly handles it (returns
`frozenset({"product_quality"})`), but no test covers this combination. The three
existing `exclude` test cases cover `(falsified, acceptable)`, `(intact, poor)`, and
`(falsified, poor)`. The `(under_pressure, poor)` combination is absent.

**Untested: unknown / invalid `opportunity_state` (defensive fallback).**
The spec explicitly mentions the defensive `frozenset()` fallback for an unrecognised
`opportunity_state` and notes it keeps the function total. No test exercises this
branch (e.g., `derive_contributing_dimensions("cheap","cold","intact","acceptable","unknown")`
→ `frozenset()`). It is unreachable in practice, but the spec called it out as an
intended behaviour.

Neither gap represents a functional defect — the untested branches either mirror
trivially-equivalent logic or are unreachable in production. Both are coverage nits,
not blockers.

## Cross-check vs inline review (items/001-review.md)

The inline review and this PR-level review agree on verdict (PASS-WITH-NITS), zero
blocker bugs, and zero latent bugs. Divergences:

- **New findings here, not in inline review:** Nit 1 (parameter naming inconsistency
  `product` vs `product_quality`), Nit 2 (inline tuple literal vs
  `_EXPENSIVE_VALUATION_STATES`), Nit 3 (unannotated `dims` re-declaration). Also
  identified the `(under_pressure, poor)` and unknown-state coverage gaps, which the
  inline review did not call out.
- **Inline review finding not repeated here:** The inline review noted that the
  `field(default_factory=frozenset)` form is idiomatic for frozen dataclasses (vs
  `field(default=frozenset())`). This PR-level review agrees — not re-flagged as a
  finding.
- **Lint count clarification:** The inline review states "0 new errors introduced."
  That is accurate at the scope of the full `src/irc/opportunity/ tests/opportunity/`
  directory (19 before, 19 after). Within `test_states.py` specifically, the new
  `@pytest.mark.parametrize` block adds 1 E402 (line 478) but simultaneously removes
  a pre-existing F401 (unused `pytest` import now used), keeping the per-file total
  at 9. The inline review did not note this incidental F401 fix.

## Recommendation
Ready to merge. No fix loop needed. All nits are non-blocking style observations;
the two coverage gaps are unreachable branches not required by the spec's ACs.
