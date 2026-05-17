# P1 + P2 Backlog — Master Spec

**Date:** 2026-05-17
**Feature branch:** `feat/evidence-wiring-and-memo-enrichment`
**Source:** 7 items from the 2026-05-17 enhance/fix plan (P0 already merged in commits 11b9eb7..db43823).
**PR strategy:** one sub-branch per item, base = `feat/evidence-wiring-and-memo-enrichment`, sub-branch prefix = `claude/p1p2-`.

## Scope classification

| # | Item | Verdict |
|---|---|---|
| 005 | Don't classify `constituent_not_applicable` as an evidence gap | IN |
| 006 | Split `missing_recent_news` into `news_search_empty` / `news_llm_failed` / `news_stage_skipped` | IN |
| 007 | Rewrite memo traceability scorer (drop fake `coverage_ratio`) | IN |
| 008 | Backfill venue/proxy registry for `unknown` / `blocked_no_proxy` rows | IN |
| 009 | Backfill the 2-3 systematically missing fundamentals metrics | IN |
| 010 | Wire `geopolitical_stress_0to1` from news sentiment (TODO at `gold_cmd.py:74`) | IN |
| 004 | Gate downstream stages on ingest freshness | IN |

All 7 items are IN-scope. No silent omissions. (See `SKIPPED.md` — it is intentionally empty.)

## Execution order (smallest-risk first)

1. **005** — single file, surgical, smallest blast radius. Validates the loop.
2. **007** — single file, deterministic logic, no external dependencies. Picks approach (b): drop the misleading `coverage_ratio` and report raw counts (`n_refs_provided` / `n_refs_quoted_verbatim`). Rationale: option (a) requires changing LLM prompts, which adds variance to QA; option (b) is honest about what we can actually measure.
3. **010** — small, the news-sentiment input pipeline exists already (research stage emits theme_reports with sentiment). Wire one number through.
4. **006** — touches `research/theme_research.py` and `opportunity/thesis_evidence.py`. Two files, but the change pattern is the same in both.
5. **008** — data work, not code logic. Inspect today's report, list the unknown rows, add entries to the venue/proxy registry (`src/irc/trades/venue_check.py` or a config under `config/`).
6. **009** — requires diagnostic investigation first (which 2-3 metrics are missing). Then a fundamentals backfill in `src/irc/fundamentals/`.
7. **004** — largest blast radius. Touches at least three stage entry points (`gold_cmd.py`, `opportunity_cmd.py`, `memo_cmd.py`) plus a new freshness helper. Done last so it sees the most signal from items 5–9 before being added.

## Judgment calls made upfront (no further clarification)

- **Item 007 approach.** Picked (b) over (a). The traceability output schema changes: `coverage_ratio` is removed; `n_refs_provided`, `n_refs_quoted_verbatim` are added; `n_refs` stays as a back-compat alias for `n_refs_provided`. Any downstream consumer that read `coverage_ratio` gets a `KeyError` on next run — acceptable because the value was misleading anyway.
- **Item 008 acceptance.** "Backfill" means: every row currently `unknown` or `blocked_no_proxy` in `outputs/2026-05-17/decision_report.md` either gains `venue_compatible=true` or gains a `proxy_id`, OR is documented (in a code comment next to the registry) as genuinely unreachable. No silent gaps allowed.
- **Item 009 scope.** First investigate which metrics are missing using today's `outputs/2026-05-17/decision_report.json` and `scoring.json`. Then backfill *only* the systematically missing metrics, not all seven. If the gap is broader than 2-3, the item splits — but I expect 2-3 based on the 0.57 (4/7) and 0.71 (5/7) distribution.
- **Item 004 freshness window.** 24h is the design hint in the original plan; codify it as a configurable constant (default 24h) read from `settings.py`, not a magic number.

## Per-item acceptance criteria

Acceptance for every item:
- All existing tests still pass.
- New behavior has a test that fails before the change and passes after.
- The change does not require a re-ingest to take effect on the next pipeline run (no schema migrations).
- The PR description includes a "before/after" snippet from one of the `outputs/` artifacts.

## Out of scope for this loop

- Anything not on the P1/P2 list (no refactors, no new features).
- Re-running the actual ingest pipeline. We exercise downstream behavior via unit tests and the existing fixtures.
- Removing the akshare retry burn (P0 preflight already handles fail-fast).
- Adding a stale-data mode (explicitly rejected during P0).

## Cost / token budget

7 items × ~5 subagent dispatches each ≈ 35 dispatches. ~150-200K orchestrator tokens. No items are >20-item-equivalents, so no warning required.
