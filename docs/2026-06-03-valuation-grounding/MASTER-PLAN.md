# MASTER-PLAN — Fundamental-Grounded Valuation (Phase 1)

**Mode:** spec
**Project type:** non-web    # Python CLI (`irc`); post-ship verifier = `/verify` (NOT `/qa`)
**PR shape:** A             # per-item PRs; no `--rollup` in the invocation
**Feature branch:** `feat/fundamental-valuation-grounding` (non-protected, non-default — sub-PRs land here)
**Base for final roll-up PR:** `main` (opened, NOT merged — left for the user)
**Run slug:** `valuation-grounding`
**Branch prefix:** `claude/valuation-grounding-`
**Item count:** N=1

## Per-mode skill skips (spec mode)

| Phase | Disposition |
|-------|-------------|
| brainstorming (spec authoring) | **SKIPPED** — user authored the design spec; copied verbatim to `items/001-spec.md`. |
| grill-with-docs | **PRE-COMPLETED ⏭️** — user-grilled (the spec carries a "§3 Resolved decisions from brainstorm" + "§3.1 spec-review findings R1–R5" trail). Orchestrator MUST NOT auto-invoke grill. |
| writing-plans (plan authoring) | **RUNS** — Opus subagent invokes `superpowers:writing-plans` against `items/001-spec.md`. |
| subagent-driven-development (impl) | RUNS (Sonnet). |
| drift / ship / verify / pr-review / fix / merge | RUN unchanged. |

## Workflow rules

- One PR per item (Mode A). Sub-branch `claude/valuation-grounding-001` cut off the feature
  branch; PR's base = `feat/fundamental-valuation-grounding`.
- Post-ship XOR: **/verify** (non-web). Never `/qa`.
- Review captured inline from `/ship` steps 8+9 → `items/001-review.md` (no separate dispatch).
- `/code-review` runs as its own downstream phase on the open PR → `items/001-pr-review.md`.
- Merge gate refuses without: `001-spec.md` + `001-plan.md` presence, and `^Verdict: PASS`
  on `{drift, ship(PR url), verify, review, pr-review}`. Grill verdict is absence-OK (⏭️).
- Protected-branch guard: the sub-PR's base is the feature branch (not protected) — OK to merge.
  The final feature→main roll-up PR is opened, never auto-merged.

## Phase 1 internal sequencing (lands inside the single plan/PR)

- **1a — data:** `fetch_cn_index_valuation_history` (AkShare-only, full series),
  `index_valuation_history` DuckDB table + `EXPECTED_TABLES` registration + ingest-stage writer.
  `real_yield_10y` derived from already-ingested `cn_10y_yield` (ratio). Lands inert.
- **1b — classifier:** new `OpportunityInput` fields, `populate_inputs` cached read (live provider
  call removed), `classify_valuation` fundamental-decides + divergence/PB notes + lit earnings-yield
  anchor, `valuation_divergence_code` + `build_opportunity_row` threading, `ADVISORY_GAP_CODES`
  entry, legend note. Activates the verdict change.
