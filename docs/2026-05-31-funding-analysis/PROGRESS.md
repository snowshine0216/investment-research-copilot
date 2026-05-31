# PROGRESS — Funding analysis enhancements

Legend: ⏳ pending · 🔄 in-progress · ✅ pass · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

Project type **non-web** → `verify` column is live; `QA` column is ⏭️ for every row (XOR).

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ✅ | ✅ | ✅ claude/funding-analysis-001 | ✅ a850f42 | ✅ | ✅ #84 | ⏭️ | ✅ | ✅ | ✅ | ✅ 0 rounds | ✅ 22baf17 |
| 002 | ✅ | ✅ | ✅ | ✅ claude/funding-analysis-002 | ✅ bee1a41 | ✅ 915f93f | ✅ #85 | ⏭️ | ✅ | ✅ | ✅ | ✅ 0 rounds | ✅ d3f48cb |
| 003 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 004 | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
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
- 002 spec: `items/002-spec.md` (commit 5242f3a) — 9 acceptance criteria. Makes pe/pb/consensus_upside live in `classify_valuation`; `core_dca` cheap-half becomes fundamental-aware (the gate already requires cheap-AND-intact). Key finding: 001's AC4 inertness lock must be **updated** (not deleted) — 002 makes a populated row's valuation_state change by design (AC7). All-None case stays `evidence_insufficient` (ADR 0009 degrade-to-none). Grill targets: threshold values (CHEAP_UPSIDE=0.20 / RICH_UPSIDE=-0.10), threading mechanism for the core_dca block, ADR-escalation judgment.
- 002 grill: `items/002-grill.md` (PASS, commits ff9ec46/a9aabd6) — 6 Qs resolved; no new ADR (core_dca gating ~1-2/3, reversible + already owned by ADR 0009 → CONTEXT.md update suffices). **Catch 1:** belt-and-suspenders threading was wrong — AC3 forbids `classify_valuation` moving toward more-expensive, so notch-refusal can't block `core_dca` on an already-cheap percentile; the explicit `compose_opportunity_state(valuation_fundamental=...)` param is the SINGLE mechanism (valuation_state stays cheap; only opportunity_state falls through). **Catch 2:** AC7 — 001's lock test row has flat price→percentile 1.0→very_expensive, so its break is annotation-only; AC7 now requires annotation assertion + a second genuinely-cheap row. All 4 load-bearing invariants (H3/SAME-3, Policy B vs thesis_state, all-None degrade, AC4 lock update) verified against code.
- 002 plan: `items/002-plan.md` (commit 5e70f31) — 10 tasks, ~55 TDD steps. New pure helper module `src/irc/opportunity/valuation_fundamental.py` (states.py already 564 lines > budget). Constants CHEAP_UPSIDE=0.20 / RICH_UPSIDE=-0.10. Single threading param `compose_opportunity_state(valuation_fundamental=...)`. Tests: new `test_valuation_fundamental_anchor.py` (22), +6 in `test_states.py`, evolved 001 lock in `test_inputs_loader.py` (renamed `test_population_consumes_consensus_upside_per_item_002` + 2nd cheap-percentile row; grep guard for old name). No CONTEXT/ADR edits (grill already did them).
- 002 ship: `items/002-ship.md` PR #85 (base feature branch); review `items/002-review.md` PASS-WITH-NITS (1 latent bug — neutral-band reason printed "上行空间" for negative upside — found by /ship steps 8+9, FIXED pre-push commit 3ef0379 with regression test; adversarial CLEAN; 3 nits→TODOS). verify `items/002-verify.md` PASS (all ACs exercised directly: dormant all-None, neutral-negative→下行空间, rich→core_dca blocked, AC8 byte-identical). pr-review `items/002-pr-review.md` PASS (/code-review on #85, 1 cosmetic nit→TODOS, 0 blockers/latent). Fix loop: 0 rounds (no blockers/latent). CHANGELOG [Unreleased] + 4 TODOS nits (docs commits d754e5d + this).
- 002 impl: 9 commits (55877c7→bee1a41) on claude/funding-analysis-002. New module `src/irc/opportunity/valuation_fundamental.py` (68 lines); states.py +31. tests/opportunity 457 passed; full suite 2516 passed / 8 failures (all 8 pre-existing, fail identically on base — tests/commands, tests/integration, tests/evals/test_architecture.py DAG cycle, tests/test_e2e_full_pipeline), 0 new. Ruff clean on all item-002 files. No plan deviations. 001 AC4 lock renamed→`test_population_consumes_consensus_upside_per_item_002` (provenance + ADR 0009 cite preserved).
