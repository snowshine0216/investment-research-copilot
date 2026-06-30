# MASTER-PLAN — launchd Wrapper Watchdog + Single-Instance Lock

**Mode:** `spec`
**Project type:** non-web   (Python `irc` CLI + bash launchd wrappers → post-ship verifier is `/verify`, not `/qa`)
**PR shape:** A   (per-item PRs; no `--rollup` opt-in this turn)
**Feature branch:** `claude/thirsty-lovelace-3da881` (current; non-protected; up to date with origin/main @ `7eef5fd`, which already has #179 sentinel fix + #180 spec)
**Sub-branch for item 001:** `claude/launchd-watchdog-001` (cut off the feature branch)
**Base for final roll-up PR:** `main` — opened, NOT merged (no "merge to main" opt-in this turn).

## Per-mode skill skips (spec mode)

| Phase | Disposition |
|-------|-------------|
| `brainstorming` (spec authoring) | **SKIPPED** — user authored the spec; copied verbatim to `items/001-spec.md`. |
| `grill` | **PRE-COMPLETED ⏭️** — user already grilled (rev-2, grill-with-docs, merged #180). Orchestrator must NOT auto-invoke. |
| `writing-plans` | **RUNS** — Opus subagent reads the spec → `items/001-plan.md`. This is the entry authoring phase. |
| `subagent-driven-development` (impl) | RUNS (Sonnet). |
| drift check | RUNS (Sonnet, in-prompt). |
| `/ship` | RUNS (PR + docs + inline review). |
| `/verify` | RUNS (non-web XOR branch). `/qa` does NOT run. |
| `/code-review` | RUNS on the open PR. |

## Required per-item verdict artifacts (merge gate)

`items/001-{plan,drift,ship,review,verify,pr-review}.md` — drift/verify/review/pr-review must carry `^Verdict: PASS|PASS-WITH-NITS`; ship.md first line `PR: https://…`; plan/spec presence-only. Grill verdict absence-OK (⏭️ pre-completed).

## Protected-branch guard

Sub-PR base = feature branch `claude/thirsty-lovelace-3da881` (non-protected) → mergeable in-run. Final roll-up PR base = `main` (protected) → opened only, never auto-merged.
