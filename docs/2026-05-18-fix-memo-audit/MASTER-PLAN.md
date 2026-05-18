# Memo-Audit Cleanup Backlog — Master Plan

## Phase ordering

| Phase | Items | Why this order |
|---|---|---|
| 1. Smallest changes | 001, 002 | One-line config/code edits. Validate the loop end-to-end before any larger change. |
| 2. Config-only | 003 | Universe YAML backfill. Zero code risk. |
| 3. Memo data plumbing | 004, 005 | Rename a single field, plumb a date. Both touch the memo pipeline narrowly. |
| 4. New behaviors | 006 | Numeric-audit validator. Net-new code with a small surface area. |
| 5. Decision report data | 007, 008 | Add a column and clean up `unknown`. Both change `decide_row` shape; do them adjacent to share context. |
| 6. Memo Section 7 | 009 | Compose execution notes from the trade plan; bigger plumbing than 005 but localized to memo. |
| 7. Venue proxy | 010 | Loosen the gold proxy rule. Has user-facing portfolio effect; do after the renderer/data changes settle. |
| 8. Renderer rewrite | 011 | Decision-report markdown restructure. Done last so it has the column from 007 and the `unknown` cleanup from 008 to render against. |

## Branch and PR conventions

- Sub-branches: `claude/fix-memo-audit-NNN` (`NNN` = item id), all branched off `main`.
- PR title: `<type>(<scope>): <one-line> (NNN)`. Mirrors the project's existing PR style (cf. #25-#28).
- PR body: Summary bullets · Spec link · Test plan checklist.
- All PRs squash-merged into `main` with `--delete-branch`.
- Never amend a merged commit; bug-fix-on-merged ships as a new PR.

## TDD policy

Items 001, 002, 004-011 ship with a failing test written first that becomes passing.
Item 003 is data-only — assertion is "the 5 IDs render with a real `name_cn`"; one snapshot test is sufficient.

## QA + review subagents

Both run in parallel after PR open. QA verifies:
- targeted tests pass (`uv run pytest tests/<module>` for the touched module)
- full test suite still passes (`uv run pytest`)
- one acceptance criterion from spec is rechecked manually

Review verifies:
- spec compliance
- no silent failures or fragile mocks
- cross-file consistency (especially for items 007/008/011 that share decision-report surface area)

## Stop conditions

- 2 retries on the same item → mark BLOCKED, document in PROGRESS.md, move on.
- Full `uv run pytest` red on `main` for reasons unrelated to my work → pause and report.
- gh CLI auth failures → pause and report.

## Final validation (Phase 3)

After the last merge:
- `uv run pytest` exits 0 on `main`.
- Re-render `outputs/2026-05-18/memo.md` against the same fixtures via the existing memo pipeline test (no LLM call); confirm Section 2 no longer contains the "valuation_cost=85 ⇒ very expensive" failure mode and Section 7 is populated.
- Confirm `outputs/2026-05-18/decision_report.md` (or its regenerated equivalent) shows a 3-block layout and no `unknown` venue rows for instruments present in the universe with `available_venues` configured.
- Update `HANDOFF.md` if pertinent.
- Delete `.autodev-current`.
