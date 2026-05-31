Verdict: PASS

Subagent: opus
Questions resolved: 6
Docs touched:
  - CONTEXT.md (commit ff9ec46)
Spec refined: items/002-spec.md (commit ff9ec46)

## Resolved decisions
- Q: Are CHEAP_UPSIDE_THRESHOLD=0.20 / RICH_UPSIDE_THRESHOLD=-0.10 defensible defaults?
  A: Yes — pin as proposed; named module constants, ratio units, tunable in one line.
  Rationale: +20% is a conventional material-upside-vs-consensus bar; -10% is asymmetric/tighter so the DCA gate errs conservative (slow to call cheap). No labelled dataset in-repo — best-judgment, isolated.
  Doc impact: CONTEXT.md term valuation_fundamental_signal

- Q: Threading mechanism — explicit compose_opportunity_state parameter vs classify_valuation notch-refusal (pick exactly one)?
  A: The explicit composer parameter is the SINGLE, non-optional, load-bearing mechanism — NOT belt-and-suspenders.
  Rationale: AC3 forbids classify_valuation from moving any state toward more-expensive, so a genuinely-cheap percentile cannot be demoted to break cheap_or_low; the notch path is structurally incapable of blocking core_dca in exactly the case AC4 targets. Block lives in compose_opportunity_state(valuation_fundamental=...); valuation_state stays cheap, only opportunity_state falls through.
  Doc impact: CONTEXT.md term Fundamental-aware core_dca gate; spec AC4 + Open Q4 + Could-not-fully-resolve corrected in place

- Q: ADR escalation — does the core_dca-gating clear the three-of-three bar?
  A: No new ADR; CONTEXT.md update suffices.
  Rationale: hard-to-reverse NO (pure helper + one-notch + optional defaulted param; revert to undo, no migration); surprise is already owned by ADR 0009 ("metric that never fires until data lands"); the design choices are bounded within ADR 0009's frame, not a new architectural shape. Net ~1-2/3, below the 3/3 bar.
  Doc impact: ADR — none

- Q: Does the item-001 AC4 inertness lock break "by design" via the NOTCH, as the spec claimed?
  A: No — for that specific test row it breaks via the REASON ANNOTATION only; AC7 corrected and a second cheap-percentile row must be added.
  Rationale: the lock row seeds a flat 300x100.0 price series; self_history_percentile uses inclusive ranking (count_le/len) → percentile 1.0 → very_expensive, never cheap, so AC3's notch never fires. consensus_upside_pct=0.20 → signal "cheap" only annotates the reason. Provenance preserved (stays in test_inputs_loader.py, keeps population guard, cites spec + ADR 0009).
  Doc impact: spec AC7 corrected in place

- Q: Do H3/SAME-3, Policy B vs thesis_state, and all-None degrade invariants hold?
  A: Yes — verified against code; spec respects all four.
  Rationale: H3 partitions on evidence_gaps==() only (no gap emitted); SAME-3 is set equality over select_citations(row.thesis_evidence) (no ThesisEvidence emitted); thesis_state set exclusively by derive_thesis_from_evidence and Policy B untouched — valuation_state is a separate Literal axis that cannot leak in; all-None → valuation_fundamental_signal None + composer param default None → byte-identical to pre-002.
  Doc impact: none (AC8 confirmation only)

- Q: Augment vs replace; do pe/pb participate in the state decision?
  A: Augment-only anchor (never replace); pe/pb are reason-only and never change the state.
  Rationale: percentile band is the always-available signal; consensus_upside_pct is None in production, so replacement would collapse every equity to evidence_insufficient (a regression). earnings_yield anchor is the exact annotate-never-change precedent. pe/pb have no self-history/peer percentile context → unsound to threshold absolutely across the mixed CN/HK/US-QDII universe.
  Doc impact: CONTEXT.md term valuation_fundamental_signal
