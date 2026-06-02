# PROGRESS — `irc eval-funds`

Mode: spec · Project type: non-web · PR shape: A · Feature branch: `feat/eval-funds-command`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused

**STATUS: COMPLETE ✅** — all phases green; item merged; close-out PR open.

| id  | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅   | ⏭️    | ✅   | ✅     | ✅   | ✅    | ✅ | ✅     | ✅     | ✅        | ✅  | ✅    |

## Evidence cells (filled as phases pass)

- **001-spec** ✅ — `items/001-spec.md` (verbatim copy of the approved design)
- **001-grill** ⏭️ — `⏭️ user-grilled` (spec mode; orchestrator must not auto-invoke grill)
- **001-plan** ✅ — `items/001-plan.md` (Opus writing-plans; commit `790d5ff`; 5 tasks / 33 steps; TDD-ordered; grounded in real signatures)
- **001-branch** ✅ — `claude/eval-funds-command-001` (off `feat/eval-funds-command`)
- **001-impl** ✅ — commits `ec332ca`→`176dc1b`→`353e7aa`→`fa86a45`→`eb24fec`; 8 new tests; diff = exactly the 10 planned files. **Verified:** `tests/opportunity/test_fund_eval.py + tests/commands/test_fund_eval_cmd.py + test_opportunity_cmd.py + test_build_input_fallback.py` → **58 passed**. Full suite: 2651 passed / 7 failed / 36 skipped — the **7 failures are pre-existing** (proven: they fail identically on base `feat/eval-funds-command`; incl. `test_eval_single_stage_data` = the ingest-halt non-goal). Impl deviations (both test-only, sound): (a) fixed monkeypatch target `opportunity_cmd.populate_inputs`→`inputs_build.populate_inputs` post-extraction; (b) integration test seeds `cn_etf/cn_on_exchange` (passive quality path) for the core_dca case, since active funds' `aum_stability_pct` is NaN in schema → `weak` (honest, per spec §6).
- **001-drift** ✅ — `items/001-drift.md` (Verdict: PASS; 33/33 steps verified vs real diff; 0 unimplemented, 0 functional scope-creep; 3 test-scaffolding divergences accepted; plan amended `2272b15`,`6e93b8b`)
- **001-PR** ✅ — [PR #91](https://github.com/snowshine0216/investment-research-copilot/pull/91) (base `feat/eval-funds-command`); `items/001-ship.md`
- **001-verify** ✅ — `items/001-verify.md` (Verdict: PASS; real `uv run irc eval-funds` on 10 cached ids; md+json written; honesty invariant confirmed live: no-NAV/no-snapshot fund → `core_dca=False`, `missing_constituent_snapshot`, no crash; commit `edf2e95`)
- **001-review** ✅ — `items/001-review.md` (Verdict: PASS-WITH-NITS; from `/ship` steps 8+9; 4 latent bugs fixed pre-push `9ad77a2`)
- **001-pr-review** ✅ — `items/001-pr-review.md` (Verdict: PASS-WITH-NITS; `/code-review` on PR #91 → [comment](https://github.com/snowshine0216/investment-research-copilot/pull/91#issuecomment-4592319230); 3 nits + 2 deferred pre-existing; zero new bugs; commit `d045a68`)
- **001-fix** ✅ — `items/001-fix.md` (0 post-ship fix rounds — exit contract met first pass; 4 latent bugs were fixed pre-push during ship; remaining nits + 2 pre-existing items non-blocking)
- **001-merge** ✅ — PR #91 squash-merged into `feat/eval-funds-command` as commit `7c6a605` (`gh pr merge --squash --delete-branch`; sub-branch deleted). All pre-merge gates passed; base non-protected.

## Notes

- Column `QA` omitted from the table: non-web project → `/verify` is the XOR branch.
- Feature branch pre-existed with the design doc committed (commit `037fa19`); not synthesized.

---

## Final status (Phase 3 — close-out)

**Run:** `irc eval-funds` targeted fund-evaluation command · mode **spec** · N=1 · project type **non-web** · PR shape **A**.

### Outcome

- **Items merged:** 1 / 1 (001).
- **Items SKIPPED / BLOCKED:** none.
- **Item PR:** #91 — squash-merged into `feat/eval-funds-command` as `7c6a605`.
- **Feature branch:** `feat/eval-funds-command`
- **Feature-branch PR:** https://github.com/snowshine0216/investment-research-copilot/pull/92  (base `main`)
- **Merged into protected branch:** no (PR #92 left **open** for user review — no protected-branch opt-in was given).

### Phase 3 gates

- Workflow-completeness audit: PASS — all 5 verdict artifacts well-formed; no `qa` file (non-web ✓); no `grill` file (spec mode ⏭️ ✓).
- Full test suite (merged feature branch `7c6a605`): **2656 passed / 36 skipped / 7 failed**. The 7 failures are **pre-existing** (proven identical on base `feat/eval-funds-command`; incl. `test_eval_single_stage_data`, which fails on the `ingest` halt this command exists to route around). **Zero in-branch failures.**
- ruff: all new/modified files clean. (124 tree-wide errors are pre-existing, entirely in files this work never touched — e.g. `scoring/gold_score.py`, `tests/opportunity/test_states.py`.)
- Behavioral `/verify`: PASS — real `uv run irc eval-funds` exercised; honesty invariant confirmed live.

### Quality verdicts (per-item)

| Gate | Verdict |
|------|---------|
| drift | PASS (33/33 plan steps verified vs real diff) |
| ship review (/ship 8+9) | PASS-WITH-NITS (4 latent edge bugs fixed pre-push `9ad77a2`) |
| verify (/verify, non-web) | PASS |
| pr-review (/code-review #91) | PASS-WITH-NITS (zero new bugs) |
| fix rounds (post-ship) | 0 (exit contract met first pass) |

### Follow-up work (filed to `TODOS.md` → Reliability)

- `states.py` `derive_thesis_from_evidence`: `ActiveFundSnapshot` branch lacks the dual-leg (data+information) coverage check the `FundLevelSnapshot` branch has — pre-existing; `eval-funds` makes it more visible. Out of scope here (command reuses the classifier verbatim, spec §1).
- `fundamentals/snapshot_cache.py` `load_active_fund_cache`: swallows `OSError`/`ValueError` without logging — corrupt cache indistinguishable from "not fetched".

### Out of scope (per spec §2 — not failures)

- The `ingest` exit-1 halt is **not** fixed (tracked separately) — `eval-funds` deliberately routes around it.

### Next step for the user

Review **PR #92** (`feat/eval-funds-command` → `main`) and merge when ready. Try the command:
`uv run irc eval-funds --ids "<fund ids from data/fundamentals/<quarter>/active_fund/>"`.
