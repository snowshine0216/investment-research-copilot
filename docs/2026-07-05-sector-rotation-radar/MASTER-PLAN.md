# MASTER-PLAN — Sector rotation radar

**Mode:** spec · **Project type:** non-web · **PR shape:** A (per-item PRs) · **N:** 1

## Branch strategy

- **Base (protected):** `main` — the user's `/autodev <spec>` invocation carried **no** "merge to main" opt-in, so autodev never merges into `main`.
- **Feature branch (synthesized):** `autodev/sector-rotation-radar-feature` — cut off `main`. Sub-PRs land here; left open at the end for the user to review + land.
- **Prep commit:** `2c1b844b` (f127→f100 fix) sits at the base of the feature branch, ahead of the design-artifact commit (user-directed; prerequisite per spec §13-T1/AC1).
- **Sub-branch (item 001):** `claude/sector-rotation-radar-001` — cut off the feature branch; PR'd into `autodev/sector-rotation-radar-feature`.

## Per-mode skill skips (spec mode)

| Phase | Runs? | Skill |
|-------|-------|-------|
| brainstorming (spec authoring) | ⏭️ SKIP | user authored the spec; copied verbatim to `items/001-spec.md` |
| grill | ⏭️ SKIP (pre-completed) | user already grilled (spec status "grilled + locked"; ADR 0023 + CONTEXT section are the grill artifacts). Orchestrator MUST NOT auto-invoke grill. |
| **plan** | ✅ RUN (ENTRY) | `superpowers:writing-plans` (orchestrator's session model) reads the refined spec |
| branch | ✅ | `git switch -c` |
| impl | ✅ | `superpowers:subagent-driven-development` (Sonnet) |
| drift | ✅ | in-prompt Sonnet, no skill |
| ship | ✅ | `/ship` (opens PR + docs + inline review) |
| verify | ✅ (non-web branch of XOR) | `/verify` — **NOT** `/qa` (no web surface; `irc` is a Python CLI) |
| pr-review | ✅ | `/code-review` on the open PR |
| fix | ✅ if any post-ship verdict FAILs | Sonnet triage subagent |
| merge | ✅ | `gh pr merge --squash --delete-branch` into the feature branch (non-protected) |

## Post-ship gate (XOR + parallel)

```
qa ⊕ verify  ‖  pr-review        (review captured inline by /ship steps 8+9)
   └─ verify (non-web)  └─ /code-review
```

Loop exits only when ALL THREE post-ship verdicts are PASS / PASS-WITH-NITS:
1. `items/001-verify.md` — `^Verdict: PASS`
2. `items/001-review.md` — `^Verdict: PASS|PASS-WITH-NITS` (inline from `/ship`)
3. `items/001-pr-review.md` — `^Verdict: PASS|PASS-WITH-NITS` (`/code-review`)

## Project-specific execution notes (from spec traps + CLAUDE.md)

- **TDD** is enforced project-wide (CLAUDE.md). Pure cores (`composite`, `states`, `exposure`, `candidates`) get unit tests first (AC4/AC5/AC6/AC7).
- **AC1 live-probe-first:** before any EM parser is written, a spike verifies the board snapshot + board-history endpoints' actual field codes on the live CN egress (`IRC_CN_PROXY`), recorded in item notes. Field codes are interface-specific (T1: `f100` vs `f127`).
- **T2:** never test EM endpoints through curl-through-proxy — false-fails; use `requests`.
- **T3:** the `cached_fetch` breaker is protective — never self-extend by retrying while blocked.
- **T5:** `pytest tests/commands/` whole-dir hangs (suite ordering) — run `tests/commands/test_rotation_cmd.py` per-file.
- **T6:** changing a shared signature (`industry_map_store`) → grep callers across all of `tests/`, not just the mirror dir.
- **VERSION:** accumulate under CHANGELOG `[Unreleased]`; do NOT bump VERSION per PR (project convention — memory `project_versioning_convention`).
- Live network (real EM egress) is gated; unit tests must run offline with fixtures. The seed and daily-run edges are I/O at the command layer; pure cores stay mockless.

## Item order

N=1 — no dependency scan needed. Single item: `001`.
