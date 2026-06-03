Verdict: PASS

Subagent: sonnet
Plan checklist items: 12
Verified present in diff: 12
Invariant checks:
  R1  PASS — `real_yield_10y = cn_10y_yield / 100.0` (ratio); `earnings_yield = 1.0 / pe_ttm` (ratio); `real_yield_10y_tips` not referenced anywhere in touched files.
  R2  PASS — single `valuation_divergence_code(inp)` detector; `classify_valuation` calls it for reason note only (signature stays `(state, reason)`); `build_opportunity_row` folds `_divergence_gaps(inp)` into `combined_gaps` before `_partition_gaps`.
  R3  PASS — `provider.fetch_index_valuation(...)` removed from `_index_valuation_metrics`; function now accepts `(con, tracked_index)` with no provider param; `populate_inputs` reads cached `index_valuation_history` table only; confirmed by `test_populate_inputs_no_live_index_fetch`.
  R4  PASS — `fetch_cn_index_valuation_history` not present in `src/irc/fundamentals/provider.py`; `git diff ... -- provider.py` is empty; provider Protocol stays 3-method.
  R5  PASS — `compose_opportunity_state` and `derive_contributing_dimensions` bodies unchanged in diff; `fundamental_contradiction` veto untouched; `valuation_state` set only by the band input.
  H3  PASS — `_partition_gaps` predicate unchanged; `valuation_price_fundamental_divergence` lands in `ADVISORY_GAP_CODES` → routes to `advisory_gaps` (non-blocking); `evidence_gaps == ()` invariant orthogonal.
  基金概況  PASS — `grep -rn "基金概況"` returns no hits in any touched file.
  risk.py-empty  PASS — `git diff feat/fundamental-valuation-grounding...claude/valuation-grounding-001 -- src/irc/narrative/risk.py` produces no output.
  provider.py-empty  PASS — same diff scoped to `src/irc/fundamentals/provider.py` produces no output.
  AC2  PASS — `classify_valuation`: when `fund_pct is None` branch falls back to `pct = _percentile(inp)`; `anchor_label = "估值百分位"`; regression test `test_fundamental_none_falls_back_to_nav_byte_for_byte` present.

Drift findings:
  - Task 2 (fetch_cn_index_valuation_history) — minor incidental divergence
    Evidence: `src/irc/fundamentals/akshare_index_valuation.py` lines 122-126 in diff: impl wraps `pe_df = _fetch_frame(...)` / `pb_df = _fetch_frame(...)` in a `try/except Exception: return None` block not present in the plan's step 3(c) code listing. `_fetch_frame` already catches all exceptions internally (returns `None` on failure), making the outer wrapper dead code. The contract (degrade-to-None on adapter failure) is identical; all 4 plan tests pass.
    Action: plan amended inline — Task 2 Step 3(c) note added (commit see below)

  - Task 11 (populate_inputs) — known-acceptable test migration scope (accepted per prompt context)
    Evidence: diff migrates 4 pre-existing tests off `_StubProvider(index_val=...)` to cached-table seeding, not the 2 named explicitly in the plan. The 4 extra tests (`test_populate_inputs_leaves_pe_pb_none_for_gold_and_bond`, `test_populate_inputs_consensus_upside_none_with_no_broker_reports`, `test_populate_inputs_consensus_upside_computed_when_reports_carry_targets`, `test_population_consumes_consensus_upside_per_item_002`) all only changed the pe/pb seeding mechanism and preserved original assertion intent.
    Action: accepted with rationale — necessary consequence of R3 removing the live-fetch seam.

CORRECTION (post-ship-review, by orchestrator): the "4 failing tests confirmed
pre-existing" context I gave this drift dispatch was WRONG for 2 of them. The
ship steps-8/9 review + an independent base-branch run found that
`tests/fundamentals/test_provider_migration.py::test_index_metrics_via_provider_matches_pre_migration`
and `::test_index_metrics_unknown_key_does_not_call_ak` PASS on base but FAILED on
this branch — i.e. they were R3 regressions, NOT pre-existing. They asserted the
pre-R3 contract (`_index_valuation_metrics(tracked_index, provider=...)` routing
through the provider) which R3 §4.3 deliberately replaced with a cached read, so
the old-signature calls raised TypeError. Resolution: the two obsolete
`_index_valuation_metrics`-via-provider locks were retired (same R3 churn category
as the Task-11 migrations); cached-read coverage lives in test_inputs_loader.py and
`provider.fetch_index_valuation` keeps its own coverage in test_provider.py (R4).
This does NOT change the code-drift verdict (PASS stands — all 12 plan tasks and
all invariants verified against the diff); it adds one more necessary test
migration the impl/drift passes missed. The genuinely pre-existing failures reduce
to 2: `test_build_rows_qdii_row_carries_sentinel_gap` and `test_only_stage_runs_single`
(both independently re-confirmed failing on base).
