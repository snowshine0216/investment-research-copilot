# PROGRESS — Instrument Pickability Fixes

**Run started**: 2026-05-27
**Mode**: backlog · **Project type**: non-web · **PR shape**: A · **Feature branch**: `autodev/instrument-pickability-feature`

| id | title | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 001 | broker_empty propagation | ✅ | ✅ | ✅ | ✅ `claude/instrument-pickability-001` | ✅ `d4d613b` | ✅ | ✅ [#76](https://github.com/snowshine0216/investment-research-copilot/pull/76) | ✅ | ✅ | ✅ | ✅ 1 round | ✅ `f869bb1` |
| 002 | concentration panel | ✅ | ✅ | ✅ | ✅ `claude/instrument-pickability-002` | ✅ `44d0338` | ✅ | ✅ [#77](https://github.com/snowshine0216/investment-research-copilot/pull/77) | ✅ | ✅ | ✅ pass-with-nits | ✅ 2 rounds | ✅ `ad31c56` |
| 003 | QDII premium snapshot | ✅ | ✅ | ✅ | ✅ `claude/instrument-pickability-003` | ✅ `1929383` | ✅ | ✅ [#78](https://github.com/snowshine0216/investment-research-copilot/pull/78) | ✅ | ✅ | ✅ pass-with-nits | ✅ 2 rounds | ✅ `3b2a31f` |

**Run-level**: `run-doc-sync` 🔄 · `run-final-verify` ⏳ · `run-close-out` ⏳

## Legend

- ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft FAIL (in fix loop) · ⛔ refused gate · ⏭️ skipped per mode

## Evidence

- 001 spec: [items/001-spec.md](items/001-spec.md) — 13 acceptance criteria, no new ADR needed (thesis_state invariant preserved)
- 001 grill: [items/001-grill.md](items/001-grill.md) — Verdict: PASS, 13 questions resolved, ADR 0005 created, CONTEXT.md updated with `advisory_gaps` + `top_holdings_broker_thin` (commit `43a61bf`)
- 001 plan: [items/001-plan.md](items/001-plan.md) — 11 tasks, ~58 TDD steps, 4 new test files + 2 extensions (commit `ad99d94`)
- 001 drift: [items/001-drift.md](items/001-drift.md) — PASS, 2 amend-able findings (commit `8856ab0`)
- 001 ship: [items/001-ship.md](items/001-ship.md) + PR [#76](https://github.com/snowshine0216/investment-research-copilot/pull/76)
- 001 verify: [items/001-verify.md](items/001-verify.md) — PASS; concrete evidence on disk (discipline_report.md line 408 shows 证据缺口 suffix on fund 003304; AC12 two-run determinism confirmed)
- 001 review: [items/001-review.md](items/001-review.md) — PASS; /ship steps 8+9 found 1 P0 + 4 P1, all fixed in-branch with 9 follow-up tests
- 001 pr-review: [items/001-pr-review.md](items/001-pr-review.md) — PASS, 0 findings (`/code-review` 7-angle sweep)
- 001 merge: squash commit `f869bb1` on feature branch
- 002 spec: [items/002-spec.md](items/002-spec.md) — 15 ACs; memo-only (no new advisory_gaps code)
- 002 grill: [items/002-grill.md](items/002-grill.md) — 13 questions resolved; 3 CONTEXT.md glossary entries added; no ADR
- 002 plan: [items/002-plan.md](items/002-plan.md) — 11 tasks / ~55 TDD steps
- 002 drift: [items/002-drift.md](items/002-drift.md) — PASS; 2 plan amendments + 1 accepted refactor
- 002 ship: [items/002-ship.md](items/002-ship.md) + PR [#77](https://github.com/snowshine0216/investment-research-copilot/pull/77)
- 002 verify: [items/002-verify.md](items/002-verify.md) — PASS; 37 concentration tests + 795 broader-suite passed; empty-case + lock + two-run determinism confirmed
- 002 review: [items/002-review.md](items/002-review.md) — PASS; /ship steps 8+9 found 1 P0 + 2 P1 (duplicate-symbol undercount, set-iter non-determinism, FP boundary), all fixed in-branch
- 002 pr-review: [items/002-pr-review.md](items/002-pr-review.md) — PASS-WITH-NITS; /code-review found 1 latent-bug (double-dash markdown) fixed in commit `79f88d7` + 2 cosmetic nits accepted
- 002 merge: squash commit `ad31c56` on feature branch
- 003 spec: [items/003-spec.md](items/003-spec.md) — 18 ACs; **memo-rendering only** (fetcher already existed from prior 2026-05-26 run)
- 003 grill: [items/003-grill.md](items/003-grill.md) — 11 questions resolved; ADR 0006 created; CONTEXT.md updated with 4 entries
- 003 plan: [items/003-plan.md](items/003-plan.md) — 14 tasks / ~70 TDD steps
- 003 drift: [items/003-drift.md](items/003-drift.md) — PASS; 3 plan amendments + 1 recorded portability concern
- 003 ship: [items/003-ship.md](items/003-ship.md) + PR [#78](https://github.com/snowshine0216/investment-research-copilot/pull/78)
- 003 verify: [items/003-verify.md](items/003-verify.md) — PASS; **`outputs/2026-05-27/qdii_premium.json` written with 30 rows; 3 blocking picks confirmed: 159501 (+6.92%), 159941 (+6.48%), 513300 (+5.99%)**; AC13 portability fix verified
- 003 review: [items/003-review.md](items/003-review.md) — PASS; 1 P0 + 3 P1 found, all fixed in-branch
- 003 pr-review: [items/003-pr-review.md](items/003-pr-review.md) — PASS-WITH-NITS; 1 missed P1 (3rd nan-guard site in `_decision_status_for_pick`) + 2 nits, all fixed in commit `53b8f88`
- 003 merge: squash commit `3b2a31f` on feature branch

## Notes

- Item order pending dependency-scan dispatch; provisional `001, 002, 003`.
- Project type non-web → post-ship XOR uses `/verify`, never `/qa`.
- Mode A → each item opens a sub-PR into `autodev/instrument-pickability-feature`; final rollup PR for the user to land.
