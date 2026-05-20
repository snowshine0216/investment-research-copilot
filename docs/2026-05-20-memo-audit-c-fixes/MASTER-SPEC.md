# Master Spec — Memo Audit C-Fixes (C4–C8)

**Date:** 2026-05-20
**Source:** `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` (Group 1, rows C4–C8) + `outputs/2026-05-20/memo_audit.txt`.

## Goal

Clear the remaining 5 audit blockers (problems P1–P6 in `memo_audit.txt`) so `irc memo` re-runs successfully and `PIPELINE_HALTED.md` clears.

## Scope

| # | Audit finding | In/Out | File(s) |
|---|---|---|---|
| C4 | P1 — hardcoded macro line is too deterministic | IN | `src/irc/commands/memo_cmd.py` (`run_memo`, `macro_summary=`) |
| C6 | P4 — execution-line triggers render as bare codes | IN | `src/irc/commands/memo_cmd.py` (`_compose_execution_lines`) |
| C7 | P5 — 综合分 is a black box, no methodology disclosure | IN | `src/irc/memo/picks_table.py` |
| C5 | P2 + P3 — LLM produces directional predictions + contradictory 估值 statements | IN | `src/irc/memo/synthesizer.py` (`_SYSTEM`/`_GLOSSARY`) |
| C8 | P6 — §4 says "敞口可接受" while §6 says premium data not collected | IN | `src/irc/memo/synthesizer.py` (prompt) |

## Acceptance criteria

- Each fix lands with new TDD tests asserting the new behavior (red → green → refactor)
- Existing tests stay green (`tests/memo/`, `tests/commands/test_memo_cmd.py`)
- `ruff check src/ tests/` clean on touched files
- Full suite has no new failures vs. main baseline (2 pre-existing unrelated failures documented in PR #51)
- After merge: re-run `irc memo` → audit gate passes (manual verification, blocked by ingest/synthesizer routes — covered by tests)

## Non-goals

- E3/E6 manual ingest work (QDII premium/discount, A-share valuation percentile) — separate manual items in the tracker
- E8 (PIPELINE_HALTED) — resolves automatically once C-fixes land
- Changes to the auditor itself; we are fixing the generator, not the checker

## Constraints

- Single feature branch + single PR (matches user's PR history pattern for grouped audit fixes)
- Each fix mechanically distinct → can be reviewed as 5 atomic commits
- Synthesizer prompt edits (C5, C8) are LLM-driven; verified by asserting prompt content, not LLM output
