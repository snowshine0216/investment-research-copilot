# Progress tracker

| id  | title | spec | grill | plan | branch | impl | drift | ship | verify | pr-review | fix | merge |
|-----|-------|------|-------|------|--------|------|-------|------|--------|-----------|-----|-------|
| 001 | contributing-dimensions | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 002 | citation-data-model | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 003 | active-fund-constituent-layer | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 004 | live-verify-fund-announcement-em | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 005 | per-asset-class-citation-coverage | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 006 | failure-mode-and-policy-b | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 007 | memo-and-discipline-renderers | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 008 | integration-test-sweep | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 009 | citation-gate-block-mode | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 010 | duckdb-fund-holdings-ingest | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

Legend: ⏳ = pending, 🔄 = in progress, ✅ = done, ⏭️ = skipped (mode / not applicable), ⚠️ = blocked.

## Notes on the `verify` column

This project is a non-web Python CLI. Each item's post-ship verification uses `/verify` (entry-point smoke + acceptance walkthrough), NOT `/qa` (which requires a browser-driven web app). The verdict file is `items/<id>-verify.md`.

## Notes on the `review` column

Per `/ship`'s steps 8+9, the in-flow review verdict is captured inline by `/ship` and lands in `items/<id>-review.md`. There is no separate review subagent dispatch. The `pr-review` column captures `/code-review` on the open PR (a distinct surface from `/ship`'s inline review).

## Outcome

(populated at run close-out — feature branch left open for user to review/merge into `main`)

## Artifacts (populated as each item completes)

- 001: `items/001-spec.md`, `items/001-grill.md`, `items/001-plan.md`, `items/001-drift.md`, `items/001-ship.md`, `items/001-verify.md`, `items/001-review.md`, `items/001-pr-review.md`
- 002: `items/002-*.md`
- 003–010: same pattern
