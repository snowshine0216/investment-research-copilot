# PROGRESS — Pickability Follow-ups (F4 / F5 / F6)

**Run started**: 2026-05-27
**Mode**: backlog · **Project type**: non-web · **PR shape**: A · **Feature branch**: `autodev/pickability-followups-feature`

| id | title | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F4 | thesis_news real-content scoring | ✅ | ✅ | ✅ | ✅ `claude/pickability-followups-F4` | ✅ `245f868` | ✅ | ✅ [#80](https://github.com/snowshine0216/investment-research-copilot/pull/80) | ✅ | ✅ pass-with-nits | ✅ pass-with-nits | ✅ 2 rounds | ✅ `21fb9ca` |
| F5 | §2 macro research excerpt depth | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| F6 | filings evidence role (drop vs normalize) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

**Run-level**: `run-doc-sync` ⏳ · `run-final-verify` ⏳ · `run-close-out` ⏳

## Run-level evidence

- doc-sync: _pending_
- final-verify: _pending_
- final PR: _pending_

## Legend

- ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft FAIL (in fix loop) · ⛔ refused gate · ⏭️ skipped per mode

## Evidence

- dep-scan: F4 → F5 → F6 confirmed (no code deps; only info-dep favoring same order) — Sonnet dispatch
- F4 spec: [items/F4-spec.md](items/F4-spec.md) — 10 ACs; position (a) keep keyword + wire plumbing; defers LLM upgrade to follow-up SKIPPED if rubric inadequate (commit `fd2cfa4`)
- F4 grill: [items/F4-grill.md](items/F4-grill.md) — 24 Qs resolved (autonomous, auto-accepted); ADR-0007 written; CONTEXT.md updated with 4 thesis-news terms; spec mapping table rewritten against real seven `asset_class` values
- F4 plan: [items/F4-plan.md](items/F4-plan.md) — 11 tasks / 40 TDD steps (commit `d7032a9`)
- F4 impl: branch `claude/pickability-followups-F4`, final SHA `245f868`; 123 tests passed; `news_summaries={}` literal removed
- F4 drift: [items/F4-drift.md](items/F4-drift.md) — PASS, 2 accepted, 0 unimplemented (commit `2c36df4`)
- F4 ship: [items/F4-ship.md](items/F4-ship.md) + PR [#80](https://github.com/snowshine0216/investment-research-copilot/pull/80); /ship inline-fixed 1 P1 observability gap (commit `43662e6`); PATCH bump 0.9.0 → 0.9.1
- F4 review: [items/F4-review.md](items/F4-review.md) — PASS-WITH-NITS (0 blocker / 0 latent after inline fix / 2 nits accepted)
- F4 verify: [items/F4-verify.md](items/F4-verify.md) — PASS; live `uv run irc run --only score` produced `news coverage: 127/127 instruments`; 10/10 ACs verified (AC #4 measured, no SKIPPED follow-up needed)
- F4 pr-review: [items/F4-pr-review.md](items/F4-pr-review.md) — round 1 FAIL (citation contamination) → round 2 FAIL (extended scope to geopolitical_stress + over-aggressive stop marker) → round 3 PASS-WITH-NITS (1 nit on gold_cmd._summary_from_theme_report subheading edge case)
- F4 fix: 2 rounds. Round 1 commit `45c715b` extracted shared `extract_prose_from_report_md` helper + ADR 0007 §3a invariant. Round 2 commit `44e07dc` tightened stop marker to `^##\s*(Citations|References)\b` + extended helper to `geopolitical_stress_from_theme_report` (third call site) + 10 new helper tests.
- F4 merge: squash commit `21fb9ca` on feature branch (PR #80 squash-merged)

## Notes

- Item order locked F4 → F5 → F6 by dep-scan 2026-05-27 (no shared write surfaces; small → medium → opinionated).
- Project type non-web → post-ship XOR uses `/verify`, never `/qa`.
- Mode A → each item opens a sub-PR into `autodev/pickability-followups-feature`; final rollup PR for the user to land.
- Origin: deferred items F4 / F5 / F6 from `docs/2026-05-27-instrument-pickability/SKIPPED.md`. User confirmed scope this turn.
