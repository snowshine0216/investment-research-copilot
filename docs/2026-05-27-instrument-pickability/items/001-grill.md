Verdict: PASS

Subagent: opus
Questions resolved: 13
Docs touched:
  - CONTEXT.md (commit 43a61bf)
  - docs/adr/0005-advisory-gaps-field.md (commit 43a61bf, new file)
Spec refined: docs/2026-05-27-instrument-pickability/items/001-spec.md (commit 43a61bf)

## Resolved decisions

- Q: Does the spec's proposed `OpportunityRow.advisory_gaps` collide with the existing `evidence_gaps` semantics?
  A: No collision IF the field is dedicated (not folded into `evidence_gaps`). Picked dedicated new field; rejected widening `evidence_gaps`.
  Rationale: H3 partition predicate is `evidence_gaps == ()`. Folding would require a publishable-safe allowlist across `_write_opportunity_outputs`, `_partition_gaps`, and discipline bucket sections — fragile.
  Doc impact: ADR 0005 + CONTEXT.md `advisory_gaps` term + H3 entry sentence on orthogonality.

- Q: Should the H3 invariant predicate widen to include `advisory_gaps`?
  A: No. Predicate stays exactly `evidence_gaps == ()`.
  Rationale: widening would invert H3's load-bearing semantic ("any gap → failure section") into a per-code allowlist.
  Doc impact: CONTEXT.md H3 entry — added sentence stating predicate unchanged.

- Q: Should `expected_omissions` widen to include `top_holdings_broker_thin`?
  A: No. Two distinct semantics — "structural non-feature by design" vs "actionable advisory."
  Rationale: conflating forces every consumer to disambiguate per-code; breaks the AUTODEV-LOOP item 005 contract that introduced `expected_omissions`.
  Doc impact: ADR 0005 considered-options.

- Q: Should `top_holdings_broker_thin` go into CONTEXT.md "evidence-gap catalog"?
  A: Yes — under "Failure-mode + audit policy" alongside the new `advisory_gaps` entry, next to `audit_errors`.
  Rationale: that section is where `failure_reasons` / `evidence_gaps` / `audit_errors` already cluster; canonical placement.
  Doc impact: CONTEXT.md term `top_holdings_broker_thin`.

- Q: Does the design actively preserve the `thesis_state` setter invariant (not just "fails to violate")?
  A: Yes. Gap goes through `derive_thesis_from_evidence`'s existing `gaps` return slot; `thesis_state` (return position 0) is untouched.
  Rationale: by routing through the same function that holds the invariant, the design reinforces the locus of authority rather than working around it.
  Doc impact: none (already covered by existing PolicyBVerdict entry).

- Q: Is the OR threshold semantics (≥2 of Top-5 OR ≥20% summed weight) surprising vs codebase precedent?
  A: Mildly surprising — no OR precedent (`FOREIGN_HEAVY_THRESHOLD` is single `>=`; `MATERIAL_HOLDING_QUORUM` is `ceil(top_n/2)`). But rationale holds: count-of-2 alone misses 1-of-5/25%; weight alone misses 2-of-5/5%-each scattered concentration.
  Rationale: both branches deterministic and named via `Final` constants — the OR is explicit, not hidden.
  Doc impact: none (no ADR — fails "surprising" gate; threshold values trivially reversible).

- Q: Pick-ordering tiebreaker — where in the hierarchy?
  A: Not a tiebreaker. `_build_pick_rows` does NOT sort today; preserves trade-plan order. Replacement is a stable partition (`non-advisory` then `advisory`).
  Rationale: there is no primary sort key to layer onto; spec misnamed the construct. Stable partition preserves trade-plan order within each bucket.
  Doc impact: spec AC8 corrected via strike-through.

- Q: How is "active fund" detected in code?
  A: Two signals: `_is_active_fund(OpportunityInput)` in states.py and `isinstance(snapshot, ActiveFundSnapshot)` in thesis_evidence.py. Gap emission uses the isinstance gate — natural since `derive_thesis_from_evidence` already branches there.
  Rationale: `FundLevelSnapshot` and `ConstituentSnapshot` branches never call the new helper, so AC4 (no passive regression) is structurally locked.
  Doc impact: none (AC4 already aligns).

- Q: Where does the emission helper live without enlarging the 454-line `thesis_evidence.py`?
  A: New file `src/irc/opportunity/advisory_gaps.py` (≤80 lines): helpers + constants + `ADVISORY_GAP_CODES`. `thesis_evidence.py` adds one import + one function call.
  Rationale: file-size constraint from CLAUDE.md forbids enlarging the existing violation; extract is the prescribed remedy.
  Doc impact: spec planning note in Resolved decisions.

- Q: Does `advisory_gaps` warrant an ADR by the three-of-three rule?
  A: Yes. Hard-to-reverse (frozen dataclass + serializer + card + 3 renderers + lockdown fixture); surprising (third gap-like field next to `evidence_gaps` and `expected_omissions`); real trade-off (three placements considered, each rejected option had a concrete failure mode).
  Rationale: ADR formalises the rejection of options 1 and 2 so the next contributor doesn't "simplify" by folding the field back.
  Doc impact: ADR 0005 created.

- Q: Foreign-heavy interaction — Policy B rule 2.5 acceptance + `top_holdings_broker_thin` simultaneously. Contradiction?
  A: No — both correct, different concerns. Rule 2.5 accepts on fund-level evidence; advisory gap warns per-holding depth is structurally thin.
  Rationale: exactly the warning an operator wants when ranking foreign-heavy funds against domestic peers.
  Doc impact: CONTEXT.md `advisory_gaps` entry — coexistence note with rule 2.5.

- Q: Citation gate v1 dual-leg structural binding — affected?
  A: No. `advisory_gaps` does not change `thesis_evidence` shape, citation_id format, or data/information leg requirement.
  Rationale: gap is advisory, not structural; orthogonal to citation surface.
  Doc impact: none.

- Q: SAME-3 invariant — affected?
  A: No. New gap does not add to `thesis_evidence`; picks-table 证据 / evidence-pool / discipline `_render_section` all read `thesis_evidence` unchanged.
  Rationale: orthogonal field, no citation contribution.
  Doc impact: none.
