Verdict: PASS

Subagent: claude-sonnet-4-6 (via /verify)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/60
Project type: non-web Python CLI
Branch: autodev/thesis-evidence-006-failure-mode-and-policy-b (49 commits over main)

## Entry-point smoke

Live `irc opportunity` was not run against live AkShare — the CLI requires external state (DuckDB schema, scoring outputs, AkShare network). Substituted per spec: fund-level integration tests that drive `_build_rows` + `_write_opportunity_outputs` through the full H3 pipeline.

**Command 1:** `python -m pytest tests/commands/test_opportunity_cmd_fund_level_integration.py -v`
**Exit code:** 0 (2 passed in 0.67s)

**Command 2:** `python -m pytest tests/commands/test_opportunity_cmd_h3_invariant.py -v`
**Exit code:** 0 (7 passed in 0.29s)

Substitute is comprehensive — it exercises the full `_build_rows` + `_write_opportunity_outputs` path including rejection log emit, discipline_report.md composition, V1 summary line, and H3 partition invariant. No AkShare mocking required because item 006 is pure audit/render logic on top of items 003+005's data flow.

**Full item 006 suite:** `python -m pytest tests/opportunity/test_policy_b.py tests/opportunity/test_rejection_log.py tests/opportunity/test_failure_renderer.py tests/commands/test_opportunity_cmd_h3_invariant.py tests/decision/test_discipline_v1_exclusions.py tests/fundamentals/test_types.py -v`
**Exit code:** 0 (101 passed, 1 skipped in 0.34s)

The 1 skip is `test_evaluate_policy_b_rule_5_direct_via_synthetic_construction` — explicitly `pytest.skip`'d by the author because rule 5 is structurally unreachable in V1 (rule 3 dominates; documented in the test itself; spec defers rule 5 direct exercise to item 009's integration test).

## Acceptance-criteria walkthrough (27 ACs)

### H1 — `rejection_log.py` schema + writer

| # | AC (paraphrased) | Approach | Evidence | Result |
|---|-----------------|----------|----------|--------|
| 1 | `record_fund_rejection` builds `RejectionRecord` with all required fields | test_rejection_log.py: `test_record_fund_rejection_with_active_fund_verdict` | PASS (all required fields present including constituent_coverage, fund_level_failure_reasons, fetch_types_attempted, evidence_gaps) | PASS |
| 2 | `ConstituentCoverageEntry.weight_rank` 1-based; ties by symbol ascending | test_policy_b.py: `test_build_coverage_entries_orders_by_weight_rank_ascending` + `test_rank_by_weight_ties_broken_by_symbol_ascending` | ranks [1,2,3] in order; ties sorted A→B→C | PASS |
| 3 | `in_material_top_half` matches `ceil(top_N/2)` semantics; boundary tie extends set | test_policy_b.py: `test_material_set_with_ties_top_10_no_ties` (ranks 1-5 → True), `test_material_set_with_ties_boundary_tie_extends_set` (6 entries when tied at cutoff) | Both PASS | PASS |
| 4 | `write_rejections_json` atomic write via `.tmp.{pid} → os.replace`; parent auto-created; JSON has `run_date`, `plan_hash`, `entries` keys | test_rejection_log.py: `test_write_rejections_json_writes_file_with_full_schema`, `test_write_rejections_json_creates_parent_dir` | Both PASS; uses `atomic_write_text` from `irc.io_utils` (same pattern as item 003) | PASS |
| 5 | `entries` ordering `(asset_class, instrument_id)` ascending; byte-identical two runs | test_rejection_log.py: `test_write_rejections_json_orders_entries_by_asset_class_then_id`, `test_write_rejections_json_byte_identical_two_runs` | Both PASS | PASS |
| 6 | Empty rejections case writes `entries: []` (not skipped) | test_rejection_log.py: `test_write_rejections_json_empty_entries_still_writes` | PASS | PASS |
| 7 | `MATERIAL_HOLDING_QUORUM(n)` == `math.ceil(n/2)`; QUORUM(10)=5, QUORUM(3)=2, QUORUM(1)=1, QUORUM(0)=0 | test_policy_b.py: 4 quorum tests | All PASS | PASS |

### H2.v2 — Policy B verdict + gap stamping

