# PROGRESS — Spend / Balance Gate Phase 2

Mode: plan · Project type: non-web · PR shape: A
Feature branch: `autodev/spend-balance-gate-phase2-feature` (synthesized off `main`)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ⏭️ | ⏭️ | ⏭️ | ✅ | ✅ 561a981 | ✅ f9a36e4 | ✅ #119 | ✅ PASS | ✅ PASS-WITH-NITS | ✅ PASS-WITH-NITS | ✅ 5 rounds | ✅ 33df8d3 |

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
- PR: [#119](https://github.com/snowshine0216/investment-research-copilot/pull/119) (base = feature branch). ship artifact `items/001-ship.md`.
- review: `items/001-review.md` — PASS-WITH-NITS (captured inline from /ship steps 8+9). 4 blockers fixed pre-push (round 2): corrupt-JSON surfacing, utf-8 encoding, theme_research failed-page over-count, memo arg-mutation. Accepted limitations documented: concurrency TOCTOU, retry double-fold, Shape-B partial-billing-on-crash.
- VERSION unchanged (0.9.3) per project convention; CHANGELOG [Unreleased] Phase 2 entry added.
- verify: `items/001-verify.md` PASS — §15.3 convergence exercised end-to-end (RUN1 0.016 CNY seed → RUN2 0.0142 CNY after one folded actual; samples 0→1, avg 4000→3100). `irc --help` / `irc spend status` boot clean.
- pr-review: `items/001-pr-review.md` PASS-WITH-NITS (3 /code-review rounds on #119).
- **fix loop: 5 rounds.** r1 (drift): removed unrequested discover/research gates + implemented 12d search-unit ledger. r2 (ship review): corrupt-JSON surfacing, utf-8, failed-page over-count, memo arg-mutation. r3 (pr-review): single-instant today in 6 cmds + lazy neutral. r4 (pr-review): discover single-instant today. r5 (pr-review nit): opportunity return annotation.
- **Regression check:** 171 touched-scope tests pass; baseline failure set unchanged (2 pre-existing: opportunity_cmd_fund_level + test_architecture DAG cycle); no new failures. ruff clean on all touched paths.
- **pre-ship fix round 1** (`914fec4`, `2bb6205`): removed unrequested `preflight_gate` from discover/research (Q7 = recorder wiring, not gating); **implemented missing Task 12d search-unit counting** (`theme_research._count_search_units` → pipeline 3-tuple → `record_command_run(search_units=…)`) so the Tavily/Bocha/Jina/Brave ledger decrement lands — the §15.2 ledger-box proof. New tests: `test_research_search_units_flow_to_actuals_and_ledger`, `test_research_pipeline_returns_search_units`.
- (branch / impl / drift / ship / verify / review / pr-review / merge evidence appended here as they land)

---

## Final status — RUN COMPLETE (2026-06-06)

- **Mode:** plan · **Project type:** non-web · **PR shape:** A
- **Items merged:** 1 / 1 (001 → squash `33df8d3` into the feature branch)
- **Items SKIPPED:** 0 · **Items BLOCKED:** 0
- **Phase 3:** workflow-completeness audit PASS (all verdict artifacts present; grill/qa correctly absent); merged-branch build/test sanity PASS (`irc --help` boots, 75 core tests pass, ruff clean).
- **Regression:** no NEW failures vs the documented ~8-failure baseline (2 pre-existing remain: `test_opportunity_cmd_fund_level`, `test_architecture` DAG cycle).
- **Fix loop:** 5 rounds (2 pre-ship drift/review, 3 post-ship /code-review).

### Branches & PRs
- Feature branch: `autodev/spend-balance-gate-phase2-feature` (synthesized off `main`)
- Item PR: #119 — MERGED (squash `33df8d3`)
- **Feature-branch PR: #120** — OPEN into `main` (roll-up review surface)
- **Merged into protected branch: no** (PR #120 left open for user review — protected-base guardrail held; no merge opt-in this turn)

### Follow-ups (deferred, documented in items/001-review.md)
- Concurrency: JSON state read-modify-write assumes sequential invocation (self-heals next run); file-locking out of scope.
- Same-day-retry EWMA double-fold; Shape-B partial-billing on mid-pipeline crash — self-healing, low impact.
- Possible 12f enhancement: eval-funds/narrative record `history=[]` (no-op) — confirm whether they make paid LLM calls that should converge standalone.
