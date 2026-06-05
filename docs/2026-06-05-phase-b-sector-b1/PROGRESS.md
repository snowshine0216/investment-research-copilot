# PROGRESS — Phase B sector expansion (B1)

**Mode:** spec · **Project type:** non-web · **PR shape:** A · **Feature branch:** `claude/relaxed-jemison-629597`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ `claude/phase-b-sector-b1-001` | ✅ `8590eed` | ✅ | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

(non-web → `verify` column used; no `QA` column.)

## Notes

- **001-spec** ✅ — verbatim copy at [`items/001-spec.md`](items/001-spec.md) (user-authored design spec). Goal + Decisions + Out-of-scope present.
- **001-grill** ⏭️ — pre-completed (user-grilled). Spec mode: orchestrator must NOT auto-invoke grill.
- **001-plan** ✅ — [`items/001-plan.md`](items/001-plan.md) (Opus `writing-plans`, commit `6f8a1ee`). 10 tasks, 23 verification commands, strict TDD ordering. Confirmed threading chain `run_opportunity (opportunity_cmd.py:1434) → _build_rows (:699) → _build_input (inputs_build.py:15) → populate_inputs (inputs_loader.py:253) → _index_valuation_metrics (:154)`; `ValuationBucketsConfig` at `src/irc/schemas/valuation.py:33`.

## Item

- **001** — B1 data onboarding (activation OFF). Scope & nuances in [`MASTER-SPEC.md`](MASTER-SPEC.md) / [`MASTER-PLAN.md`](MASTER-PLAN.md).