| # | AC (paraphrased) | Approach | Evidence | Result |
|---|-----------------|----------|----------|--------|
| 8 | All 10 holdings full dual-leg → publishable verdict, no rejection | test_policy_b.py: `test_evaluate_policy_b_publishable_5_of_5_decision_rule_template` | PASS; decision_rule contains "(publishable)" | PASS |
| 9 | 5/5 top-5 info-satisfied, tail data-only → publishable | test_policy_b.py: `test_evaluate_policy_b_rule_4_tail_data_only_passes_when_top_half_full` | PASS; gap_codes=() | PASS |
| 10 | 3 of material top-5 info-satisfied → `insufficient_info_coverage_top_half` | test_policy_b.py: `test_evaluate_policy_b_rule_4_info_quorum_partial` | PASS; decision_rule="info-leg quorum 5 of 10; 3 of material top-half satisfied" | PASS |
| 11 | Position with no data leg → `incomplete_constituent_data`; rule 3 fires before rule 4 | test_policy_b.py: `test_evaluate_policy_b_rule_3_data_leg_missing_one_holding` | PASS; gap_codes=('incomplete_constituent_data',) | PASS |
| 12 | All 10 with only `failure_reasons`, no evidence → `incomplete_constituent_data` (rule 3 dominates) | test_policy_b.py: `test_evaluate_policy_b_rule_3_all_holdings_failure_reasons_only` | PASS; "10 of 10" in decision_rule | PASS |
| 13 | `evidence==() AND failure_reasons==()` → `incomplete_constituent_record` audit error | test_policy_b.py: `test_evaluate_policy_b_rule_2_missing_constituent_record_audit_error`, `test_evaluate_policy_b_rule_2_coverage_entries_carry_audit_errors` | Both PASS; audit_errors tuple contains `missing_constituent_record:{symbol}` | PASS |
| 14 | Rule precedence: data-leg miss + info-leg miss → `incomplete_constituent_data` (not info quorum) | test_policy_b.py: `test_evaluate_policy_b_rule_3_precedence_over_rule_4` | PASS; gap_codes=('incomplete_constituent_data',) | PASS |
| 15 | `thesis_state` invariant: Policy B never modifies `thesis_state` | test_policy_b.py: `test_evaluate_policy_b_thesis_state_never_modified` | PASS; `evaluate_policy_b` returns `PolicyBVerdict` only, never touches `OpportunityRow.thesis_state` | PASS |
| 16 | `ConstituentAnalysis.audit_errors` default `()` at END of dataclass | tests/fundamentals/test_types.py: 3 audit_errors tests | All PASS; field at position `[-1]` confirmed | PASS |

### H3 — universal gapped-row invariant

| # | AC (paraphrased) | Approach | Evidence | Result |
|---|-----------------|----------|----------|--------|
| 17 | `_write_opportunity_outputs` skips thesis_cards + opportunity_report for gapped rows | test_opportunity_cmd_h3_invariant.py: `test_h3_partition_excludes_gapped_rows_from_thesis_cards`, `test_h3_partition_excludes_gapped_rows_from_opportunity_report_rows` | Both PASS; only publishable rows in yaml/json | PASS |
| 18 | Failure renderer reads ONLY 4 fields; no conclusion fields in output | test_failure_renderer.py: `test_render_failure_section_does_not_leak_conclusion_fields`, `test_render_failure_section_format_regex` | Both PASS; regex match; no `opportunity_state`/`dca`/etc. in output | PASS |
| 19 | All gap codes recognised; unknown raises `RuntimeError` (pre-scan of ALL gaps) | test_rejection_log.py: `test_classify_rejection_reason_unknown_gap_raises_runtime_error`, `test_classify_rejection_reason_mixed_known_and_unknown_raises` | Both PASS; pre-scan in rejection_log.py:195-199 raises on any unknown gap before returning | PASS |
| 20 | `fetch_budget_exhausted` → `RuntimeError` with "row-level emission is a programming error"; unconditional `raise` not `assert` | test_opportunity_cmd_h3_invariant.py: `test_h3_fetch_budget_exhausted_raises_immediately`; also run with `python -O` | PASS under both normal and `-O` mode; `raise RuntimeError(...)` at opportunity_cmd.py:1030 | PASS |
| 21 | Discipline bucket sections exclude gapped rows | test_opportunity_cmd_h3_invariant.py: `test_h3_discipline_bucket_sections_exclude_gapped` | PASS; gapped instrument_id absent from publishable sections | PASS |
| 22 | `rejections.json` records all gapped funds; publishable funds absent | test_opportunity_cmd_h3_invariant.py: `test_h3_rejections_json_lists_all_gapped_funds` | PASS; entries count matches gapped subset only | PASS |

### H4 — V1 systematic exclusions

| # | AC (paraphrased) | Approach | Evidence | Result |
|---|-----------------|----------|----------|--------|
| 23 | §1.2 footnote in `docs/diagnosis-thesis-cards-evidence-gap.md` with canonical text | test_decision/test_discipline_v1_exclusions.py: `test_diagnosis_doc_v1_footnote_intact` | PASS; text contains "V1 systematic exclusion" and "systematic exclusion of US-heavy" (test uses OR between two canonical phrases; doc text satisfies both) | PASS |
| 24 | Once-per-run V1 summary line emitted unconditionally (even when N=0) | test_opportunity_cmd_h3_invariant.py: `test_h3_v1_summary_line_emitted_unconditionally`; test_failure_renderer.py: `test_render_v1_systematic_exclusion_summary_zero_count` | Both PASS; "## V1 systematic exclusions: 0 funds excluded" rendered when no US-heavy funds | PASS |
| 25 | N counts US-heavy funds correctly; non-US-heavy excluded from count | test_failure_renderer.py: `test_render_v1_systematic_exclusion_summary_counts_us_heavy`, `test_render_v1_systematic_exclusion_summary_ignores_non_quorum_reasons` | Both PASS; strict majority US in material set required | PASS |

