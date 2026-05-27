# MASTER-PLAN — Pickability Follow-ups (F4 / F5 / F6)

**Mode**: `backlog`
**Project type**: `non-web` — Python CLI (`irc` entry point), no browser surface. Post-ship verifier is `/verify` (XOR — never `/qa` for this run).
**PR shape**: `A` (per-item PRs into the feature branch, then one rollup PR you land yourself)
**Base branch**: `main` (default; protected — never auto-merged)
**Feature branch**: `autodev/pickability-followups-feature` (synthesized off `main`, pushed before any sub-branch is cut)
**Sub-branch prefix**: `claude/pickability-followups-`
**Item order**: `F4, F5, F6` (locked by dep-scan 2026-05-27)

## Dep-scan (2026-05-27)

Surface-area review on `main`:

| Item | Primary write surface | Secondary write surface |
|------|----------------------|-------------------------|
| F4 | `src/irc/scoring/pipeline.py` (~line 116), `src/irc/scoring/factors/thesis_news.py`, `src/irc/commands/score_cmd.py`, new `docs/adr/0007-thesis-news-scoring.md` | `src/irc/templates/config/scoring.yaml`, tests under `tests/scoring/factors/` |
| F5 | `src/irc/research/synthesize.py`, `src/irc/research/theme_research.py`, `src/irc/memo/macro_pillar.py`, `src/irc/templates/config/llm.yaml` (`memo_synthesis` task) | new `docs/adr/0008-macro-research-excerpt-depth.md`, tests under `tests/research/` + `tests/memo/` |
| F6 | `src/irc/opportunity/thesis_evidence.py`, `src/irc/memo/evidence_pool.py`, **ADR amendment to `docs/adr/0001-citation-data-model.md` AND/OR `0003-failure-mode-policy-b.md`** | tests under `tests/opportunity/` + `tests/memo/` |

**No shared write surfaces between items** — F4 / F5 / F6 are independent. Sequential ordering (Mode A default) is preferred over parallel because it preserves linear git history and lets each item's grill update CONTEXT.md before the next item references it.

Ordering rationale: F4 → F5 → F6 is small → medium → opinionated. Run the loop on F4 first to revalidate the autodev harness against this codebase. F5 last would also be fine but its eval-bench step is unfamiliar; better to do F5 in the middle so F6 (an ADR-driven design + small code change) lands with the most context. Order locked: **F4 (smallest, harness validation) → F5 (riskiest, mid-run when token budget is healthy) → F6 (design call, lands last)**.

## Phase contract per item (backlog mode)

Every IN item runs the full backlog pipeline:

```
spec   (Opus brainstorming)
  → grill (Opus grill-with-docs auto-accept; writes CONTEXT.md / ADRs inline)
  → plan  (Opus writing-plans)
  → branch
  → impl  (Sonnet subagent-driven-development; TDD red-green-refactor)
  → drift (Sonnet in-prompt)
  → ship  (/ship — opens PR into feature branch + captures review inline)
  → [/verify ‖ /code-review] (Sonnet, parallel)
  → fix   (Sonnet, looped until all 3 post-ship verdicts PASS / PASS-WITH-NITS)
  → merge (gh pr merge --squash --delete-branch into feature branch)
```

No item-level shortcuts. Per-item exit requires all 6 verdict files (`grill`, `drift`, `ship`, `verify`, `review`, `pr-review`) at PASS or PASS-WITH-NITS.

## Project-specific constraints (read before any phase)

- **TDD is mandatory** — global CLAUDE.md says "All coding must follow TDD. Tests are written before implementation." No exceptions.
- **Functional, immutable** — pure functions, `const`-style by default, no mutation of arguments, files <200 lines, functions <20 lines.
- **Effects at edges** — I/O confined to `src/irc/data/`, `src/irc/research/persistence.py`, thin wrappers, and `src/irc/commands/`. Stage cores stay pure.
- **Deterministic memo locks** — §2/§3/§5/§7 are between `IRC_*_BEGIN/END` markers; LLM content kept verbatim. F5's paragraph-level summaries must respect these markers — no new mutable rendering inside the locks.
- **H3 + SAME-3 invariants** — see CONTEXT.md "Renderers + alias-builder" and ADR 0004 before touching `_write_opportunity_outputs`. F6 changes to evidence-pool composition MUST keep picks/evidence-pool/discipline citation-set equality.
- **Citation ID format** — `\[ref:[0-9a-f]{16}\]` (ADR 0001). Any new evidence rows must conform.
- **`基金概况` indicator is forbidden** — guarded by an acceptance test that greps for the literal string in production fetch code.
- **`thesis_state` setter** — set ONLY by `derive_thesis_from_evidence`. F4 changes scoring rubric only — it must NOT bypass that function.
- **Live-test gate** — F5 eval bench may need live LLM calls; those are double-gated: a `pytest.mark.<name>` marker AND an `IRC_*=1` env var (see CONTEXT.md "Live test gate"). Eval bench commits with snapshot fixtures; live LLM tests stay opt-in.

## Run-level gates (end of Phase 2)

- `run-doc-sync.md` — Sonnet dispatch, verifies CONTEXT.md / `docs/adr/**` updates match every functional change across all 3 items (especially F4's new ADR, F5's potential new ADR, and F6's ADR amendment).
- `run-final-verify.md` — Sonnet `/verify` against integrated feature branch (`uv run irc opportunity` against `outputs/2026-05-27/`; also full `uv run pytest` against the feature branch with the 7 pre-existing failures called out).

Run is "done" only when both gates PASS plus every IN row has all 6 verdict files.

## Cost ceiling (declared)

Soft ceiling: **450K orchestrator tokens** (50K higher than the prior pickability run because F5's eval bench step is unfamiliar and likely needs extra back-and-forth). If approached, STOP per `references/stop-conditions.md` and surface to user with a written status of which items remain.

Per-item rough cost: 3 Opus dispatches (spec/grill/plan) + 4+ Sonnet dispatches (impl/drift/verify/pr-review/fix). N=3 → ~9 Opus + ~12+ Sonnet direct dispatches + run-level gates.

## Branching protocol

1. Synthesize `autodev/pickability-followups-feature` off `main` at run start; push immediately.
2. Each item sub-branch (`claude/pickability-followups-{F4,F5,F6}`) is cut off the **feature branch** (not main), so item-N picks up item-(N-1)'s merged ADR/CONTEXT.md updates.
3. Each item's `/ship` opens a PR `claude/... → autodev/pickability-followups-feature`.
4. Each item's merge is `gh pr merge <PR#> --squash --delete-branch` into the feature branch.
5. Final close-out opens `autodev/pickability-followups-feature → main` as a rollup PR; user lands it. No auto-merge to `main`.
