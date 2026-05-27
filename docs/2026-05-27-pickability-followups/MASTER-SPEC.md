# MASTER-SPEC — Pickability Follow-ups (F4 / F5 / F6)

**Mode**: `backlog` (3 IN items)
**Detected at**: 2026-05-27
**Origin**: Deferred items from the `instrument-pickability` run (`docs/2026-05-27-instrument-pickability/SKIPPED.md`). The user has elected to close all three in a follow-up autodev run despite SKIPPED.md flagging that each needs preparatory work (an ADR, an eval-bench design, or a design conversation). That preparatory work is handled inside the per-item **grill** phase — which is exactly where ADR/CONTEXT.md authoring lives in backlog mode — and reflected in the per-item plan before implementation begins.

## Goal of the run

Deepen the evidence base feeding pick decisions, in three orthogonal directions:

1. **F4** — make `thesis_news` actually differentiate picks (currently 50 across the board because `news_summaries` arrives empty to `scoring/pipeline.py:116`).
2. **F5** — replace heading-only macro excerpts in memo §2 with paragraph-level summaries that survive the renderer.
3. **F6** — resolve the "filing data orphan" ambiguity (rows carry a "数值不得作为业绩依据" warning but still appear in evidence pools): either drop them from pick evidence or normalize `revenue_yoy` with explicit unit handling, then amend ADR 0001/0003 accordingly.

Together these close the "weak-evidence" critique surfaced in the prior review: when triggers eventually clear, the user reads §2 (macro), §5/§6 (picks + evidence), and §7 (decision) — and right now all three sections are thinner than they need to be for pick-time judgment.

## IN-scope items (3)

| ID | Title | Why it matters | Rough surface area |
|---|---|---|---|
| **F4** | `thesis_news` real-content scoring (replace 50-default) | `scoring/factors/thesis_news.py` already implements a real `score_thesis_news`, but `scoring/pipeline.py:116` calls it with `news_summaries.get(r.instrument_id, ())` — and in production `news_summaries` is empty, so every pick lands on the empty-input fallback (50.0). Real differentiation requires wiring per-instrument news (research summaries or news headlines) into the call site. | **Medium**: data plumbing (`commands/score_cmd.py` or pipeline) + scoring rubric refinement + ADR `thesis_news_scoring` + tests. SKIPPED.md flagged the ADR as the prerequisite. |
| **F5** | §2 macro research excerpts: heading → paragraph | Memo §2 currently shows only the heading or first line of each theme-research output. Truncation happens at either the research-summarizer (`research/synthesize.py`) or the `memo_synthesis` LLM prompt; `gold_regime.json["evidence"]` carries the data. SKIPPED.md asked for a 5-week historical bench before committing. | **Large**: paragraph-level summary prompt variant + eval-bench fixtures (5-week corpus) + regression test + memo §2 renderer changes. |
| **F6** | Filings evidence role: drop or normalize | `opportunity/thesis_evidence.py:_filing_evidence` emits filing rows; renderers carry the "数值不得作为业绩依据" warning but the row still influences `thesis_state` ranking. ADR 0001/0003 preserve filings as a "raw evidence archive" — semantics that conflict with the warning. SKIPPED.md called this a "design conversation, not autodev run". | **Medium**: ADR 0001 or 0003 amendment + either (a) drop filings from picks evidence pool OR (b) normalize `revenue_yoy` with declared unit + tests. The grill phase IS the design conversation. |

## Item ordering rationale

Provisional `F4, F5, F6` (small → large surface; F6 last because it amends an ADR that F4/F5 don't touch). Dep-scan confirms (see MASTER-PLAN.md): F4 touches `scoring/`, F5 touches `research/`+`memo/macro_pillar.py`, F6 touches `opportunity/thesis_evidence.py`+`memo/evidence_pool.py`. No shared write surfaces — items are independent and could run in parallel branches, but Mode A runs them sequentially into the feature branch by default.

## OUT-scope items

None. All three deferred items from the prior `SKIPPED.md` are IN-scope this run. No new deferrals expected; if grill discovers a hard pre-requisite (e.g., F5 needs an LLM eval framework that doesn't exist yet), the item moves to *this* run's `SKIPPED.md` with a written reason — not silently abandoned.

## Acceptance gate for the run

A simulated rerun (`uv run irc opportunity` against cached `outputs/2026-05-27/`, or a fixture pipeline if F4 needs fresh score recompute) produces:

1. **F4** — `thesis_news` scores differentiate at least 3 of the top-10 picks by ≥10 points (no longer all-50). Scoring still falls back to 50.0 when `news_summaries=()` (empty-input invariant preserved).
2. **F5** — `outputs/<date>/memo.md` §2 macro pillar renders ≥3 sentences (or ≥150 chars) per theme, not just the heading. Eval bench shows ≥4 of 5 historical weeks improved over the current truncation.
3. **F6** — Either (a) picks evidence-pool no longer contains `type="filing"` rows AND the H3/SAME-3 invariants still hold, OR (b) filing rows render `revenue_yoy` with a normalized unit + the "数值不得作为业绩依据" warning either removed or reframed in code+ADR.
4. No regression in existing IRC_*_BEGIN/END deterministic markers or H3/SAME-3 invariants.
5. All existing tests pass; new behavior covered by unit tests; pre-existing failures on `main` (the 7 enumerated in the prior run's `run-final-verify.md`) are not newly worsened.

## Known risks (declared upfront, before any phase fires)

- **F4 has a smaller blast radius than SKIPPED.md implied** — the factor function already exists; this is plumbing + rubric, not a green-field scoring redesign.
- **F5 is the riskiest** — paragraph-level summaries cost more LLM tokens and may drift across weeks. The eval-bench step is non-negotiable; if the grill phase concludes we cannot produce a 5-week corpus today, F5 falls back to a smaller spec ("publish first 3 sentences of existing summary; defer prompt redesign") and the larger goal moves to this run's `SKIPPED.md` with reason.
- **F6 is the most opinionated** — picking (a) drop vs (b) normalize is a real product judgment. The grill phase resolves it via design-conversation-as-grill; if the user (the grill subagent's interlocutor) cannot reach a decision, the item is shipped as ADR-amendment-only and code lands in a follow-up run.
