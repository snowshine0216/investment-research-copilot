Verdict: PASS
Subagent: opus
Questions resolved: 10
Docs touched:
  - CONTEXT.md (commit ad2f86d)
  - docs/2026-06-02-narrative-coverage-markdown/items/001-spec.md (commit ad2f86d)
Spec refined: items/001-spec.md (commit ad2f86d)

## Resolved decisions
- Q: Is narrative autobuild the same concept as opportunity autobuild, or a variant deserving its own naming?
  A: Same concept on a different command surface; gets its own env var IRC_NARRATIVE_AUTOBUILD (default "1"), independently togglable from IRC_OPPORTUNITY_AUTOBUILD.
  Rationale: independent toggling is a real operator need; the cache-only inversion must be recorded, not silent drift.
  Doc impact: CONTEXT.md term (new "Narrative active-fund autobuild" + amended "Analyze deepens, then reads cache")

- Q: Should the narrative autobuild path also run evaluate_policy_b + rule-2.5 fund-level evidence stamping like opportunity_cmd.py:939-954?
  A: No — keep the minimal posture for item 001; supply the snapshot only and let build_opportunity_row -> derive_thesis_from_evidence consume it.
  Rationale: narrative report has no dual-coverage gate / H3 partition / publishability decision, so Policy B gap-codes have no consumer; thesis_state stays set ONLY by derive_thesis_from_evidence (ADR 0003). Foreign-heavy funds lose only the rule-2.5 fund-level citation legs (cosmetic completeness, not correctness). Rule-2.5 citation parity is a documented follow-up.
  Doc impact: CONTEXT.md term (new "Narrative path is Policy-B-free")

- Q: Does the rule-2.5 deferral warrant an ADR?
  A: No — three-of-three fails (not hard to reverse, not surprising, no novel trade-off; strict subset of ADR 0003 §7).
  Rationale: CONTEXT.md boundary note + spec Resolved-decisions section suffice.
  Doc impact: none

- Q: Does flipping "narrative --analyze is cache-only" -> "auto-builds" need an ADR?
  A: No — CONTEXT.md amendment instead.
  Rationale: reversible via IRC_NARRATIVE_AUTOBUILD=0, mirrors ADR 0002's opportunity autobuild, no novel trade-off.
  Doc impact: CONTEXT.md ("Analyze deepens, then reads cache" amendment)

- Q: "active fund" / cn_equity_fund vs index LOF terminology drift (resolved-Q #1)?
  A: No conflict to fix — lookthrough.py:88 routes cn_equity_fund -> active_fund pipeline-wide; the narrative gate inherits the same benign over-inclusion as opportunity.
  Rationale: spec is consistent with the established routing contract and CONTEXT.md.
  Doc impact: none

- Q: "shortlist" / "look-through" terminology drift?
  A: None — both match CONTEXT.md "Narrative selector" / "Screen -> analyze gate" and the code.
  Rationale: spec uses the canonical terms.
  Doc impact: none

- Q: Cache-presence probe — reuse _load_latest_active_fund_cached (latest-quarter, private to opportunity_cmd.py) or probe the resolved quarter?
  A: Probe the resolved analyze-context quarter via the public load_active_fund_cache(iid, quarter, data_dir).
  Rationale: probe and consumer must agree on the quarter for idempotence (AC8); avoids a private cross-command import.
  Doc impact: spec strike-through on Acceptance #2

- Q: FetchBudgetExceeded / _fetch_budget — reuse or re-define?
  A: Reuse the public FetchBudgetExceeded class and _fetch_budget() helper; pre-build estimate = n_eligible_missing x (constant x TOP_N_DEFAULT) vs IRC_FETCH_BUDGET; no narrative-specific knob.
  Rationale: legitimate shared seam; single locus for the budget concept (already glossaried under "Preflight fetch budget").
  Doc impact: none

- Q: Does the corrected error string over-promise autobuild?
  A: Tighten so it does not imply autobuild rescues the None-context case (it fires exactly when the context cannot open); name irc ingest + a data/fundamentals/ quarter, drop the irc fundamentals snapshot instruction.
  Rationale: autobuild cannot start when _open_analyze_context returns None; Acceptance #9 grep assertions unchanged.
  Doc impact: none beyond the Resolved-decisions note

- Q: build_snapshot return type vs write_active_fund_cache input (Acceptance #5)?
  A: No change — for kind == "active_fund" build_snapshot returns ActiveFundSnapshot; the isinstance guard mirrors opportunity_cmd.py exactly.
  Rationale: defensive shape is correct as written.
  Doc impact: none
