# MASTER-PLAN — Phase A legulegu rate-limit

**Mode:** spec
**Project type:** non-web   <!-- Python CLI (`irc`); no browser surface → post-ship verifier is `/verify`, never `/qa` -->
**PR shape:** A   <!-- per-item PR; no `--rollup` requested -->

## Branch strategy

- **Feature branch:** `phase-a/legulegu-rate-limit` — already exists (off `main`), holds the 3 design commits + the autodev run dir. Non-protected. Sub-PR target.
- **Sub-branch (item 001):** `phase-a/legulegu-rate-limit-impl` — cut off the feature branch. All impl + test commits land here.
- **Ship PR:** `phase-a/legulegu-rate-limit-impl` → `phase-a/legulegu-rate-limit` (item-level review surface).
- **Final (Phase 3):** open `phase-a/legulegu-rate-limit` → `main` PR — **opened, not merged**. `main` is protected and the user did NOT opt into a protected merge. The operator merges after the live gates pass.

## Per-mode skill skips (spec mode)

| Phase | Skill | Status |
|-------|-------|--------|
| spec (brainstorming) | `superpowers:brainstorming` | **skipped** — user authored the spec (`items/001-spec.md` verbatim) |
| grill | `grill-with-docs` | **skipped ⏭️** — user-grilled (rev3 + ADR 0014 + CONTEXT committed). Orchestrator MUST NOT auto-invoke. |
| plan | `superpowers:writing-plans` | **runs** (Opus) — ENTRY phase |
| impl | `superpowers:subagent-driven-development` | runs (Sonnet) |
| drift | in-prompt | runs (Sonnet) |
| ship | `/ship` | runs (review captured inline) |
| verify | `/verify` | runs (Sonnet) — non-web XOR branch (no `/qa`) |
| pr-review | `/code-review` | runs (Sonnet) |
| fix | in-prompt | runs if any post-ship verdict FAILs |
| doc-sync | in-prompt | run-level, Phase 3 |

## Loop exit contract (item 001)

Merge requires all of: `items/001-drift.md` (`Verdict: PASS`), `items/001-ship.md` (`PR: https://…`), `items/001-verify.md` (`Verdict: PASS`), `items/001-review.md` (`PASS|PASS-WITH-NITS`), `items/001-pr-review.md` (`PASS|PASS-WITH-NITS`). Spec + plan presence-only. Grill absence-OK (PROGRESS shows ⏭️ user-grilled).

## `/verify` scope clamp (CRITICAL — read before dispatching verify)

`/verify` for this item is **OFFLINE ONLY**. It MUST NOT hit the live legulegu network (limiter in deep cooldown). Acceptable smoke evidence: `irc` CLI imports/`--help`, the new module's offline unit behavior, targeted offline `pytest tests/fundamentals/ tests/data/ tests/commands/` runs. The live network gates (#3/#4/#5, all `IRC_RUN_LIVE_AKSHARE=1`) are explicitly **deferred to the operator** — see MASTER-SPEC.md "Live-network operator gates". A verify subagent that runs a live-network test is a contract violation.

## Test-suite baseline caveat

Full `pytest` is ~18 min and **NOT green on `main`** (8 known pre-existing failures + flaky/hang-prone e2e research gate — see memory `project_test_suite_baseline`). Diff-scope before calling anything a regression. Targeted runs: `tests/fundamentals/`, `tests/data/`, `tests/commands/`.

## Version / changelog

`VERSION` stays `0.9.3`. Changes accumulate under CHANGELOG `[Unreleased]` as a sub-bullet under the Phase A entry (project convention — memory `project_versioning_convention`).
