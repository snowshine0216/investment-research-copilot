# PROGRESS — Pickability Follow-ups (F4 / F5 / F6)

**Run started**: 2026-05-27
**Mode**: backlog · **Project type**: non-web · **PR shape**: A · **Feature branch**: `autodev/pickability-followups-feature`

| id | title | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F4 | thesis_news real-content scoring | ✅ | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
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

## Notes

- Item order locked F4 → F5 → F6 by dep-scan 2026-05-27 (no shared write surfaces; small → medium → opinionated).
- Project type non-web → post-ship XOR uses `/verify`, never `/qa`.
- Mode A → each item opens a sub-PR into `autodev/pickability-followups-feature`; final rollup PR for the user to land.
- Origin: deferred items F4 / F5 / F6 from `docs/2026-05-27-instrument-pickability/SKIPPED.md`. User confirmed scope this turn.
