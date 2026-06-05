# PROGRESS — Phase A: Broad-index valuation grounding

**Mode:** spec · **Project type:** non-web · **PR shape:** A
**Feature branch:** `claude/stupefied-banach-f1f037` · **Base:** `main` (roll-up PR, not merged)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

| id  | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ⏭️ | ⏭️ | ✅ | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

> **QA column omitted by design** — project is non-web (XOR resolves to `verify`). `items/001-qa.md` must NOT exist.

## Cell notes

- **001 spec** ⏭️ `user-provided` — verbatim copy at [`items/001-spec.md`](items/001-spec.md).
- **001 grill** ⏭️ `user-grilled` — orchestrator must not auto-invoke (spec mode). Any doc gaps caught by Phase-3 run-level doc-sync.
- **001 plan** → Opus `superpowers:writing-plans` (ENTRY).

## Evidence cells (filled as phases pass; bare ✅ is not enough)

- **001 plan** ✅ → [`items/001-plan.md`](items/001-plan.md) (10 tasks / ~60 steps, 29 verification commands; commit `c96025a`). TDD-ordered; approved by orchestrator.

## Environmental boundaries (operator follow-ups, not loop failures)

The source spec's exit gates #3/#4/#5 require real network + cache + LLM and are labeled "operator/human gates" in the spec and plan. The autonomous loop produces all code/tests/script/docs offline; these remain operator follow-ups after merge:
- **Gate #4 (live confirmation):** `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py` (hard-asserts the 4 production symbols return rolling PE+PB).
- **Gate #3 (measured coverage ≥9):** `irc run --from ingest` (network) + count grounded broad funds.
- **Gate #5 (before/after artifact):** `docs/2026-06-05-phase-a-broad-grounding/build_diff.py` is committed; generating `before-after.md` needs a baseline-vs-after ingest (network). Artifact noted PENDING-LIVE in the PR body.
