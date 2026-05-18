# SKIPPED — out-of-scope items

The source spec is a two-phase plan. **Phase 2 (green active suite) is OUT-of-scope for this autonomous run** because every Phase-2 item is gated on the truthful reports produced by the Phase-1 changes landing first, and most Phase-2 work is judgment-heavy (which metrics to redesign, which product defects to fix, whether to keep or retire stages).

The list below preserves every Phase-2 item with its blocker and the explicit unblock path. After Phase 1 lands, the user (or a subsequent autodev-loop run scoped to Phase 2 specifically) should re-run `irc eval --all`, classify the fresh reports, and pick up here.

## OOS-A — Phase 2A re-run and classify

- **Blocker:** Bucketing failures into (real defect / metric defect / unfinished / retained warning) requires a human's read of the fresh reports and the surrounding product intent. Cannot be done autonomously without conflating product judgment with eval truthfulness.
- **Unblock:** After Phase 1 merges, run `uv run irc eval --all` against the current outputs, paste the resulting report contents into a new spec, and triage each non-PASS into one of the four buckets.

## OOS-B — Phase 2B metric redesign

Items the spec calls out by name:

- `opportunity.same_theme_distinct_index_limit` — collapses untheme rows into a single `_unthemed` bucket, so unrelated assets (gold, bonds, Nasdaq, S&P) count as one theme. Fix is a redesign: probably treat missing theme as a distinct identity per row, or as "ungrouped" excluded from the limit.
- `scoring.score_distribution_stability` — current implementation compares first-half vs second-half of a single list, which is order-sensitive and not a temporal stability measurement. Fix is a redesign against the design-doc invariant.
- Any `gold_score`, `allocation`, or `memo` metric that cannot be grounded in the current producer's outputs (surfaced by items 006/007/009 of Phase 1).
- **Blocker:** Each requires a design-level decision on what invariant the metric should express.
- **Unblock:** Open a per-metric design spec; the answer informs the new metric implementation.

## OOS-C — Phase 2C real product/data defects

- Data freshness WARNs if the "fresh within two days" operating bar is still desired.
- Scoring completeness gap remaining after fresh artifacts are evaluated.
- `src/irc/commands/ingest_cmd.py` at 632 lines exceeds the `max_file_loc` threshold — real refactor candidate.
- **Blocker:** Each is a product-side change (refactor, contract change, threshold-vs-bar negotiation). Outside the scope of "fix the eval framework."
- **Unblock:** Open product-side specs after Phase 1 reports identify which gaps are real.

## OOS-D — Phase 2D unfinished or inactive surfaces

- `triggers`: active eval but no metrics implemented (intentional FAIL). Either implement, or decide product no longer needs trigger semantics.
- `queries`: `irc ask` writes no persisted artifact. Either add persistence (then re-activate eval) or retire the eval.
- `news`: no live CLI producer. Either re-introduce a news stage or retire the runner.
- **Blocker:** Each is a product-direction decision.
- **Unblock:** Product owner picks implement vs. retire per stage; corresponding code change follows.

## OOS-E — Phase 2E green active suite end state

- **Blocker:** Composite outcome of OOS-A through OOS-D.
- **Unblock:** Reached automatically once 2A–2D resolve.
