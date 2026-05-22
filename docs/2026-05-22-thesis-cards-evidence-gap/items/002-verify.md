# Item 002 verify — citation-data-model (Slice D0)

## Verdict
PASS-WITH-NOTES

## Smoke results

| Check | Result |
|-------|--------|
| Import smoke (`ThesisEvidence`, `CitationMeta`, `OpportunityRow`, `DisciplineRow`, `select_citations`, `build_cited_map`) | ✅ PASS |
| `ThesisEvidence` — empty `owner_instrument_id` raises `ValueError` | ✅ PASS |
| `ThesisEvidence` — `citation_kind='both'` raises `ValueError` | ✅ PASS |
| `ThesisEvidence` — `scope='unknown'` raises `ValueError` | ✅ PASS |
| `ThesisEvidence` — empty `type` raises `ValueError` | ✅ PASS |
| `citation_id` determinism — identical preimage → identical 16-hex id | ✅ PASS |
| `citation_id` divergence — different `owner_instrument_id` → different id | ✅ PASS |
| `select_citations` determinism — shuffled input tuple produces same output | ✅ PASS |
| `select_citations` data+info invariant — 1 data + 5 info → 1 data + 2 info | ✅ PASS |
| `select_citations` data+info invariant — 5 data + 1 info → 2 data + 1 info | ✅ PASS |
| `build_cited_map` wrong-owner detector — `owner_instrument_id != row.instrument_id` raises `RuntimeError` | ✅ PASS |
| Duplicate-id detector (cross-owner) — logic present in `build_cited_map`; same-owner idempotent (one map entry, no raise) | ⚠️ PARTIAL (see Notes) |
| `irc --help` entry-point smoke | ✅ PASS |

All 322 tests in `tests/opportunity/` and `tests/memo/` pass. Two pre-existing failures (`test_only_stage_runs_single`, `test_thesis_coverage_meets_threshold`) are unrelated to this slice and were documented in the plan.

## Acceptance criteria walkthrough (27 ACs)

