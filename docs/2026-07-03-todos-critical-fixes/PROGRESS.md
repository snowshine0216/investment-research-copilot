# PROGRESS — TODOS.md critical fixes

Run dir: `docs/2026-07-03-todos-critical-fixes/` · Mode: backlog · PR shape: A · Project type: non-web

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 002 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 003 | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ |
| 004 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

QA column pre-filled ⏭️ for all items: project type is non-web → `/verify` is the post-ship
verifier (XOR rule).

Item 003 row all-⏭️: reclassified OUT at dependency-scan review — stale TODO, already
resolved on main (see SKIPPED.md). TODOS.md annotated resolved-as-built, doc-only.

## Run-level

| gate | status |
|------|--------|
| dependency scan | ✅ order locked: 001, 002, 004 (003 reclassified OUT — stale TODO, see SKIPPED.md) |
| run-doc-sync | ⏳ |
| run-final-verify | ⏳ |
| close-out (roll-up PR opened, left for user) | ⏳ |

## Notes

- Feature branch `autodev/todos-critical-fixes-feature` synthesized off `main` @ 221a34e4
  and pushed (no merge-to-main opt-in in this invocation).
