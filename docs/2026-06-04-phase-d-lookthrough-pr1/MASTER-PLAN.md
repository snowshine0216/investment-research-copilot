# MASTER-PLAN — Phase D active-fund look-through (PR1)

Mode: spec
Project type: non-web
PR shape: A
Feature branch: docs/phase-d-active-lookthrough-spec
Final roll-up base: main
Item order: 001 (single item)

## Per-mode skill skips

| Phase | Status | Reason |
|-------|--------|--------|
| brainstorming (spec authoring) | ⏭️ skipped | User authored the design spec; brainstorming would silently rewrite intent. |
| grill | ⏭️ skipped | Spec-mode autonomous run: user is assumed to have already grilled. Orchestrator MUST NOT auto-invoke grill. (Any CONTEXT.md/ADR gaps caught by Phase 3 doc-sync.) |
| writing-plans | runs (Opus) | ENTRY phase for spec mode — produces `items/001-plan.md` (PR1 plan only, per spec §10). |
| subagent-driven-development | runs (Sonnet) | Implementation. |
| drift check | runs (Sonnet, in-prompt) | Plan↔diff drift. |
| ship (`/ship`) | runs | Opens PR into feature branch; captures inline review. |
| post-ship verify | `/verify` (non-web) | Project type is non-web → `/verify`, never `/qa`. |
| pr-review (`/code-review`) | runs | On the open PR. |
| fix loop | runs as needed | No retry budget; exits only on all-3-PASS. |
| merge | runs | `gh pr merge --squash --delete-branch` into the feature branch. |

## Phase 2 sequence

```
spec (⏭️) → grill (⏭️) → plan (Opus writing-plans)
  → branch → impl (Sonnet) → drift → ship (/ship: PR + docs + inline review)
  → [verify ‖ pr-review] → fix → merge
```

## Models (subagent contract — every dispatch declares model)

- plan → `opus`
- impl / drift / verify / pr-review / fix → `sonnet`
- orchestrator (this session) → session default, no override

## Hard stops specific to this run (NON-NEGOTIABLE)

The autodev loop delivers **PR1 only** and STOPS at the spec's human gates. It must **not**:

1. **Flip the flag** (`enabled: true`). That is PR2 — gated on the gate-#5 human floor decision. The flag stays `enabled: false` in this run.
2. **Run the live AkShare test autonomously** (gate #4 — `IRC_RUN_LIVE_AKSHARE=1`). The live-gated test code is *authored* but not *executed*; column-string confirmation against real EastMoney rows is a human follow-up. `/verify` smokes non-network paths only (help/dispatch/cached-DB/unit suite).
3. **Sign off the diff report** (gate #5). The loop ships the diff-report command and produces the artifact; the human reviews it and chooses the final `coverage_floor`.

At end of run, Phase 3 leaves the feature branch open with PR1 merged, and the report surfaces gates #4 + #5 as the remaining manual steps before PR2.

## Verify-phase note (gate #4 boundary)

`/verify` for this item asserts entry-point health WITHOUT live network: `irc fundamentals stock-valuation --help`, `irc config validate` accepting the new block, the unit/integration suite green (excluding `-m live_akshare`), and the command degrading cleanly against an empty/cached DB. A real live ingest is gate #4 (human).

## Test-suite baseline caveat

Per project memory: full `uv run pytest` is ~18 min and is NOT green on `main` (8 known pre-existing failures + a flaky e2e research gate). Verify/drift must scope assertions to **this item's** new + touched tests, not a blanket "all green," and must distinguish a regression from a pre-existing failure.
