Verdict: PASS

Subagent: opus
Questions resolved: 11
Docs touched:
  - CONTEXT.md (commit d882685)
  - docs/adr/0003-failure-mode-policy-b.md (commit d882685)
Spec refined: items/001-spec.md (commit d882685)

## Resolved decisions

- Q: Is `RejectionReasonCode` literal `"foreign_heavy_evidence_missing"` a NEW
     literal added to the `Literal[...]` tuple, or does it map to an existing
     code (e.g. `incomplete_constituent_data`)?
  A: NEW literal, identity-mapped from the gap code
     `foreign_heavy_fund_level_evidence_missing` in `_GAP_TO_REASON`. Appended
     LAST in the dict-literal insertion order (mirroring `citation_gate_blocked`
     precedent) so existing precedence is unchanged.
  Rationale: the operator distinction "we couldn't reach this fund's data
     because the per-holding pipeline doesn't cover HK/US" vs "the filings
     pipeline broke" is the load-bearing signal the new code preserves.
  Doc impact: ADR-0003 §7 + spec AC7 (strike-through refinement).

- Q: Must `fund_level_evidence` carry `scope="instrument"`,
     `owner_instrument_id=fund_id`, `parent_fund_id=None`, `constituent_key=None`
     for the dual-coverage gate to accept it on the publishable row?
  A: YES. Structural identity with `_build_fund_level_snapshot`'s evidence
     shape is required. Otherwise the downstream dual-coverage gate silently
     rejects the row.
  Rationale: reuse the QDII reform's evidence shape exactly — same
     audit-trail semantics, same citation-id space.
  Doc impact: CONTEXT.md `ActiveFundSnapshot.fund_level_evidence` entry.

- Q: When rule 2.5 publishes, what merges `snapshot.fund_level_evidence`
     into `row.thesis_evidence` — extend `_stamp_audit_errors_from_verdict`,
     or factor a new helper?
  A: Factor a NEW helper, e.g. `_stamp_fund_level_evidence_from_verdict`,
     alongside the existing `_stamp_audit_errors_from_verdict`. The two
     helpers handle different concerns (audit_errors → constituent_analyses
     vs row-level evidence → thesis_evidence).
  Rationale: one function, one responsibility (FP principle); avoids
     coupling two unrelated transforms.
  Doc impact: spec AC6 (strike-through refinement); implementation-notes
     hint preserved.

- Q: Should the active-fund cache serializer round-trip
     `fund_level_evidence` be an explicit AC?
  A: NO. Constraints section already calls it out under "Cache-shape
     compatibility"; ADR-0003 §7 pins the behaviour normatively. The TDD
     flow (AC15) naturally tests round-trip via the publishable-case
     fixture.
  Rationale: ADR + Constraints together suffice; redundant ACs invite drift.
  Doc impact: ADR-0003 §7 "Cache-shape compatibility" sub-bullet.

- Q: Does rule 2.5's failure code affect the H3 universal-gap invariant or
     the 4-field failure renderer?
  A: NO functional change. The new code participates in `evidence_gaps` like
     any other Policy B gap code; the 4-field renderer reads it via the
     tuple; `_classify_rejection_reason` resolves it through the new
     `_GAP_TO_REASON` entry.
  Rationale: structural — rule 2.5 is a peer of rules 1–5 inside the same
     precedence chain.
  Doc impact: none (existing H3 semantics cover by construction).

- Q: Does rule 2.5 disturb the V1 systematic-exclusions tally?
  A: NO. The line counts `insufficient_info_coverage_top_half` (rule 4)
     entries only. Rule 2.5's failure branch surfaces under the new code,
     NOT in the systematic-exclusions count. Funds that previously failed
     rule 3 due to HK/US-heavy holdings will now publish or fail under the
     new code — they will NOT reach rule 4.
  Rationale: §5's renderer keys off rejection_reason equality, not on which
     rule ran.
  Doc impact: ADR-0003 §7 "Interaction with §5" sub-bullet.

- Q: Does rule 2.5 violate ADR-0003 §6 ("Policy B applies ONLY to
     ActiveFundSnapshot")?
  A: NO. Rule 2.5 lives INSIDE `evaluate_policy_b` and only runs when input
     is `ActiveFundSnapshot`. QDII funds (post-2026-05-25, routed through
     `_build_fund_level_snapshot`) bypass Policy B entirely.
  Rationale: structural — Policy B is the function, rule 2.5 is one of its
     six rules.
  Doc impact: ADR-0003 §7 "Interaction with §6" sub-bullet.

- Q: Should `fund_level_evidence` be renamed to match
     `FundLevelSnapshot.evidence`?
  A: NO. The deliberate asymmetry is load-bearing for the cache serializer
     (`_active_fund_to_dict` and `_fund_level_to_dict` produce different
     JSON shapes; a shared key name would suggest they're interchangeable).
  Rationale: explicit-data-flow principle — different shapes deserve
     different names.
  Doc impact: CONTEXT.md entry pins the naming asymmetry.

- Q: Does the foreign-share computation need to handle empty
     `constituent_analyses`?
  A: YES, gracefully — return `0.0` (AC2 already specifies). Defensive
     guard against snapshots that should have been caught by rule 1.
  Rationale: pure-function determinism.
  Doc impact: none (AC2 normative).

- Q: Should `UNKNOWN` exchange be treated as HK/US-equivalent for funds
     holding off-platform tickers?
  A: NO in V1. Treated conservatively (not foreign). A future
     ticker-resolution improvement that maps UNKNOWN → HK/US would
     naturally re-classify without ADR amendment.
  Rationale: fail-safe by construction — accidental publishability via
     unresolved tickers is worse than over-rejection.
  Doc impact: CONTEXT.md "Foreign-heavy fund" entry pins the policy.

- Q: Does the fetch-budget delta (2 extra calls × N active funds) need a
     preflight contract change?
  A: NO. ~50 active funds × 2 = ~100 calls, well under
     `IRC_FETCH_BUDGET=2000`. Document the per-fund delta for future
     scale-up awareness.
  Rationale: empirical headroom.
  Doc impact: ADR-0003 §7 "Fetch budget impact" sub-bullet.
