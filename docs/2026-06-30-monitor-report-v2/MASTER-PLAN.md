# MASTER-PLAN — Monitor Report v2

**Mode:** spec
**Project type:** non-web   (Python `irc` CLI / data tool; report is static HTML rendered by pure functions — post-ship verifier is `/verify`, NOT `/qa`)
**PR shape:** A   (per-item PR; no `--rollup` opt-in this turn)
**Base branch:** `main`
**Feature branch:** `claude/wizardly-shamir-60a599`
**Item count (IN):** 1   →   `001`
**Item branch:** `claude/monitor-report-v2-001`

## Per-mode skill skips (spec mode)

| Phase | Disposition |
|-------|-------------|
| spec (`superpowers:brainstorming`) | **SKIPPED** — user authored the spec; copied verbatim to `items/001-spec.md`. |
| grill (`grill-with-docs`) | **SKIPPED ⏭️** — user already grilled (spec header: "grilled 2026-06-30 via grill-with-docs"). Orchestrator must NOT auto-invoke. |
| plan (`superpowers:writing-plans`) | **RUNS** — Opus, reads `items/001-spec.md` → `items/001-plan.md`. (ENTRY phase.) |
| impl (`superpowers:subagent-driven-development`) | RUNS — Sonnet. |
| drift | RUNS — Sonnet in-prompt, no skill. |
| ship (`/ship`) | RUNS — opens PR, updates docs, captures inline review (steps 8+9). |
| verify (`/verify`) | RUNS — non-web XOR branch; NOT `/qa`. |
| pr-review (`/code-review`) | RUNS — on the open PR. |
| fix | RUNS if any post-ship verdict FAILs. |
| merge | `gh pr merge --squash --delete-branch` into feature branch (NOT main). |

## Branch & merge strategy

- Item 001 implemented on `claude/monitor-report-v2-001`, cut off the feature branch `claude/wizardly-shamir-60a599`.
- Item PR: `claude/monitor-report-v2-001` → `claude/wizardly-shamir-60a599` (squash-merge after gate passes).
- Phase 3: open `claude/wizardly-shamir-60a599` → `main` as a roll-up review PR; **leave it OPEN** for the user (no "merge to main" opt-in this turn).

## Loop exit contract (item 001)

All three post-ship verdicts PASS / PASS-WITH-NITS before merge:
1. `items/001-verify.md` — `^Verdict: PASS` (entry-point smoke: `irc monitor` produces report.html with the new components; no `<script>`/remote refs; `基金概况` absent).
2. `items/001-review.md` — PASS / PASS-WITH-NITS (captured inline from `/ship` steps 8+9).
3. `items/001-pr-review.md` — PASS / PASS-WITH-NITS (`/code-review`).
Plus `items/001-drift.md` `^Verdict: PASS` and `items/001-ship.md` `PR: https://…`.

## Project conventions to enforce (from CLAUDE.md / CONTEXT.md)

- **TDD** red→green→refactor; test mirrors source (`foo.py` → `tests/.../test_foo.py`).
- Pure functions, frozen dataclasses, immutable transforms; I/O at edges (`monitor_cmd` / `evals/` runner only).
- Files <200 lines, functions <20 lines ideal.
- Signature-change discipline: run `tests/monitor/` AND `tests/commands/` (per-file — whole-dir hangs) AND `evals/monitor_forward/` tests.
- Citation ID format locked 16 hex; `基金概况` forbidden in production fetch code.
- ADR 0021 to be authored by impl (spec §14).
