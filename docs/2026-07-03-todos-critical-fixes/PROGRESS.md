# PROGRESS — TODOS.md critical fixes

Run dir: `docs/2026-07-03-todos-critical-fixes/` · Mode: backlog · PR shape: A · Project type: non-web

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ✅ | ✅ | ✅ claude/todos-critical-fixes-001 | ✅ f61f5e5c+a77aba13 | ✅ | ✅ [#195](https://github.com/snowshine0216/investment-research-copilot/pull/195) | ⏭️ | ✅ | ✅ | ✅ | ✅ 0 rounds | ✅ 7ddeea80 |
| 002 | ✅ | ✅ | ✅ | ✅ claude/todos-critical-fixes-002 | ✅ de05779c+5e39574b | ✅ | ✅ [#196](https://github.com/snowshine0216/investment-research-copilot/pull/196) | ⏭️ | ✅ | ✅ nits-deferred | ✅ | ✅ 0 rounds | ✅ 2594b26a |
| 003 | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ | ⏭️ |
| 004 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 005 | ⏭️ user-authored | ⏭️ | ✅ | ✅ claude/todos-critical-fixes-005 | ✅ 843eefbc+96c034fd | ✅ | ✅ [#197](https://github.com/snowshine0216/investment-research-copilot/pull/197) | ⏭️ | ✅ | ✅ | ✅ | ✅ 0 rounds | ✅ 9ceb9b13 |

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
