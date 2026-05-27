# ADR 0005 — `advisory_gaps`: a third gap-like field on `OpportunityRow`

**Status:** Accepted (2026-05-27, instrument-pickability item 001).
**Supersedes:** none. Builds on [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md) (H3 partition predicate) and the May-2026 `expected_omissions` field on `OpportunityRow` (`docs/AUTODEV-LOOP/items/005-plan.md`).
**Spec:** `docs/2026-05-27-instrument-pickability/items/001-spec.md`.

## Context

The opportunity row already carries two gap-like tuple fields:

- `evidence_gaps` — row-blocking. H3 (ADR 0003 §3) routes any row with `evidence_gaps != ()` away from `thesis_cards.yaml` + `opportunity_report.json.rows` into the discipline failure section. The failure renderer reads only 4 fields; the row has not earned conclusions.
- `expected_omissions` — structural non-features by design (currently `constituent_not_applicable` for `gold`, `cn_bond_fund`, `qdii_global`). Surfaced separately so they don't pollute the actionable list, but the row remains publishable.

Item 001 introduces a third category: **non-blocking advisories that the operator should see in publishable outputs.** First instance is `top_holdings_broker_thin` — an active fund whose top-5 holdings have weak broker coverage. Such a fund's per-holding CN broker pipeline didn't reach every Top-5 position, but the fund itself is fully publishable (data + information legs intact at the fund or constituent level; Policy B did not reject). The operator needs to see the weakness when ranking picks; the row should not be hidden in the failure section.

Three placements were considered:

1. **Add to `evidence_gaps`** — Rejected. H3 routes the row to `gapped_rows`. The failure renderer's 4-field contract would prevent the operator from ever seeing the row's `opportunity_state` or `note_cn`. Widening H3's predicate to "not all gaps are blocking" would require a publishable-safe allowlist scattered across `_write_opportunity_outputs`, `_partition_gaps`, and the discipline bucket sections — three places where the next contributor could "fix" the allowlist by removing entries.
2. **Widen `expected_omissions`** — Rejected. `expected_omissions` carries the explicit meaning "structural non-feature by design." `top_holdings_broker_thin` is the opposite — it's a real evidence gap that just happens to not warrant fail-close. Conflating the two semantics would force every future reader of `expected_omissions` to disambiguate, and every consumer (cards, report serializer, renderer) would need an additional branch to know which codes are "by design" vs "actionable advisory."
3. **New field `advisory_gaps`** — Accepted.

## Decision

Add a new field `advisory_gaps: tuple[str, ...] = ()` to `OpportunityRow` (mirrored on `ThesisCard`, serialised by `compose_opportunity_report._row_to_dict`).

- Populated by `derive_thesis_from_evidence` (active-fund branch only for V1) and partitioned out of the flat `gaps` return by `_partition_gaps` in `src/irc/opportunity/states.py`. `_partition_gaps` becomes a 3-way split returning `(real_gaps, expected_omissions, advisory_gaps)`.
- Allowlist `ADVISORY_GAP_CODES: frozenset[str]` lives at module-top in `states.py` alongside `EXPECTED_OMISSION_CODES`. Initial members: `{"top_holdings_broker_thin"}`.
- H3 partition predicate in `_write_opportunity_outputs` stays exactly `evidence_gaps == ()` — `advisory_gaps` is orthogonal and rows carrying it remain publishable.
- Renderers (memo §6 risk notes, discipline header, picks-table tiebreaker) read `row.advisory_gaps`. The thesis-state setter invariant (CONTEXT.md / ADR 0003 §1) is preserved: only `derive_thesis_from_evidence` writes `thesis_state`; the new field carries the advisory codes through the existing `gaps` return slot.

## Why this is hard to reverse

- `OpportunityRow` is a frozen dataclass serialised into `opportunity_report.json`, cached `thesis_cards.yaml`, and read by item 008's two-run byte-equality lockdown. Adding the field touches the serializer (`_row_to_dict`), `ThesisCard` mirror, `cards.py` propagation, and every fixture builder in `tests/`.
- Once consumers (memo §6, discipline header, picks-table) read `advisory_gaps`, removing the field requires reverting those renderer surfaces too. Renaming it later means a coordinated change across producer (`thesis_evidence.py`), partition (`states.py`), type (`types.py`), serializer (`report.py`), card (`cards.py`), three renderer sites (`memo_cmd.py`, `picks_table.py`, `report.py::render_failure_section`), and the lockdown fixture in `tests/integration/test_publishable_set_lockdown.py`.
- The H3 partition predicate is one of the load-bearing invariants of the opportunity pipeline. Touching it (option 1) would silently shift rows between the publishable and gapped buckets — exactly the class of bug the lockdown was designed to catch.

## Consequences

- A row may now carry simultaneously: `evidence_gaps == ()` (publishable) AND `advisory_gaps == ("top_holdings_broker_thin",)` AND a Policy B rule 2.5 acceptance. All three are correct; the row publishes via fund-level evidence, AND the operator sees the per-holding broker thinness warning. Documented in the `advisory_gaps` CONTEXT.md entry.
- Cache files written before this ADR re-hydrate with `advisory_gaps=()` — the field defaults to empty tuple on the frozen dataclass, mirroring the `expected_omissions` migration pattern. No cache invalidation required.
- The SAME-3 invariant (CONTEXT.md "Renderers + alias-builder") is unaffected: `advisory_gaps` does not contribute to `thesis_evidence`, citation_ids, or the 3-way citation-set equality across picks-table / evidence-pool / discipline.
- Citation gate v1 dual-leg structural binding (CONTEXT.md "Audit gates and enforcement modes") is unaffected: `advisory_gaps` does not change `thesis_evidence` shape or the data/information leg requirement.

## Considered Options

- **Option 1 — fold into `evidence_gaps` + publishable-safe allowlist.** Rejected (would invert H3; allowlist drift across three modules).
- **Option 2 — widen `expected_omissions`.** Rejected (collapses two distinct semantics: "structural by design" vs "actionable advisory").
- **Option 3 — new `advisory_gaps` field.** Accepted.
