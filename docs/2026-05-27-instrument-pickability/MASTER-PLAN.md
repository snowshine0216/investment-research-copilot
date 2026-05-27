# MASTER-PLAN — Instrument Pickability Fixes

**Mode**: `backlog`
**Project type**: `non-web` — Python CLI (`irc` entry point), no browser surface. Post-ship verifier is `/verify` (XOR — never `/qa` for this run).
**PR shape**: `A` (per-item PRs into the feature branch, then one rollup PR you land yourself)
**Feature branch**: `autodev/instrument-pickability-feature` (synthesized off `main`, pushed)
**Sub-branch prefix**: `claude/instrument-pickability-`
**Item order**: pending dependency-scan; provisional `001, 002, 003`

## Phase contract per item (backlog mode)

Every IN item runs the full backlog pipeline:

```
spec (Opus brainstorming)
  → grill (Opus grill-with-docs auto-accept; writes CONTEXT.md / ADRs inline)
  → plan (Opus writing-plans)
  → branch
  → impl (Sonnet subagent-driven-development; TDD red-green-refactor)
  → drift (Sonnet in-prompt)
  → ship (/ship — opens PR into feature branch + captures review inline)
  → [/verify ‖ /code-review] (Sonnet, parallel)
  → fix (Sonnet, looped until all 3 post-ship verdicts PASS)
  → merge (gh pr merge --squash --delete-branch into feature branch)
```

No item-level shortcuts. Per-item exit requires all 6 verdict files (`grill`, `drift`, `ship`, `verify`, `review`, `pr-review`) at PASS or PASS-WITH-NITS.

## Project-specific constraints (read before any phase)

- **TDD is mandatory** — global CLAUDE.md says "All coding must follow TDD. Tests are written before implementation." No exceptions.
- **Functional, immutable** — pure functions, `const`-style by default, no mutation of arguments, files <200 lines, functions <20 lines.
- **Effects at edges** — I/O confined to `src/irc/data/`, thin wrappers, and `src/irc/commands/`. Stage cores stay pure.
- **Deterministic memo locks** — §2/§3/§5/§7 are between `IRC_*_BEGIN/END` markers; LLM content kept verbatim. New rows added by Items 002/003 must respect these markers.
- **H3 + SAME-3 invariants** — see CONTEXT.md "Renderers + alias-builder" and ADR 0004 before touching `_write_opportunity_outputs`.
- **Citation ID format** — `\[ref:[0-9a-f]{16}\]` (ADR 0001). Any new evidence rows must conform.
- **`基金概况` forbidden** — guarded by an acceptance test; do not introduce.
- **`thesis_state` setter** — set ONLY by `derive_thesis_from_evidence`. Item 001 must extend that function (or document a separate setter as an ADR), not bypass it.

## Run-level gates (end of Phase 2)

- `run-doc-sync.md` — Sonnet dispatch, verifies CONTEXT.md / `docs/adr/**` updates match every functional change across all 3 items
- `run-final-verify.md` — Sonnet `/verify` against integrated feature branch (likely runs `uv run irc opportunity` against the latest cached outputs to sanity-check pipeline still produces a memo)

Run is "done" only when both gates PASS plus every IN row has all 6 verdict files.

## Cost ceiling (declared)

Soft ceiling: 350K orchestrator tokens. If approached, STOP per `references/stop-conditions.md` and surface to user.

Per-item rough cost: 3 Opus dispatches (spec/grill/plan) + 4+ Sonnet dispatches (impl/drift/verify/pr-review/fix). N=3 → ~9 Opus + ~12+ Sonnet direct dispatches + run-level gates.
