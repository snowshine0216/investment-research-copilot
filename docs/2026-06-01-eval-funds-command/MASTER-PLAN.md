# MASTER-PLAN — `irc eval-funds`

**Mode:** spec
**Project type:** non-web    # Python `irc` CLI — post-ship verifier is `/verify` (NOT `/qa`)
**PR shape:** A             # per-item PR into the feature branch (no `--rollup` given)
**Feature branch:** `feat/eval-funds-command`  (current; non-protected; holds the committed design doc)
**Base for final roll-up PR:** `main`  (NOT auto-merged — Phase 3 opens it for the user)
**Item order:** 001 (single item; degenerate N=1)

## Per-mode skill skips (spec mode)

| Phase | Status in this run |
|-------|--------------------|
| brainstorming (`superpowers:brainstorming`) | ⏭️ skipped — user authored the spec |
| grill (`grill-with-docs`) | ⏭️ pre-completed — user-grilled; orchestrator must NOT auto-invoke |
| writing-plans (`superpowers:writing-plans`) | ✅ runs (Opus) — ENTRY phase |
| subagent-driven-development | ✅ runs (Sonnet) |
| drift check | ✅ runs (Sonnet, in-prompt) |
| `/ship` | ✅ runs — PR + docs + inline review |
| `/verify` | ✅ runs (non-web XOR branch; `/qa` does NOT run) |
| `/code-review` | ✅ runs on the open PR |

## Sub-branch / PR strategy

- Sub-branch: `claude/eval-funds-command-001` cut off `feat/eval-funds-command`.
- Per-item PR: `claude/eval-funds-command-001` → `feat/eval-funds-command` (squash-merge after gate).
- Phase 3: open `feat/eval-funds-command` → `main` PR as a review surface; leave UNMERGED.

## Pre-merge gate (per item)

Merge refuses without ALL of:
- `items/001-drift.md` → `^Verdict: PASS`
- `items/001-ship.md` → first line `PR: https://…`
- `items/001-verify.md` → `^Verdict: PASS`  (non-web XOR)
- `items/001-review.md` → `^Verdict: PASS|PASS-WITH-NITS`  (captured inline by `/ship`)
- `items/001-pr-review.md` → `^Verdict: PASS|PASS-WITH-NITS`  (`/code-review`)
- grill verdict: absence-OK in spec mode (PROGRESS shows ⏭️)
- protected-base check: PR base `feat/eval-funds-command` is non-protected ✓

## Model contract

- Orchestrator: session default (Opus 4.8) — no override.
- plan subagent: `model="opus"`.
- impl / drift / verify / pr-review / fix subagents: `model="sonnet"`.
