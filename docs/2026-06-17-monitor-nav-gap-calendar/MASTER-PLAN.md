# MASTER-PLAN — Monitor `nav_quality` calendar-grounded NAV-gap check

**Mode:** spec
**Project type:** non-web
**PR shape:** A
**Feature branch:** `claude/affectionate-greider-e105f6` (current, non-protected; item PR lands here)
**Base for final roll-up PR:** `main` (Phase 3 opens feature → main PR, **not merged** — left for the user)
**Item branch:** `claude/monitor-nav-gap-calendar-001`

## Per-mode skill skips (spec mode)

| Phase | Skill | Status |
|-------|-------|--------|
| spec | `superpowers:brainstorming` | ⏭️ skipped — user authored the spec (copied verbatim to `items/001-spec.md`) |
| grill | `grill-with-docs` | ⏭️ pre-completed — user-grilled; orchestrator must NOT auto-invoke |
| plan | `superpowers:writing-plans` (Opus) | runs (ENTRY) |
| impl | `superpowers:subagent-driven-development` (Sonnet) | runs |
| drift | in-prompt (Sonnet) | runs |
| ship | `/ship` | runs (PR + docs + inline review) |
| verify | `/verify` (non-web XOR) | runs — **not** `/qa` |
| pr-review | `/code-review` | runs |
| fix | Sonnet triage | runs if any post-ship verdict FAILs |
| merge | `gh pr merge --squash --delete-branch` (Mode A) | runs after pre-merge gate |

## Loop exit contract (item 001)

Merge gate requires, on disk:
- `items/001-spec.md` (presence) ✓ user-provided
- grill verdict — **absence-OK** (PROGRESS shows ⏭️ user-grilled)
- `items/001-plan.md` (presence)
- `items/001-drift.md` — `^Verdict: PASS`
- `items/001-ship.md` — first line `PR: https://…`
- `items/001-verify.md` — `^Verdict: PASS`
- `items/001-review.md` — `^Verdict: PASS|PASS-WITH-NITS` (inline from `/ship`)
- `items/001-pr-review.md` — `^Verdict: PASS|PASS-WITH-NITS`

## Model contract

| Role | Model |
|------|-------|
| Orchestrator (this session) | session default (no override) |
| plan subagent | opus |
| impl / drift / verify / pr-review / fix subagents | sonnet |

## Project-specific notes

- TDD is mandatory (CLAUDE.md + global FP guidance): red → green → refactor; `tests/` mirrors `src/irc/`.
- Pure functions never do I/O (ADR 0017 §3.3). `trace.py` / `structural.py` receive the calendar as a parameter; only `akshare_client.py` and the new `trading_calendar.py` touch network/filesystem.
- Live AkShare tests are double-gated (`pytest.mark.live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`). The unit suite must pass with NO network.
- `eval_trace.json` `schema_version` is bumped — update any structural test that pins it.
- ADR 0018 "D3" must be updated to point at this calendar-grounded successor (doc-sync / grill territory — handled in plan + doc-sync gate).
