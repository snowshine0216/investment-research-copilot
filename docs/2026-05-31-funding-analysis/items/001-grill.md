Verdict: PASS

Subagent: opus
Questions resolved: 6
Docs touched:
  - CONTEXT.md (commit 6956d23)
  - docs/adr/0009-consensus-upside-degrade-to-none.md (commit 6956d23)
Spec refined: docs/2026-05-31-funding-analysis/items/001-spec.md (commit 6956d23)

## Resolved decisions
- Q: Is `consensus_upside_pct` a new load-bearing term, and what units?
  A: Yes — add to CONTEXT.md "Valuation inputs"; lock as ratio units (`median/close − 1`, e.g. 0.12 = +12%) matching the `qdii_premium_pct` sibling.
  Rationale: closest price-vs-reference sibling is ratio-unit; `_pct` suffix is codebase-inconsistent, so units stated explicitly.
  Doc impact: CONTEXT.md term `consensus_upside_pct`

- Q: Does pe/pb/upside population interact with the dual-coverage gate, citation scope, H3/SAME-3, or Policy B?
  A: No — they are plain `float | None` scalars on `OpportunityInput`, not `ThesisEvidence`; no scope/citation_kind/citation_id, so all citation invariants are structurally untouched.
  Rationale: grep-verified no non-test reader; OpportunityInput is never serialised, so population is provably inert.
  Doc impact: CONTEXT.md term `consensus_upside_pct` + "Valuation-input inertness" entry

- Q: Is the item 001 / 002 boundary crisp; does item 001 touch any classifier or the `core_dca` gate?
  A: Crisp — item 001 only populates inputs + adds the pure helper/fetcher; no classifier reads these fields today. Added an inertness regression lock to AC4 (classify_valuation byte-unchanged).
  Rationale: `classify_valuation` reads only valuation_percentile_self + earnings_yield/real_yield_10y; populating pe/pb changes no state and no published byte.
  Doc impact: CONTEXT.md "Valuation-input inertness" entry + AC4 clarification

- Q: Is a new ADR warranted under the three-of-three bar?
  A: One ADR. Scalar inputs + pure helper = 0/3 (no ADR); index-level vs per-A-share = ~2/3 consequence of existing granularity (no ADR); wire-but-degrade-to-None rather than fabricate target_price = 3/3 (ADR 0009).
  Rationale: degrade-to-None plumbing is hard to reverse, surprising ("a metric that never fires"), and the chosen one of three real alternatives (fabricate / drop / wire-degrade).
  Doc impact: ADR-0009

- Q: Any factual spec error vs. code requiring strike-through?
  A: Three minor errors struck through (never deleted): `_build_input` at opportunity_cmd.py:532 not "~559"; `target_price=None` at akshare_filing.py:83 not :84; `_BROAD_INDEX_DISPLAY` has 9 keys (a subset of the legulegu coverage), QDII/sector in separate maps and out of scope.
  Rationale: none contradict a load-bearing ADR or break the design; Verdict stays PASS.
  Doc impact: none (in-spec strike-throughs only)

- Q: Does `consensus_upside_pct` need disambiguation from the existing `_broker_consensus`?
  A: Yes — one line. `_broker_consensus` is broker rating sentiment (information-leg); `consensus_upside_pct` is a price-target valuation scalar.
  Rationale: similar names invite conflation; the distinction is load-bearing for the boundary.
  Doc impact: CONTEXT.md term `consensus_upside_pct` (distinction noted)
