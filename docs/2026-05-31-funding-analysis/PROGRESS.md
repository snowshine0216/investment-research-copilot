# PROGRESS — Funding analysis enhancements

Legend: ⏳ pending · 🔄 in-progress · ✅ pass · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

Project type **non-web** → `verify` column is live; `QA` column is ⏭️ for every row (XOR).

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ✅ | ✅ | ✅ claude/funding-analysis-001 | ✅ a850f42 | ✅ | 🔄 | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
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

- 001 spec: `items/001-spec.md` (commit d5439f6) — 7 acceptance criteria. Key correction: target_price unavailable from `stock_research_report_em` (consensus_upside wired pure, None until Tushare/003); pe/pb via `stock_index_pe_lg`/`stock_index_pb_lg` at fund/index level.
- 001 grill: `items/001-grill.md` (PASS, commits 6956d23/0015e89) — created ADR 0009 (consensus-upside-degrade-to-none), added `consensus_upside_pct` to CONTEXT.md (ratio units). Proved pe/pb/upside are inert (no non-test reader) → 001 cannot touch any state classifier; AC4 has an inertness regression lock.