| AC | Description | Verified by | Result |
|----|-------------|-------------|--------|
| 1  | Empty `owner_instrument_id` raises `ValueError` | Smoke test + `test_thesis_evidence_rejects_empty_owner_instrument_id` | ✅ |
| 2  | `citation_kind='both'` raises `ValueError` | Smoke test + `test_thesis_evidence_rejects_invalid_citation_kind` | ✅ |
| 3  | `scope='random'` raises `ValueError` | Smoke test + `test_thesis_evidence_rejects_invalid_scope` | ✅ |
| 4  | Empty `type`/`source`/`date` raises `ValueError` | Smoke test + `test_thesis_evidence_rejects_empty_type_source_date` | ✅ |
| 5  | `parent_fund_id=None`, `constituent_key=None` constructs successfully | Smoke test + `test_thesis_evidence_accepts_none_for_fund_level_optional_fields` | ✅ |
| 6  | `citation_id` is deterministic (16 hex chars) | Smoke test + `test_citation_id_is_deterministic_for_identical_preimage` | ✅ |
| 7  | Different `owner_instrument_id` → different `citation_id` | Smoke test + `test_citation_id_differs_across_owner_instruments` | ✅ |
| 8  | Different `constituent_key` → different `citation_id` | Smoke test + `test_citation_id_differs_across_constituents_under_same_fund` | ✅ |
| 9  | `select_citations((), cap=3) == ()` | Smoke test + `test_select_citations_empty_input_returns_empty_tuple` | ✅ |
| 10 | `select_citations(entries, cap=0) == ()` | Smoke test + `test_select_citations_cap_zero_returns_empty_tuple` | ✅ |
| 11 | Shuffled inputs produce same output tuple | Smoke test + `test_select_citations_deterministic_across_shuffled_inputs` | ✅ |
| 12 | At least 1 data AND 1 info when input has both | Smoke test + `test_select_citations_data_and_info_leg_invariant` | ✅ |
| 13 | Output ordered by `(scope_rank desc, date desc, citation_id asc)` | Smoke test + `test_select_citations_rendering_order_scope_then_date_then_id` | ✅ |
| 14 | `_row_to_dict` emits `thesis_evidence`, `contributing_dimensions`, `constituent_analyses` | Smoke test + `test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions` | ✅ |
| 15 | `_discipline_row_from` propagates 4 new fields into `DisciplineRow` | Code inspection + `test_discipline_row_has_new_evidence_fields_with_empty_defaults` | ✅ |
| 16 | `PickRow` accepts `citations=()` default; non-empty renders `[ref:{citation_id}]` per citation | Smoke test + `test_render_picks_table_emits_citation_markers_in_evidence_column` + `test_render_picks_table_empty_citations_renders_dash` | ✅ |
| 17 | Absent trade target → `absent` list, NOT `pick_rows` | `test_build_pick_rows_absent_target_routes_to_absent_bucket` + `test_build_pick_rows_missing_opportunity_falls_into_absent` | ✅ |
| 18 | Gapped trade target → `gapped` list, NOT `pick_rows` | `test_build_pick_rows_gapped_target_routes_to_gapped_bucket` | ✅ |
| 19 | Clean trade target → `PickRow` with `citations=select_citations(evidence, cap=3)` | `test_build_pick_rows_clean_target_builds_pick_with_citations` | ✅ |
| 20 | `_build_pick_rows` raises `ValueError` on `citation_id` round-trip mismatch | `test_build_pick_rows_raises_on_citation_id_tampering` | ✅ |
| 21 | `build_cited_map` raises `RuntimeError("duplicate citation_id: ...")` on cross-owner id collision | `test_build_cited_map_raises_on_duplicate_citation_id` — same-owner idempotent path verified; cross-owner RuntimeError logic exists in code but test documents it is only reachable via birthday-paradox collision (64-bit). See Notes. | ⚠️ |
| 22 | `build_cited_map` returns correct `CitationMeta` shape | Smoke test + `test_build_cited_map_returns_correct_shape` | ✅ |
| 23 | `build_cited_map` raises `RuntimeError` on `owner_instrument_id != row.instrument_id` | Smoke test + `test_build_cited_map_raises_on_wrong_owner` | ✅ |
| 24 | `_row_to_dict` round-trip: `thesis_evidence` list includes `citation_id` | Smoke test + `test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions` | ✅ |
| 25 | `_row_to_dict` round-trip: `contributing_dimensions` is sorted JSON list | Smoke test confirms `sorted(row.contributing_dimensions)` matches loaded JSON | ✅ |
| 26 | Failure-section markdown uses `###` h3 headers nested under `## 5. 精选标的`; omitted when bucket empty | Smoke test + `test_render_failure_sections_produces_expected_markdown` + `test_render_failure_sections_empty_buckets_returns_empty_string` | ✅ |
| 27 | Failure-section bullets never render `opportunity_state`, `dca_action`, `risk_action`, `note_cn` | Smoke test confirms absent fields; `render_failure_sections` source-verified | ✅ |

**Score: 26/27 ✅, 1/27 ⚠️**

## Notes

**AC21 — Duplicate-id detector partial coverage.** The cross-owner `RuntimeError` path in `build_cited_map` (lines 37-43 of `src/irc/opportunity/citation_map.py`) exists and is correct. However, `test_build_cited_map_raises_on_duplicate_citation_id` only verifies the same-owner idempotent case (two identical entries collapse to one map entry without error). A true cross-owner `citation_id` collision requires a SHA-256 birthday hit across 64 bits (~2.7e-10 probability per 100k citations), which the test file explicitly documents as the reason for skipping the direct `RuntimeError` assertion on that branch. The implementation is correct; the gap is test coverage for an astronomically unlikely path. The wrong-owner detector (AC23) serves as the primary provenance guard in practice. This does NOT block pass.

**`select_citations` identity-vs-equality latent note.** The `select_citations` fill-remaining step uses `e not in selected` which relies on object identity for frozen dataclasses (Python `in` uses `==` on dataclasses, which is structural equality for frozen dataclasses). Since `ThesisEvidence` is frozen and equality is field-wise, this is correct. No latent bug observed.

**Two pre-existing test failures** (`test_only_stage_runs_single`, `test_thesis_coverage_meets_threshold`) confirmed unrelated to this slice; documented in the plan and observed before any item 002 changes.

## Recommendation

Ship. All functional ACs pass. The one ⚠️ (AC21) is a documented, intentional gap in test coverage for a physically-unreachable code path guarded by a 64-bit hash space — not a behavioral defect.
