# PROGRESS — `irc eval-funds`

Mode: spec · Project type: non-web · PR shape: A · Feature branch: `feat/eval-funds-command`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused

| id  | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅   | ⏭️    | ✅   | ✅     | ✅   | ✅    | ✅ | 🔄     | ✅     | 🔄        | ⏳  | ⏳    |

## Evidence cells (filled as phases pass)

- **001-spec** ✅ — `items/001-spec.md` (verbatim copy of the approved design)
- **001-grill** ⏭️ — `⏭️ user-grilled` (spec mode; orchestrator must not auto-invoke grill)
- **001-plan** ✅ — `items/001-plan.md` (Opus writing-plans; commit `790d5ff`; 5 tasks / 33 steps; TDD-ordered; grounded in real signatures)
- **001-branch** ✅ — `claude/eval-funds-command-001` (off `feat/eval-funds-command`)
- **001-impl** ✅ — commits `ec332ca`→`176dc1b`→`353e7aa`→`fa86a45`→`eb24fec`; 8 new tests; diff = exactly the 10 planned files. **Verified:** `tests/opportunity/test_fund_eval.py + tests/commands/test_fund_eval_cmd.py + test_opportunity_cmd.py + test_build_input_fallback.py` → **58 passed**. Full suite: 2651 passed / 7 failed / 36 skipped — the **7 failures are pre-existing** (proven: they fail identically on base `feat/eval-funds-command`; incl. `test_eval_single_stage_data` = the ingest-halt non-goal). Impl deviations (both test-only, sound): (a) fixed monkeypatch target `opportunity_cmd.populate_inputs`→`inputs_build.populate_inputs` post-extraction; (b) integration test seeds `cn_etf/cn_on_exchange` (passive quality path) for the core_dca case, since active funds' `aum_stability_pct` is NaN in schema → `weak` (honest, per spec §6).
- **001-drift** ✅ — `items/001-drift.md` (Verdict: PASS; 33/33 steps verified vs real diff; 0 unimplemented, 0 functional scope-creep; 3 test-scaffolding divergences accepted; plan amended `2272b15`,`6e93b8b`)
- **001-PR** ✅ — [PR #91](https://github.com/snowshine0216/investment-research-copilot/pull/91) (base `feat/eval-funds-command`); `items/001-ship.md`
- **001-verify** 🔄 — `items/001-verify.md`  (non-web → `/verify` dispatched; `/qa` does NOT run)
- **001-review** ✅ — `items/001-review.md` (Verdict: PASS-WITH-NITS; from `/ship` steps 8+9; 4 latent bugs fixed pre-push `9ad77a2`)
- **001-pr-review** 🔄 — `items/001-pr-review.md`  (`/code-review` on PR #91 dispatched)
- **001-fix** —
- **001-merge** —

## Notes

- Column `QA` omitted from the table: non-web project → `/verify` is the XOR branch.
- Feature branch pre-existed with the design doc committed (commit `037fa19`); not synthesized.
