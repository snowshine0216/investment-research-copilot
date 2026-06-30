# PROGRESS — launchd Wrapper Watchdog + Single-Instance Lock

**Mode:** spec · **Project type:** non-web · **PR shape:** A · **Feature branch:** `claude/thirsty-lovelace-3da881`

Legend: ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped-by-mode · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

### Notes
- **spec** ✅ — `items/001-spec.md` (verbatim copy of merged spec PR #180).
- **grill** ⏭️ — user-grilled (rev-2, grill-with-docs). Orchestrator must not auto-invoke in spec mode.
- **plan** ✅ — `items/001-plan.md` (Opus writing-plans, commit `836a427`); 12 tasks, ~50 steps, TDD red-first; harness assumptions + doc anchors verified by orchestrator.
- **verify** — non-web project → `/verify` (not `/qa`). XOR: `/qa` never runs.
- This is the non-web spec-mode path: exactly one of {qa, verify} → `verify`.
