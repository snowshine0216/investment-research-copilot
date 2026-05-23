Verdict: SHIP-BLOCKED — 2 P0 findings from /ship steps 8+9, must fix before push.

Source: /ship steps 8 (pre-landing parallel review) + 9 (adversarial deferred — review halted before push)

## P0 (blockers)

### P0-1: `_classify_rejection_reason` silently accepts unknown gap codes when paired with known ones

**File:** `src/irc/opportunity/rejection_log.py:181-187`
**Source:** silent-failure-hunter (step 8b)
**Issue:** Loop returns on FIRST match; only raises if ZERO gaps match `_GAP_TO_REASON`. Concrete: row with `evidence_gaps=("unknown_synthetic_gap", "holdings_fetch_failed")` returns `"holdings_fetch_failed"` silently — the unknown code goes undetected.
**Spec violation:** criterion 19 ("`_classify_rejection_reason` raises on unknown codes") + ADR 0003 §"Negative" ("silent acceptance of new codes would let bugs slip through").
**Test gap:** `test_classify_rejection_reason_unknown_gap_raises_runtime_error` (test_rejection_log.py:111) only covers the all-unknown case.
**Fix:** pre-scan all gaps; raise `RuntimeError` if ANY gap is not in `_GAP_TO_REASON` BEFORE returning the first-match. Add a regression test for the mixed-gap case.

### P0-2: `snapshot_cache_by_instrument` + `plan_hash` never passed in production

**File:** `src/irc/commands/opportunity_cmd.py:1001, 1052, 1152-1155`
**Source:** silent-failure-hunter (step 8b) + code-reviewer (step 8a) — both flagged independently
**Issue:** `_write_opportunity_outputs` accepts `plan_hash=""` and `snapshot_cache_by_instrument={}` kwargs but `run_opportunity` never passes them. Result: every production `rejections.json` ships `plan_hash: ""` (kills the ADR 0003 §4 audit-trail correlation key) AND `fund_level_failure_reasons: []` (criterion 22 "completeness" violated) even when the snapshot held them.
**Tests don't catch this:** the unit tests call `_write_opportunity_outputs` directly with the kwargs threaded; only the production caller misses them.
**Fix:** plumb `plan_hash` and `snapshot_cache_by_instrument` from `_build_rows` (the hash is already computed there) into `run_opportunity`'s call to `_write_opportunity_outputs`. Add a regression test that calls `run_opportunity` end-to-end and asserts `plan_hash` non-empty + at least one `fund_level_failure_reasons` populated.

## P1 (should fix in same round)

### P1-1: `_GAP_TO_REASON` missing entries for legacy-path gap codes

**File:** `src/irc/opportunity/rejection_log.py:171-187`
**Source:** code-reviewer (step 8a)
**Issue:** `_GAP_TO_REASON` omits: `news_stage_skipped`, `news_search_empty`, `news_llm_failed`, `missing_constituent_snapshot`, `missing_broker_coverage`, `constituent_missing`. All are real producers in `thesis_evidence.py:409-429` / `states.py:415`. Any non-active-fund row hitting the legacy path with one of these gaps → partitioned as gapped → `_classify_rejection_reason` raises `RuntimeError` → halts the whole opportunity run.
**Fix:** add mappings:
- `news_*` codes → `incomplete_constituent_data` (data leg ok, info leg degraded — semantically the closest match)
- `missing_constituent_snapshot` / `constituent_missing` → `incomplete_constituent_record`
- `missing_broker_coverage` → `incomplete_constituent_data`
Add a regression test that exercises each gap code through `_classify_rejection_reason`.

## Other notes (not blocking)

- P1 (adversarial deferred — step 9 not yet run because step 8 surfaced P0s; will rerun after fix)
- `record_fund_rejection` silently accepts `snapshot=None` (correctly handles non-active-fund rows; combined with P0-2 above this masks the missed-wiring bug but is logically OK once P0-2 is fixed)
- `_resolve_fund_level_snapshot` appends `nav_cache_write_failed:...` to `fund_level_failure_reasons` — a NEW gap reason string not in `_GAP_TO_REASON`. Today it only lands in `fund_level_failure_reasons`, not `evidence_gaps`, so P0-1's classifier is not reached. But if the boundary ever weakens, P0-1's strict-mode mapping would prevent the silent-first-match issue. Leave as-is for now.

## Fix loop instructions

1. Dispatch Sonnet fix subagent with this file as input.
2. After fixes land, re-invoke `/ship` (full workflow — re-runs preflight, merge, tests, step 8+9).
3. The new step 8+9 verdict (if PASS-WITH-NITS or PASS) replaces this ship-blocked.md by becoming `items/006-review.md`.
