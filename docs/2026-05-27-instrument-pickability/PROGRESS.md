# PROGRESS — Instrument Pickability Fixes

**Run started**: 2026-05-27
**Mode**: backlog · **Project type**: non-web · **PR shape**: A · **Feature branch**: `autodev/instrument-pickability-feature`

| id | title | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 001 | broker_empty propagation | ✅ | ✅ | ✅ | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 002 | concentration panel | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 003 | QDII premium snapshot | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

**Run-level**: `run-doc-sync` ⏳ · `run-final-verify` ⏳ · `run-close-out` ⏳

## Legend

- ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft FAIL (in fix loop) · ⛔ refused gate · ⏭️ skipped per mode

## Evidence

- 001 spec: [items/001-spec.md](items/001-spec.md) — 13 acceptance criteria, no new ADR needed (thesis_state invariant preserved)
- 001 grill: [items/001-grill.md](items/001-grill.md) — Verdict: PASS, 13 questions resolved, ADR 0005 created, CONTEXT.md updated with `advisory_gaps` + `top_holdings_broker_thin` (commit `43a61bf`)
- 001 plan: [items/001-plan.md](items/001-plan.md) — 11 tasks, ~58 TDD steps, 4 new test files + 2 extensions (commit `ad99d94`)

## Notes

- Item order pending dependency-scan dispatch; provisional `001, 002, 003`.
- Project type non-web → post-ship XOR uses `/verify`, never `/qa`.
- Mode A → each item opens a sub-PR into `autodev/instrument-pickability-feature`; final rollup PR for the user to land.
