# Progress tracker

| id  | title | spec | grill | plan | branch | impl | drift | ship | verify | pr-review | fix | merge |
|-----|-------|------|-------|------|--------|------|-------|------|--------|-----------|-----|-------|
| 001 | contributing-dimensions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏭️ | ✅ |
| 002 | citation-data-model | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 003 | active-fund-constituent-layer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
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

## Per-item merge log

- **001 contributing-dimensions** — PR [#55](https://github.com/snowshine0216/investment-research-copilot/pull/55) squash-merged 2026-05-22 as `4cb4b9b` on `autodev/thesis-cards-evidence-gap`. Inline review PASS-WITH-NITS, verify PASS (8/8 ACs), pr-review PASS-WITH-NITS. Fix loop skipped (zero blockers, zero latent bugs).
- **002 citation-data-model** — PR [#56](https://github.com/snowshine0216/investment-research-copilot/pull/56) squash-merged 2026-05-22 as `5bc4b95`. 18-task plan; 7 impl commits + 1 fix commit. Drift PASS-WITH-NOTES (27/27 ACs verified), inline review PASS-WITH-NITS, verify PASS-WITH-NOTES (26/27 ACs — AC21 documented as ⚠️), pr-review PASS-WITH-NITS. Fix loop ran once: closed real latent bug (`fetch_types_attempted` schema gap on `OpportunityRow`); inline reviewer's `select_citations` identity-vs-equality flag was refuted by pr-review (mutually-exclusive data/info candidate sets). Includes new ADR `docs/adr/0001-citation-data-model.md`.
- **003 active-fund-constituent-layer** — PR [#57](https://github.com/snowshine0216/investment-research-copilot/pull/57) squash-merged 2026-05-23 as `3fbf50c`. 24-task plan + 4 fix rounds. Drift PASS (after Task 22 wiring amendment). Inline review PASS-WITH-NITS, /verify PASS (31/31 ACs), /code-review PASS-WITH-NITS (after closing 3 latent bugs). New ADR `docs/adr/0002-active-fund-fetch-engine.md` locks the cache/probe/budget/forbidden-pair contracts. Fix rounds closed: (1) `fundamentals→opportunity` import cycle (relocated 4 types to `fundamentals/types.py` with re-exports); (2) `--limit`/`--rebuild-fundamentals` not threaded into `_build_rows`; (3) preflight budget gate + advisory lock + resumable state defined-but-not-called (drift checker missed; surfaced by adversarial review); (4) 3 latent parser bugs from /code-review (all-NaN quarter, `_BJ_TOKENS` `'京'` collision, 5xxx ETF codes routed to UNKNOWN). Spec deviation noted: spec located `LookthroughTarget`/`ConstituentAnalysis`/`ThesisEvidence` in `opportunity/types.py` — ran into an architecture cycle, relocated to `fundamentals/types.py` with re-export preserving documented import path.

## Artifacts (populated as each item completes)

- 001: `items/001-spec.md`, `items/001-grill.md`, `items/001-plan.md`, `items/001-drift.md`, `items/001-ship.md`, `items/001-verify.md`, `items/001-review.md`, `items/001-pr-review.md`
- 002: `items/002-*.md`
- 003–010: same pattern
