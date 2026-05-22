# Item 001 inline review — contributing-dimensions (Slice A0)

## Verdict
PASS-WITH-NITS

## Blocker bugs
None.

## Latent bugs
None.

### Detailed analysis

**`exclude` branch alignment** — `compose_opportunity_state` fires `exclude` when
`thesis == "falsified" or product_quality == "poor"`. The deriver's `exclude` branch
correctly collects both contributors independently with two separate `if` guards
(not `elif`), so the double-trigger case (`frozenset({"thesis","product_quality"})`) is
correctly returned. Aligned.

**`pause_wait` branch alignment** — `compose_opportunity_state` fires `pause_wait` when
`expensive or hot_heat` (i.e. `valuation in ("expensive","very_expensive") or
heat in ("crowded","overheated")`). The deriver collects both independently, matching
this logic exactly. Aligned.

**`small_watch` priority chain** — `_weak_link_label` (the canonical small_watch
priority) returns the single "weakest link" label in priority order: product_quality →
thesis → valuation → heat → conflict. The deriver mirrors this chain, returning a
singleton frozenset per winning dimension. The fall-through `return frozenset()` for
the conflict case is correct (no single weak link). Aligned with `_weak_link_label`.

**`core_dca` returns all four** — `compose_opportunity_state` fires `core_dca` only when
`cheap_or_low and quiet_heat and intact_thesis and decent_product` — i.e., all four
dimensions are positive drivers. Returning all four is semantically correct.

**`field(default_factory=frozenset)`** — Correct. `field(default=frozenset())` would
share one mutable object across instances (though `frozenset` is immutable, it is still
the right pattern for `dataclass(frozen=True)`). Using `default_factory=frozenset`
is idiomatic and correct.

**Immutability** — Function never mutates its arguments; intermediate `set[str]` is
local and immediately converted to `frozenset` before return. No shared mutable state.

**Purity** — No I/O, no logging, no side effects. Deterministic.

## Nits / style observations

1. **Docstring length** — The docstring in `derive_contributing_dimensions` (6 lines
   including the "note on `small_watch`" paragraph) is the longest in the module by
   some margin. It is accurate and justified (the `_weak_link_label` coupling note is
   genuinely non-obvious), so this is purely cosmetic.

2. **Mid-file import in test** — `from irc.opportunity.states import
   derive_contributing_dimensions` at line 478 of `test_states.py` follows the
   pre-existing module E402 idiom. Non-blocking; documented in drift verdict.

3. **Lint count unchanged** — The 19 ruff errors in scope are all pre-existing; zero
   new errors introduced. The new E402 at line 478 is consistent with the established
   pattern.

## Coverage assessment

The test suite exercises the function's behavior thoroughly:

- `test_derive_contributing_dimensions_branch_table` — 12 parametrized cases covering
  all four `opportunity_state` branches. The `exclude` branch hits 3 sub-cases (thesis
  only, product only, both). The `pause_wait` branch hits 3 sub-cases (valuation only,
  heat only, both). The `small_watch` branch hits the full 5-step priority chain
  including the conflict/empty case. `core_dca` is covered with 1 case (deterministic
  branch, no sub-cases needed).

- `test_derive_contributing_dimensions_returns_frozenset_not_set` — Directly asserts
  `isinstance(result, frozenset)`, satisfying AC #6. The docstring explains *why* this
  matters (frozen dataclass hashability), which is the non-obvious reason.

- `test_build_opportunity_row_populates_contributing_dimensions_for_core_dca` — End-to-
  end integration through `build_opportunity_row`; asserts both value equality and
  `isinstance(frozenset)`. Satisfies AC #5.

Coverage is substantive, not ceremonial. All meaningful branches of the deriver are
exercised by name with explicit expected values.

## Recommendation
Ready to merge once verify + pr-review verdicts are also PASS / PASS-WITH-NITS.
No fix loop needed.
