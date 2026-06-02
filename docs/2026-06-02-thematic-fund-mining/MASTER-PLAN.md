# MASTER-PLAN — `irc narrative` Thematic Fund Mining

**Mode:** spec
**Project type:** non-web    # Python 3.12 CLI (irc) — post-ship verifier is `/verify`, NOT `/qa`
**PR shape:** A             # per-item PR (default; no --rollup in invocation)
**Feature branch:** `autodev/thematic-fund-mining-feature` (synthesized off `main`; `main` is protected, no opt-in this turn)
**Sub-branch (item 001):** `claude/thematic-fund-mining-001`
**Base for feature-branch roll-up PR (Phase 3, opened not merged):** `main`

## Per-mode skill skips (spec mode)

| Phase | Status in this run |
|-------|--------------------|
| brainstorming (spec authoring) | ⏭️ SKIPPED — user authored the spec; copied verbatim to `items/001-spec.md` |
| grill (`grill-with-docs`) | ⏭️ PRE-COMPLETED — user-grilled their own spec; orchestrator must NOT auto-invoke |
| writing-plans | ▶️ RUNS — Opus `superpowers:writing-plans` is the ENTRY authoring dispatch |
| subagent-driven-development (impl) | ▶️ RUNS (Sonnet) |
| drift check | ▶️ RUNS (Sonnet in-prompt) |
| `/ship` | ▶️ RUNS (PR + docs + inline review steps 8+9) |
| `/verify` (non-web XOR branch) | ▶️ RUNS — NOT `/qa` |
| `/code-review` | ▶️ RUNS on the open PR |
| triage + fix | ▶️ RUNS if any post-ship verdict FAILs |

## Model contract (per autodev SKILL.md)

| Role | Model |
|------|-------|
| Orchestrator (this session) | session default — no override |
| plan subagent (writing-plans) | **opus** |
| impl / drift / verify / pr-review / fix subagents | **sonnet** |

## Loop exit contract (item 001)

Merge gate refuses without all of: `items/001-drift.md` (`Verdict: PASS`), `items/001-ship.md` (`PR: https://…`), `items/001-verify.md` (`Verdict: PASS`), `items/001-review.md` (`Verdict: PASS|PASS-WITH-NITS`, inline from `/ship`), `items/001-pr-review.md` (`Verdict: PASS|PASS-WITH-NITS`). Grill verdict is absence-OK in spec mode (PROGRESS shows ⏭️). Plus `items/001-spec.md` + `items/001-plan.md` presence.

## Project conventions to enforce (from CLAUDE.md + CONTEXT.md)

- **TDD red→green→refactor**; tests mirror source 1:1; `tests/narrative/` ↔ `src/irc/narrative/`.
- **Functional/immutable**: frozen dataclasses, `dataclasses.replace`, no arg mutation, no module-global mutable state.
- **Effects at edges**: I/O only in `holdings_fetch.py`, `config.py`, `narrative_cmd.py`; pure cores (`screen`, `risk`, `report`).
- **Size budget**: files < 200 lines, functions < 20 lines ideal.
- **Citation ID** locked 16-hex `\[ref:[0-9a-f]{16}\]`.
- **`基金概况` forbidden** in production fetch code (acceptance grep).
- **Live tests double-gated**: `pytest.mark.live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`.
- **No silent caps**: funds with no holdings → diagnostics file, logged, not dropped.
- Lint: `uv run ruff check src tests` (line-length 100, py312). Tests: `uv run pytest`.

## Open content decision (flag to user, non-blocking)

The `compute_metals` basket (spec §7) is **seeded as a draft** for user approval, then frozen. This run seeds a reasonable draft (copper/aluminium/tin + PCB-gold names tied to AI-datacenter demand) and flags it in the PR description for the user to approve/adjust. Seeding a draft is within autonomous scope; the *content* is user-approvable post-merge without a code change (it's config data).
