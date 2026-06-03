Verdict: PASS-WITH-NITS

Source: /code-review on PR #101 (round 2)
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/101#issuecomment-4610020750
Round-1 latent bug (missing_valuation_data): CONFIRMED FIXED
Findings: 2 (both nits — loop-exit contract already met: 0 blockers, 0 latent bugs)
  - src/irc/opportunity/inputs_loader.py:178 — nit — docstring says "are inert until item 002" but item 001 (this PR) already activates valuation_percentile_fundamental via classify_valuation; stale wording misleads maintainers. **RESOLVED** (commit drop-dead-provider): docstring corrected to state the cached-read grounding.
  - src/irc/opportunity/inputs_loader.py:171,180 — nit — `provider` parameter is accepted and `default_cn_provider()` is instantiated but never used after the R3 migration; dead parameter obscures the cache-only design. **RESOLVED** (same commit): removed the dead `provider = provider or default_cn_provider()` assignment + the now-unused `default_cn_provider` import. The `provider` PARAMETER is intentionally kept (API stability + the AC6 no-live-fetch test passes a raising stub to prove the index path never calls it). Non-behavioral: ruff clean, 110 opportunity tests pass, risk.py/provider.py byte-identical to base.

Both nits were optional (PASS-WITH-NITS already satisfied the exit contract); addressed for quality. No re-review dispatched — the changes are non-behavioral doc + dead-code removal, fully covered by the existing tests + ruff.

## Round-1 fix verification
`_structural_evidence_gaps` at states.py:588-593 now requires all three of
`valuation_percentile_self`, `valuation_percentile_vs_benchmark`, AND
`valuation_percentile_fundamental` to be None before emitting
`missing_valuation_data`. Two regression tests confirmed in
tests/opportunity/test_states.py:437-474:
  - test_no_missing_valuation_gap_when_fundamental_percentile_present
  - test_missing_valuation_gap_when_all_three_percentiles_none
All 110 tests in test_states.py + test_inputs_loader.py pass.

## Not flagged (by design)
- R3: live provider.fetch_index_valuation removed from opportunity stage — by-design per spec §4.3.
- R4: CnFundamentalsProvider Protocol stays 3-method — by-design.
- No VERSION bump — project convention (accumulate under [Unreleased]).
- _BROAD_INDEX_KEYS private import in ingest_cmd.py — accepted cosmetic nit from round 1.
- test_build_rows_qdii_row_carries_sentinel_gap failure — pre-existing (Item 016 / commit 61ccf88 on base branch); this PR did not modify snapshot.py or opportunity_cmd.py.
