# PROGRESS — `irc eval-funds`

Mode: spec · Project type: non-web · PR shape: A · Feature branch: `feat/eval-funds-command`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused

| id  | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅   | ⏭️    | ⏳   | ⏳     | ⏳   | ⏳    | ⏳ | ⏳     | ⏳     | ⏳        | ⏳  | ⏳    |

## Evidence cells (filled as phases pass)

- **001-spec** ✅ — `items/001-spec.md` (verbatim copy of the approved design)
- **001-grill** ⏭️ — `⏭️ user-grilled` (spec mode; orchestrator must not auto-invoke grill)
- **001-plan** — `items/001-plan.md` (pending Opus writing-plans)
- **001-branch** —
- **001-impl** —
- **001-drift** — `items/001-drift.md`
- **001-PR** — `items/001-ship.md`
- **001-verify** — `items/001-verify.md`  (non-web → `/verify`; `/qa` does NOT run)
- **001-review** — `items/001-review.md`  (inline from `/ship` steps 8+9)
- **001-pr-review** — `items/001-pr-review.md`  (`/code-review` on open PR)
- **001-fix** —
- **001-merge** —

## Notes

- Column `QA` omitted from the table: non-web project → `/verify` is the XOR branch.
- Feature branch pre-existed with the design doc committed (commit `037fa19`); not synthesized.
