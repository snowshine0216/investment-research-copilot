# PROGRESS — narrative coverage gap + markdown

Legend: ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused/blocked

**Mode:** backlog · **Project type:** non-web (verify, not qa) · **PR shape:** A · **Authoring:** full Opus
**Feature branch:** `autodev/narrative-coverage-markdown-feature` (synthesized off `main`; left open for user to land)
**Item order:** 001, 002, 003, 004 (locked via dependency scan)

| id  | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ✅ | ✅ | ✅ `claude/narrative-coverage-markdown-001` | ✅ c70ba52 | ✅ 1269290 | ✅ #95 | ⏭️ | 🔄 | ✅ | 🔄 | ⏳ | ⏳ |
| 002 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 003 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
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

## Run-level
| gate | status |
|------|--------|
| run-doc-sync | ⏳ |
| run-final-verify | ⏳ |
| run-close-out | ⏳ |

## Notes / decisions
- 2026-06-02: Run created. Scope = 4 consolidated items (user choice). Full Opus authoring (user choice).
- 2026-06-02: `main` is protected + default → synthesized feature branch; no merge-to-main opt-in this turn.
