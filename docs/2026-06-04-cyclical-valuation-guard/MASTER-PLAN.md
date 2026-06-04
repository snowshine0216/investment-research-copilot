# MASTER-PLAN — Commodity-Cyclical Valuation Guard + Sector PE Accumulate

**Mode:** spec
**Project type:** non-web   <!-- Python `irc` CLI / data tool → post-ship verifier is /verify, NOT /qa -->
**PR shape:** A   <!-- per-item PR; no --rollup in invocation -->
**Base (default) branch:** main (protected)
**Feature branch:** autodev/cyclical-valuation-guard-feature (synthesized off main — no opt-in to merge into a protected branch this turn; left open for the user at close-out)
**Sub-branch (item 001):** claude/cyclical-valuation-guard-001

## Per-mode skill skips (spec mode)

| Phase | Skill | This run |
|-------|-------|----------|
| spec (brainstorming) | `superpowers:brainstorming` | **SKIPPED** — user authored the spec; copied verbatim to `items/001-spec.md`. |
| grill (`grill-with-docs`) | `grill-with-docs` | **PRE-COMPLETED ⏭️** — user-grilled (Status: "revised after spec review"). Orchestrator MUST NOT auto-invoke grill in spec mode. |
| plan (writing-plans) | `superpowers:writing-plans` | **RUNS** (Opus subagent) — ENTRY phase; reads `items/001-spec.md`. |
| impl | `superpowers:subagent-driven-development` | RUNS (Sonnet). |
| drift | in-prompt diff-vs-plan | RUNS (Sonnet). |
| ship | `/ship` | RUNS — opens PR into feature branch, captures inline review. |
| post-ship verify | `/verify` (non-web XOR) | RUNS (Sonnet) — NOT `/qa`. |
| pr-review | `/code-review` | RUNS (Sonnet) on the open PR. |
| fix | Sonnet triage | RUNS if any of 3 post-ship verdicts FAIL. |
| merge | `gh pr merge --squash --delete-branch` | Pre-merge gate; lands sub-branch into the feature branch only. |

## Item order

001 (single item — N=1).

## Protected-branch guard

Never `gh pr merge` into main/master/etc. Sub-PR base = `autodev/cyclical-valuation-guard-feature`. The feature branch's own roll-up PR into `main` is opened (NOT merged) at Phase 3 close-out for the user to land.

## Model assignment

| Role | Model |
|------|-------|
| Orchestrator (this session) | session default (no override) |
| plan subagent (writing-plans) | opus |
| impl / drift / verify / pr-review / fix subagents | sonnet |

## Project conventions to honor (from CLAUDE.md / CONTEXT.md)

- **TDD red→green→refactor**; test mirrors source (`foo.py` → `tests/.../test_foo.py`).
- Functional, immutable; pure cores, effects at edges; files <200 lines, functions <20 lines ideal.
- `基金概况` indicator **forbidden** in production fetch code (acceptance test greps the literal).
- Citation IDs locked at 16 hex; H3/SAME-3 invariants govern opportunity output partitions.
- Live AkShare tests double-gated (`pytest.mark` + `IRC_*=1`); no live calls in unit tests.
- Secrets in `.env` only.
- Lint: `uv run ruff check src tests` (line-length 100, py312). Tests: `uv run pytest`.

## Test-suite baseline (from auto-memory)

Full `uv run pytest` ~18 min and is **NOT green on main** (8 known pre-existing failures + a flaky/hang-prone e2e research gate). Scope test runs to the diff (`tests/opportunity/`, `tests/fundamentals/`, `tests/commands/`, `tests/narrative/`, `tests/discovery/`) before assuming a regression. Do not block on pre-existing reds.
