# MASTER-SPEC — Adversarial Review Fixes (2026-05-19)

**Source:** `outputs/2026-05-19/adversarial_review.md`
**Working branch:** `claude/adversarial-fixes-2026-05-19`
**Verification:** re-run `irc run` end-to-end against the 2026-05-19 inputs and
confirm none of the priority issues recur in the regenerated artifacts.

## Scope decisions

Every finding in the adversarial review is classified IN-scope or OUT-scope.
The IN-scope items are decomposed into 15 discrete tasks below. OUT-scope
items go to `SKIPPED.md` with a documented reason.

## IN-scope items

| ID | Title | Source ref | Touched code (primary) |
|---|---|---|---|
| 001 | Theme research query relevance | A1, A2 | `src/irc/research/theme_research.py`, `dispatch.py` |
| 002 | Thesis intact requires relevance | A2, A3 | `src/irc/opportunity/thesis_evidence.py`, `states.py` |
| 003 | Provider degradation gate | A4 | `src/irc/research/quality_gate.py`, `theme_research.py` |
| 004 | Source quality tiering | A5 | `src/irc/research/source_tier.py` (new), `synthesize.py` |
| 005 | Bond valuation uses yield anchor | B1 | `src/irc/opportunity/states.py`, `inputs_loader.py` |
| 006 | Wire gold's 6 drivers into tilt | B2 | `src/irc/scoring/gold_score.py`, `gold_band.py`, `pipeline.py` |
| 007 | Equity earnings-yield sanity anchor | B3 | `src/irc/opportunity/states.py`, `types.py` |
| 008 | Correlation filter caps intra-index | C1 | `src/irc/allocation/correlation_filter.py`, `pipeline.py` |
| 009 | Audit becomes a blocking gate | H | `src/irc/memo/auditor.py`, `pipeline.py`, `cli.py` |
| 010 | Role-bucket failure banner in memo | E | `src/irc/memo/synthesizer.py`, `template.py` |
| 011 | Scoring reweight for DCA horizon | G | `config/scoring.yaml`, scoring tests |
| 012 | Symmetric trim-side discipline triggers | F | `config/triggers.yaml`, `src/irc/opportunity/discipline.py`, `cards.py` |
| 013 | Execution-drift alert | C3 | `src/irc/decision/`, `src/irc/memo/synthesizer.py` |
| 014 | FX / QDII premium diagnostics | C4, C5 | `src/irc/memo/synthesizer.py`, `template.py` |
| 015 | Sector QDII sizing constraint | C2 | `src/irc/allocation/target_weights.py`, `inputs/preferences.yaml` |

## OUT-scope items

See `SKIPPED.md`.

## Acceptance criteria (cross-cutting)

After all items land, re-running `irc run` against the 2026-05-19 frozen
inputs must produce regenerated artifacts that satisfy ALL of:

1. `data/research/holdings_sector.md` cites at least one source whose
   extracted entities intersect a user holding or its sector code.
2. `thesis_cards.yaml` does not set `thesis_state: intact` for any card
   whose evidence list contains zero relevance-passing sources.
3. `proposed_allocation.yaml`: at most one S&P500 instrument, at most one
   Nasdaq100 instrument.
4. `gold_regime.json` (or its successor) includes a `drivers_score` field
   from `compute_gold_score`, OR a `drivers_unavailable` honest fallback.
5. `memo.md` Section 1 or 2 names the failed role buckets explicitly.
6. `memo.md` carries an execution-drift line when ≥5pp of target weight
   cannot be filled by venue.
7. `memo_audit.txt` says "审核通过" (audit passed) — or the publish step
   exits non-zero. No publishing with 高风险 issues outstanding.
8. `opportunity_report.json` bond rows derive `valuation_state` from a
   yield-curve anchor, not NAV percentile.
9. `config/scoring.yaml` has `valuation_cost ≥ 0.25`, `thesis_news ≤ 0.10`,
   and `weights_version` bumped.
10. `trade_plan.yaml` rows trigger `trim_review` where
    `valuation_state ∈ {expensive, very_expensive}` for ≥ N consecutive
    weeks (or first observation, if no history).