### MASTER-SPEC acceptance items 7 + 8

| # | AC (paraphrased) | Approach | Evidence | Result |
|---|-----------------|----------|----------|--------|
| 26 | Item 7: `rejections.json` exists after non-empty rejection run; all required fields present | test_rejection_log.py: `test_write_rejections_json_writes_file_with_full_schema`; H3 invariant integration test | PASS; JSON has instrument_id, name_cn, asset_class, rejection_reason, decision_rule, constituent_coverage (with weight_rank + failure_reasons), fund_level_failure_reasons, fetch_types_attempted, evidence_gaps | PASS |
| 27 | Item 8: discipline_report.md has once-per-run summary line naming US-heavy count | test_failure_renderer.py: `test_render_v1_systematic_exclusion_summary_counts_us_heavy`; H3 invariant integration test | PASS; count matches `_is_us_heavy` predicate on constituent_coverage | PASS |

**Total: 27/27 PASS** (1 test skipped — rule 5 direct; documented as structurally unreachable in V1, deferred to item 009)

## Specific verification checks (from request)

### H1 rejection_log schema
- `record_fund_rejection` writes `rejection_reason` from the closed Literal set — confirmed at `rejection_log.py:23-32` (`RejectionReasonCode` Literal). `decision_rule`, `constituent_coverage` with per-stock weight ranks + `failure_reasons` all present — confirmed by `test_record_fund_rejection_with_active_fund_verdict` PASS.

### H2.v2 Policy B rule precedence
- Rules implemented in order 1→2→3→4→5 in `policy_b.py`. Rule 3 short-circuits before rule 4 (criterion 14 locked test PASS). Per-holding data leg for ALL top-N (including tail — no tail exemption in rule 3). Info leg for `ceil(top_N/2)` material holdings with tie extension. All PASS.

### H3 gapped-row invariant
- `_write_opportunity_outputs` Step 1: `raise RuntimeError(...)` (NOT `assert`) confirmed at `opportunity_cmd.py:1030`. Verified with `python -O` — test still PASS.
- `fetch_budget_exhausted` fires BEFORE any `atomic_write_text` call (Steps 3-5 never reached).

### H4 V1 systematic exclusions
- `render_v1_systematic_exclusion_summary` emitted unconditionally even when N=0 (returns "0 funds excluded" string).

### Failure renderer reads ONLY 4 fields
- `failure_renderer.py:27-42`: `render_failure_section` reads only `instrument_id`, `name_cn`, `evidence_gaps`, `fetch_types_attempted` — confirmed by code inspection. `OpportunityRow` has no `note_cn` or `dca_action` field, confirming the 4-field-only constraint is type-enforced.

### `ConstituentAnalysis.audit_errors: tuple[str, ...] = ()`
- Added at end of dataclass in `src/irc/fundamentals/types.py`. Positional compat confirmed: `field_names[-1] == "audit_errors"` test PASS.

### `_build_rows` 7-tuple threading
- `_build_rows` returns `(rows, positions, qualities, roles, pending_verdicts, plan_hash, snapshot_cache_by_instrument)` — 7 elements, confirmed at `opportunity_cmd.py:921`. All 3 new elements threaded into `_write_opportunity_outputs` at `opportunity_cmd.py:1167-1170`.

### `_GAP_TO_REASON` legacy gap codes
- Covers: `news_stage_skipped`, `news_search_empty`, `news_llm_failed` (→ `incomplete_constituent_data`); `missing_constituent_snapshot`, `constituent_missing` (→ `incomplete_constituent_record`); `missing_broker_coverage` (→ `incomplete_constituent_data`). All 6 legacy codes confirmed in `rejection_log.py:77-85` and parametrized test `test_classify_rejection_reason_handles_legacy_gap_codes` (6 params, all PASS).

### `_classify_rejection_reason` strict pre-scan
- Pre-scan at `rejection_log.py:195-199`: scans ALL gaps before returning any result. `test_classify_rejection_reason_mixed_known_and_unknown_raises` verifies that a row with `("holdings_fetch_failed", "unknown_code")` raises even though the first gap is known. PASS.

### Fix-round commits present
- `2976add fix(opportunity): _classify_rejection_reason raises on any unknown gap` — confirmed in history
- `08a2bb7 feat(opportunity): _GAP_TO_REASON covers legacy news + constituent gap codes` — confirmed in history
- `eaa9863 fix(opportunity): plumb plan_hash + snapshot_cache_by_instrument through run_opportunity` — confirmed in history

## Regression checks (items 003+005)

`tests/commands/test_opportunity_cmd_fund_level_integration.py` (2 tests) — PASS. Items 003+005 paths untouched; `_build_active_fund_snapshot`, `_build_fund_level_snapshot`, and the QDII sentinel emitter are unmodified. The `ConstituentAnalysis.audit_errors` default `()` field is backward-compatible with all existing item 003 call sites.

## Environmental blockers

None for CLI verification. Live AkShare substituted with purpose-built integration tests as specified. No network, no external auth required.
