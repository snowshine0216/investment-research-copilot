# PROGRESS — Funding analysis enhancements

Legend: ⏳ pending · 🔄 in-progress · ✅ pass · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

Project type **non-web** → `verify` column is live; `QA` column is ⏭️ for every row (XOR).

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 002 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 003 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 004 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 005 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Run-level

| gate | status |
|------|--------|
| run-doc-sync | ⏳ |
| run-final-verify | ⏳ |
| run-close-out | ⏳ |

## Item titles

- 001 — Wire `target_price` consensus upside + populate pe/pb from AkShare
- 002 — Fundamental `valuation_state`; gate `core_dca` on cheap-AND-intact
- 003 — Pluggable CN data layer + Tushare fallback (gated live tests + README)
- 004 — Deterministic `compute_ratios()` → roe/debt_equity/gross_margin/fcf_yield
- 005 — Bull/bear debate behind `--adversarial` (`thesis_defend` half)

## Notes

- QA column ⏭️ for all rows: project is non-web (CLI/library). Verify is the post-ship verifier.
- Item order locked after dependency scan — see MASTER-PLAN.md `Item order:`.

## Artifact links (filled as cells go ✅)

_(spec/plan/grill/drift/ship/verify/review/pr-review verdict files land under `items/`)_
