# Item 002 inline review — citation-data-model (Slice D0)

## Verdict
PASS-WITH-NITS

## Blocker bugs
None.

## Latent bugs

**1. `select_citations` fills remaining slots using `__eq__` but the slot-reservation guard uses `is` (identity).** Line 63 uses `info_pick is not data_pick` (identity), while line 67 uses `e not in selected` (equality via `__eq__`). For frozen dataclasses, two instances with identical fields are `==`-equal but not `is`-identical. If a caller constructs two separate `ThesisEvidence` objects with identical field values (e.g. duplicate evidence from two fetch paths), line 63 would add both as data-pick and info-pick (since they differ by identity), but line 67 would then exclude one copy when filling remaining slots (since they are `==`-equal). Net effect: possible double-counting of a logically-identical citation in the first two slots. In practice the evidence producers deduplicate upstream, so this is low-probability but worth hardening in item 003.

## Nits / style observations

1. **`_evidence_from_dict` drift/tampering detection is asymmetric**: the function raises on mismatched `citation_id` only when the JSON dict has a non-empty `expected_id`. If the JSON was written with `citation_id=""` (shouldn't happen after item 002, but conceivable from a pre-002 artifact), the check is silently skipped and the recomputed id is used without warning. Consider adding an explicit log/warning when `expected_id` is falsy but the artifact was written after this schema version.

2. **`_strip_venue_suffix` leading-letter strip is over-broad**: the heuristic `stripped[0].isalpha() and stripped[1:].isdigit()` would strip the leading character of a ticker like `H1234` (hypothetical HK fund proxy) even if that's the canonical id. Low risk in current universe but worth a comment noting this is conservative for the known universe (A-share proxies only).

3. **`render_failure_sections` uses `"\n" + "\n".join(parts)`**: the leading `"\n"` adds a blank line before the first `###` header only when the function returns a non-empty string. This is intentional (separator after the picks table) but is not explicitly documented or tested. A test that checks for the leading newline would lock the contract.

4. **`CitationMeta.asset_class` has no validation**: an empty `asset_class` string passes silently through `build_cited_map`. The audit gates in item 009 will depend on this field being a known asset-class string; adding a non-empty check in a `__post_init__` would surface bad data earlier.

5. **Import organisation**: `from irc.opportunity.types import ThesisEvidence` at the top of `memo_cmd.py` is slightly surprising (memo importing from opportunity types directly); it is correct but worth a note in ADR 0001 that memo modules may import types from opportunity.

## Coverage assessment

Strong overall. Key invariants are well-locked:
- `__post_init__` validation: all 4 rejection paths have dedicated tests (empty owner, bad citation_kind, bad scope, empty type/source/date).
- Hash determinism: tested for identical preimage, owner collision, and constituent-key collision.
- `select_citations`: determinism test exercises 3 different orderings of the same 4-entry set; dual-coverage invariant tested with 6 data + 2 info. Rendering order tested with hand-constructed dates.
- `build_cited_map`: wrong-owner and duplicate-id detectors each have a test; happy-path round-trips `CitationMeta` fields.
- `_build_pick_rows`: absent-iid and gapped-iid routing each have tests; venue-suffix stripping has a dedicated unit test.

One gap: there is no test that exercises the `_evidence_from_dict` mismatch-detection path (i.e., a JSON dict with a stale/wrong `citation_id` that triggers the `ValueError`). This is low-risk because the path is only reached when replaying a corrupted artifact, but a test would lock it.

## Recommendation
Merge as-is. Address latent-bug #1 (identity-vs-equality in `select_citations`) in item 003 when constituent evidence is wired; add `CitationMeta.asset_class` non-empty check as a follow-up nit.
