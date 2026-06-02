# PROGRESS — narrative coverage gap + markdown

Legend: ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused/blocked

**Mode:** backlog · **Project type:** non-web (verify, not qa) · **PR shape:** A · **Authoring:** full Opus
**Feature branch:** `autodev/narrative-coverage-markdown-feature` (synthesized off `main`; left open for user to land)
**Item order:** 001, 002, 003, 004 (locked via dependency scan)

| id  | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ✅ | ✅ | ✅ `claude/narrative-coverage-markdown-001` | ✅ c70ba52 | ✅ 1269290 | ✅ #95 | ⏭️ | ✅ | ✅ | ✅ | ✅ 0 rounds (P0 fixed pre-push) | ✅ f81d6f1 |
| 002 | ✅ | ✅ | ✅ | ✅ `claude/narrative-coverage-markdown-002` | ✅ 9620ea4 | ✅ db009cd | ✅ #96 | ⏭️ | ✅ | ✅ | ✅ | ✅ 1 inline nit (pre-push P0 layer-fix) | ✅ fd624c5 |
| 003 | ✅ | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 004 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

QA column is ⏭️ for all items (non-web project — `/verify` is the post-ship gate).

## Items
- 001 — Active-fund autobuild in `narrative --analyze` + fix misleading error string (handoff #1+#6)
- 002 — Passive-ETF fund-level + theme_report wiring into `analyze_fund` (handoff #2)
- 003 — Markdown report enrichment: M1 evidence prose/citations + M2 product metrics (handoff #3+#4)
- 004 — Suppress action-triad / triggers on `insufficient` rows (handoff #5)

## Artifact links (filled as phases complete)
<!-- items/<id>-spec.md, -grill.md, -plan.md, -drift.md, -ship.md, -verify.md, -review.md, -pr-review.md -->
- 001-spec: [items/001-spec.md](items/001-spec.md) (commit c554491; 11 acceptance criteria; 1 open Q flagged for planner — Policy B / rule-2.5 evidence stamping, minimal posture chosen)
- 001-grill: [items/001-grill.md](items/001-grill.md) (commit b56ff2e; Verdict PASS; 10 Q resolved; CONTEXT.md +2 terms; no new ADR; Policy-B-free minimal posture confirmed — rule-2.5 parity is a documented follow-up)
- 001-plan: [items/001-plan.md](items/001-plan.md) (commit b8cbbb1; 10 tasks / ~46 steps; all 11 ACs → tests; new `src/irc/commands/narrative_autobuild.py` helper; effects-at-edges, analyze_fund stays read-only; 2 spec-gap judgment calls flagged for reviewer)
- 001-drift: [items/001-drift.md](items/001-drift.md) (commit 1269290; Verdict PASS; 0 findings; 5 invariants verified vs diff)
- 001-ship: [items/001-ship.md](items/001-ship.md) → PR [#95](https://github.com/snowshine0216/investment-research-copilot/pull/95) (base=feature branch; no VERSION bump; 8 pre-existing test failures noted, 0 in-branch)
- 001-review: [items/001-review.md](items/001-review.md) (Verdict PASS via /ship 8+9; P0 + P1s found & fixed pre-push — commits c3463b5/8d4c7e5/3eee793; re-review CLEAN) · pre-push findings: [items/001-ship-blocked.md](items/001-ship-blocked.md)
- 001-verify: [items/001-verify.md](items/001-verify.md) (Verdict PASS; real-CLI offline smoke — corrected error string rc=2 no-traceback, kill-switch, no `基金概况`; network-leg ACs test-backed)
- 001-pr-review: [items/001-pr-review.md](items/001-pr-review.md) (Verdict PASS-WITH-NITS; [PR #95 comment](https://github.com/snowshine0216/investment-research-copilot/pull/95#issuecomment-4600948867); 2 nits — `_fetch_budget` private import [grill-sanctioned], test import style; 0 bugs)
- 001-fix: 0 rounds — post-ship verdicts all clean; the P0/P1 blockers were fixed in the pre-push /ship review round.
- 002-spec: [items/002-spec.md](items/002-spec.md) (commit e40cb27; 14 ACs; passive eligibility on LookthroughTarget.kind + qdii; passive nav-snapshot autobuild edge; **theme_report sourcing deferred** — FundLevelSnapshot branch never reads it, so `None` recovers robots_report; flagged as bounded follow-up)
- 002-grill: [items/002-grill.md](items/002-grill.md) (commits f1deb2e/0939f6f; Verdict PASS; 8 Q; theme_report=None confirmed via thesis_evidence.py:348-373; 2 spec corrections — passive autobuild needs instrument index (not ShortlistRow); CONTEXT.md +3 terms; no new ADR)
- 002-plan: [items/002-plan.md](items/002-plan.md) (commit 1f3e7f4; 10 tasks / ~50 steps; all 14 ACs → tests; unifies autobuild into `autobuild_narrative` w/ shared preflight FetchPlan [RD-7a]; widens build_opportunity_row snapshot annotation [RD-6a]; 3 judgment calls flagged)
- 002-drift: [items/002-drift.md](items/002-drift.md) (commit db009cd; Verdict PASS; 1 accepted deviation [direct OpportunityInput build] + plan amend; 251-line file NOTE; 8 invariants verified)
- 002-ship: [items/002-ship.md](items/002-ship.md) → PR [#96](https://github.com/snowshine0216/investment-research-copilot/pull/96) (base=feature; blast-radius tests 7 pre-existing-fail/1090 pass, 0 in-branch)
- 002-review: [items/002-review.md](items/002-review.md) (Verdict PASS-WITH-NITS; adversarial P0 REFUTED [table-fallback gaps force insufficient]; layer-inversion P0 + QDII dup + observability FIXED pre-push c98be90/d97b3e3; re-review P0=none) · [items/002-ship-blocked.md](items/002-ship-blocked.md)
- 002-verify: [items/002-verify.md](items/002-verify.md) (commit 746475e; Verdict PASS; 14 ACs — offline CLI+import-health+layering grep + 906 test-backed; 0 failures)
- 002-pr-review: [items/002-pr-review.md](items/002-pr-review.md) (Verdict PASS-WITH-NITS; [PR #96 comment](https://github.com/snowshine0216/investment-research-copilot/pull/96#issuecomment-4601702712); 1 nit [stale msg wording] — fixed inline; 0 bugs)
- 002-fix: 1 inline nit (budget-msg wording generalized to active+passive); the pre-push layer-inversion P0 + dup + observability were fixed in the /ship review round.
- 003-spec: [items/003-spec.md](items/003-spec.md) (commit 1a3bce2; 11 ACs; M1 prose from ThesisEvidence.summary + ConstituentAnalysis.one_line_view + citation_id-sorted footnote appendix; M2 surfaces product drivers; SAME-3 safe [report.py not an ADR-0004 §3 surface]; scorer-flooring = follow-up F-1, NOT changed; supporting edit threads metrics + constituent_analyses via _report_from_card)
- 003-grill: [items/003-grill.md](items/003-grill.md) (Verdict PASS; subagent opus; 6 RDs resolved; verified report.py is NOT an ADR-0004 §3 SAME-3 surface [appendix safe], active-fund 质量=weak is a scorer floor not signal [F-1]; CONTEXT.md +2 terms; spec +`## Resolved decisions` + 2 inline corrections [ADR-0004 §Consequences precedent; _report_from_card must receive inp for product metrics])

## Run-level
| gate | status |
|------|--------|
| run-doc-sync | ⏳ |
| run-final-verify | ⏳ |
| run-close-out | ⏳ |

## Notes / decisions
- 2026-06-02: Run created. Scope = 4 consolidated items (user choice). Full Opus authoring (user choice).
- 2026-06-02: `main` is protected + default → synthesized feature branch; no merge-to-main opt-in this turn.
- 2026-06-02: Item 001 MERGED into feature branch via squash PR #95 (commit f81d6f1). Pre-push /ship review caught a real P0 (FetchBudgetExceeded uncaught + con leak) — fixed before push. Post-ship: verify PASS, review PASS, pr-review PASS-WITH-NITS (2 nits). 8 pre-existing test failures on base (unrelated; verified by checkout).
- 2026-06-02: Item 002 MERGED into feature branch via squash PR #96 (commit fd624c5). Pre-push review: adversarial P0 REFUTED (table-fallback gaps force insufficient); real layer-inversion P0 + QDII dup + observability fixed before push; also removed a pre-existing `commands↔narrative` import cycle. Post-ship: verify PASS, review PASS-WITH-NITS, pr-review PASS-WITH-NITS (1 nit fixed inline). dag_acyclic_check unchanged vs base (no new cycle). Clean ff (feature pushed before sub-branch cut — no divergence).
