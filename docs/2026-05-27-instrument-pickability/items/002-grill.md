Verdict: PASS

Subagent: opus
Questions resolved: 13
Docs touched:
  - CONTEXT.md (commit 0135373)
  - docs/2026-05-27-instrument-pickability/items/002-spec.md (commit 0135373)
Spec refined: items/002-spec.md (commit 0135373)

## Resolved decisions

- Q: Spec AC10 claims 8 existing `IRC_*_BEGIN/END` marker pairs. Is that factual?
  A: No. Only 5 marker pairs exist in src/ (`IRC_PICKS_TABLE_*`, `IRC_EVIDENCE_GAP_*`, `IRC_EXECUTION_LINES_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*`). The phantom `IRC_FX_QDII_*`, `IRC_ROLE_BUCKET_*`, `IRC_EXECUTION_DRIFT_*` are non-existent. Spec corrected via strikethrough on AC10.
  Rationale: Plan-stage engineer would have hit non-existent imports. Fact-checking earns now is cheap.
  Doc impact: spec strikethrough; no CONTEXT.md change.

- Q: Spec AC10 claims `memo/auditor.py` recognises markers structurally. True?
  A: No. `auditor.py` is an LLM content reviewer parsing 审核通过/审核未通过 verdict tokens. `grep -n "IRC_" src/irc/memo/auditor.py` returns zero. The actual lockdown mechanism is synthesizer prompt + publishable-set lockdown two-run byte equality. AC10 strikethrough corrects this.
  Rationale: Item 001 didn't extend the auditor either — pattern is "synthesizer prompt + lockdown."
  Doc impact: spec strikethrough; no auditor change needed.

- Q: Is AC4 (`i < j` after `instrument_id` sort) in conflict with AC8 (render order `overlap_pct DESC`)?
  A: No conflict. AC4's `i < j` is internal canonicalization (each pair once); AC8's three-key sort is observable render order. Both coexist. One-line clarification added to AC4.
  Rationale: Distinguishes deduplication invariant from render order — both load-bearing.
  Doc impact: spec AC4 clarification.

- Q: How does the metric handle a fund with fewer than 10 valid holdings?
  A: `topN(A) = A.constituent_analyses` after rank sort, no padding when `len(A.constituent_analyses) < CONCENTRATION_TOP_N`. Symmetry preserved because intersection is over identity set, not cardinality. Added AC1 sub-clause + test requirement.
  Rationale: AkShare returns 10 by default but partial/corrupted fixtures hit this branch.
  Doc impact: spec AC1 clarification; CONTEXT.md `weighted_overlap_pct` entry.

- Q: Is `CONCENTRATION_OVERLAP_PCT_THRESHOLD = 30.0` in percent units or fraction units?
  A: Percent units (0–100), matches `weight_pct` unit per ADR 0002 §4. NOT a fraction like `qdii_max_premium_pct = 0.05`. Inline unit comment added to AC3.
  Rationale: Three precedent constants have different units (`FOREIGN_HEAVY_THRESHOLD = 0.50` fraction; `qdii_max_premium_pct = 0.05` fraction; `CONCENTRATION_OVERLAP_PCT_THRESHOLD = 30.0` percent) — easy plan-stage confusion.
  Doc impact: spec AC3 unit clarification; CONTEXT.md metric entry pins unit.

- Q: When is `overlap_pct` rounded — at construction or at render?
  A: At construction (inside `ConcentrationPair` factory). Pins determinism by construction, not by render-time discipline. Updated AC5.
  Rationale: Render-time-only rounding is brittle to future renderer additions.
  Doc impact: spec AC5 clarification; CONTEXT.md `ConcentrationPair` entry.

- Q: Pair vs cluster — is 6 lines for a 4-pick cluster (`C(4,2)`) noisy?
  A: Keep pairs. 6 lines is operator-readable; clustering hides asymmetric structure. No change.
  Rationale: Stress-tested against actual 2026-05-27 CPO cluster of 4 picks; fits §6 without sprawl.
  Doc impact: none.

- Q: Should the analytic cover passive ETFs that have known holdings via `lookthrough_target`?
  A: No, V1 active-fund-only. Passive ETF overlap is an `tracked_index` identity check (two CSI 300 ETFs are 100% by construction) — different signal, defer to F2. NG5 rationale strengthened.
  Rationale: CONTEXT.md "Passive ETF / tracked index" excludes them from drill-through; `OpportunityRow.constituent_analyses != ()` predicate naturally excludes them via `build_snapshot` dispatch.
  Doc impact: spec NG5 strengthening; no scope change.

- Q: Where do `IRC_CONCENTRATION_*` marker constants live?
  A: Module-top in `src/irc/memo/concentration.py` — producing-module pattern, mirrors `macro_pillar.py`. NOT in `template.py`. Updated AC9.
  Rationale: Concentration is a §6 sub-block produced at memo-cmd time, not a skeleton-level section.
  Doc impact: spec AC9 clarification; CONTEXT.md marker entry.

- Q: Is `aliases.py` the right shape mirror for `concentration.py`?
  A: Yes. Both are pure modules: tuple-in / frozen-dataclass-tuple-out, no I/O, single `irc.opportunity.types` import. Explicit Constraint added.
  Rationale: Tier-1 import contract load-bearing for renderer module independence (no cycles).
  Doc impact: spec Constraints addition; CONTEXT.md tier-1 contract entry updated.

- Q: Where does `op_rows_by_id` come from in `_compose_concentration_lines`?
  A: Built once at the hook call-site in `memo_cmd.py` as `{r.instrument_id: r for r in opportunity_rows}`. NOT inside the pure helper, NOT a global, NOT threaded onto `PickRow` (breaks item 003 column lock per NG3). FP-explicit clarification added to AC7.
  Rationale: "Dependencies visible in the function signature" per CLAUDE.md FP guidance.
  Doc impact: spec AC7 clarification.

- Q: Is "extend existing publishable-set lockdown" the right two-run-byte-equality strategy?
  A: Yes. Item 008's pipeline-level invariant covers `memo.md`; the new `IRC_CONCENTRATION_*` block is byte-stable if the two-run identical-inputs invariant from item 008 covers it. No new fixture. Clarified AC13.
  Rationale: Avoid lockdown-fixture sprawl; existing baseline is single source of regression truth.
  Doc impact: spec AC13 clarification.

- Q: Is an ADR warranted?
  A: No. Three-of-three test: hard-to-reverse LOW, surprising-without-context LOW, real-tradeoff MEDIUM. Two of three are LOW; threshold not met. CONTEXT.md glossary entries are sufficient.
  Rationale: Item 001's very-similar `IRC_EVIDENCE_GAP_*` marker addition got CONTEXT.md-only treatment; only the row-level `advisory_gaps` shape change earned ADR 0005.
  Doc impact: CONTEXT.md entries (`IRC_CONCENTRATION_BEGIN/END`, `weighted_overlap_pct`, `ConcentrationPair`); no ADR.
