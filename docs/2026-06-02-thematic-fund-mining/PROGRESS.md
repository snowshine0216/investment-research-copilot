# PROGRESS — `irc narrative` Thematic Fund Mining

**Mode:** spec · **Project type:** non-web · **PR shape:** A
**Feature branch:** `autodev/thematic-fund-mining-feature` (synthesized off `main`)

| # | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|---|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ `claude/thematic-fund-mining-001` | ✅ 62953c4 | ✅ | ✅ #93 | 🔄 | ✅ | 🔄 | ⏳ | ⏳ |

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop active) · ⏭️ skipped · ⛔ refused gate

## Notes

- **001-spec** ✅ — `items/001-spec.md` (verbatim copy of `docs/superpowers/specs/2026-06-02-thematic-fund-mining-design.md`).
- **001-grill** ⏭️ — spec mode: user authored + grilled their own spec; orchestrator must NOT auto-invoke grill. Any CONTEXT.md/ADR gaps caught by Phase 3 run-level doc-sync.
- **QA column** omitted — non-web project uses `verify` (XOR).
- **001-ship** ✅ — PR [#93](https://github.com/snowshine0216/investment-research-copilot/pull/93) → `autodev/thematic-fund-mining-feature`. `items/001-ship.md`.
- **001-review** ✅ PASS-WITH-NITS — captured inline from `/ship` steps 8+9; 3 P0 blockers found → fixed pre-push (`items/001-ship-blocked.md` → `items/001-review.md`). No VERSION bump (project convention); CHANGELOG `[Unreleased]` entry added.
- **Full-suite triage:** 8 failures are ALL pre-existing (reproduce identically on base branch — broken ingest/data/eval pipeline). 0 in-branch regressions; narrative suite 59 passed / 1 skipped.
- Branch detection: `main` is protected and the invocation contained no opt-in phrase → synthesized `autodev/thematic-fund-mining-feature` as the feature branch; item sub-branch `claude/thematic-fund-mining-001` PRs into it.

## Phase 3 (final validation) — pending
