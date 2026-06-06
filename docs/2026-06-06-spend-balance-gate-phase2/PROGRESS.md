# PROGRESS — Spend / Balance Gate Phase 2

Mode: plan · Project type: non-web · PR shape: A
Feature branch: `autodev/spend-balance-gate-phase2-feature` (synthesized off `main`)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ⏭️ | ⏭️ | ⏭️ | ✅ | ✅ 561a981 | ✅ f9a36e4 | 🔄 | ⏳ | ⏳ | ⏳ | ✅ pre-ship r1 | ⏳ |

## Notes

- **001 spec** ⏭️ — user-provided (inferred stub at `items/001-spec.md`).
- **001 grill** ⏭️ — user-authored input; plan mode never grills (`items/001-grill.md` intentionally absent).
- **001 plan** ⏭️ — user-provided (verbatim copy at `items/001-plan.md`).
- Project type **non-web** → post-ship verifier is `/verify` (no `/qa` task created).

## Artifact index (filled as phases complete)

- spec: `items/001-spec.md`
- plan: `items/001-plan.md`
- branch: `claude/spend-balance-gate-phase2-001` (off feature branch)
- impl: 21 commits `08ef86f..561a981` (Tasks 1-12, TDD). tests/spend green (58 passed); 93 touched-unit tests green; no NEW failures vs baseline (2 pre-existing remain: opportunity_cmd_fund_level + test_architecture DAG cycle).
- drift: `items/001-drift.md` — round 1 FAIL → fix → re-check PASS (`f9a36e4`). 1 accepted plan amendment (Task 10 memo MemoOutput carrier).
- **pre-ship fix round 1** (`914fec4`, `2bb6205`): removed unrequested `preflight_gate` from discover/research (Q7 = recorder wiring, not gating); **implemented missing Task 12d search-unit counting** (`theme_research._count_search_units` → pipeline 3-tuple → `record_command_run(search_units=…)`) so the Tavily/Bocha/Jina/Brave ledger decrement lands — the §15.2 ledger-box proof. New tests: `test_research_search_units_flow_to_actuals_and_ledger`, `test_research_pipeline_returns_search_units`.
- (branch / impl / drift / ship / verify / review / pr-review / merge evidence appended here as they land)
