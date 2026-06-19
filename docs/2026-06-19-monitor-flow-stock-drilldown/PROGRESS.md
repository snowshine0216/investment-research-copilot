# PROGRESS — Monitor flow-stock drill-down

**Mode:** spec · **Project type:** non-web (`/verify`) · **PR shape:** A · **Feature branch:** `monitor-flow-stock-drilldown`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (pre-completed) · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ⏭️ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Evidence cells

- **001 spec** ⏭️ — user-provided, copied verbatim → [items/001-spec.md](items/001-spec.md)
- **001 grill** ⏭️ — user-grilled; ADR 0019 + CONTEXT flow glossary committed on this branch (orchestrator must not auto-invoke)
- **001 plan** ⏳ — Opus `superpowers:writing-plans` → `items/001-plan.md`

## Notes

- Single IN-scope item (N=1). The spec's 4 TDD slices become plan tasks under `items/001-plan.md`.
- QA column omitted — non-web project uses `/verify` (XOR).
- Final landing: Phase 3 opens `monitor-flow-stock-drilldown → main` PR, left OPEN for the user (protected base, no opt-in).
