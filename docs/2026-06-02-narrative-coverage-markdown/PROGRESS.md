# PROGRESS — narrative coverage gap + markdown

Legend: ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused/blocked

**Mode:** backlog · **Project type:** non-web (verify, not qa) · **PR shape:** A · **Authoring:** full Opus
**Feature branch:** `autodev/narrative-coverage-markdown-feature` (synthesized off `main`; left open for user to land)
**Item order:** 001, 002, 003, 004 (locked via dependency scan)

| id  | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
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

## Run-level
| gate | status |
|------|--------|
| run-doc-sync | ⏳ |
| run-final-verify | ⏳ |
| run-close-out | ⏳ |

## Notes / decisions
- 2026-06-02: Run created. Scope = 4 consolidated items (user choice). Full Opus authoring (user choice).
- 2026-06-02: `main` is protected + default → synthesized feature branch; no merge-to-main opt-in this turn.
