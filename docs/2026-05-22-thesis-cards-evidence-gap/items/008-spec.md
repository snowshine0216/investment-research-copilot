# Item 008 spec — integration test sweep (Slice E)

**Source slice:** `docs/diagnosis-thesis-cards-evidence-gap.md` lines 221–242 (Slice E, sub-items E1–E17).
**Master-spec line:** `008 | integration-test-sweep` (one-liner: "E10 coverage smoke across V1 asset classes + any E1–E17 not folded into 002–007 + green-before-009").
**Branch:** `autodev/thesis-evidence-008-integration-test-sweep` (cut from feature branch `autodev/thesis-cards-evidence-gap` after grill).
**Dependencies in:** items 001–007 (merged on feature branch). **Dependents out:** item 009 will NOT flip the citation gate to `block` mode until item 008's tests are green on the feature branch.

**Grill verdict:** PASS (see `008-grill.md`). All seven open questions auto-resolved against existing project precedent; one new invariant family (pipeline-level byte equality) added; CONTEXT.md gains one term; no ADR amendment needed.

## 1. Goal

Lock the **publishable set** end-to-end before item 009 flips `IRC_CITATION_ENFORCE_MODE=block` on canonical paths. "Publishable set" = the set of rows that survive `_write_opportunity_outputs`' H3 partition and reach `thesis_cards.yaml`, the `opportunity_report.json` `rows` array, the `memo.md` picks-table, and the discipline-report bucket sections (NOT the `## 证据不足 / Failed fetch` section). Item 008 adds the missing cross-cutting integration layer that asserts every published row satisfies the citation / scope / state / asset-class invariants when read back from on-disk artifacts after a full `run_opportunity` (and minimally `run_memo`) execution. Items 002–007 shipped extensive unit + scenario tests for individual components; item 008 binds them together at the artifact-read level so item 009's block-mode gate has a known-clean baseline.

## 2. What's already covered (E1–E17 audit)

Read of `tests/` on the feature branch as of commit `178ac04` (post-item-007 merge):

| #     | E-item spec | Existing test(s) | Status |
|-------|-------------|------------------|--------|
| E1    | `cn_equity_fund` thesis-state intact with 3 filing + 3 broker entries | `tests/opportunity/test_thesis_evidence.py::test_intact_when_strong_majority_positive_yoy_and_neutral_brokers` + `::test_intact_when_majority_positive_and_buy_broker_consensus` + `::test_evidence_includes_filing_entries` + `::test_evidence_includes_broker_entries` (item 003) | **COVERED (unit)** |
| E2    | Themed `cn_equity_fund` routes to `active_fund` not `sector_theme` | `tests/opportunity/test_lookthrough.py::test_map_lookthrough_cn_equity_fund_themed_routes_to_active_fund` (+ unthemed + tracked-index variants, item 003) | **COVERED (unit)** |
| E3    | `_row_to_dict` round-trips `thesis_evidence`; `compose_discipline_markdown` renders nested bullets | `tests/opportunity/test_report.py::test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions` + `::test_render_section_emits_top_3_nested_bullets` + `::test_render_section_nested_bullet_format` (items 002 + 007) | **COVERED (unit)** |
| E4    | Evidence-pool emits filing + news URLs + `[stock:XXX]` tag | `tests/memo/test_evidence_pool.py::test_build_evidence_pool_emits_ref_markers` + `::test_build_evidence_pool_emits_stock_marker_for_constituent_scope` (item 007) | **COVERED (unit)** |
| E5    | `PickRow.citations` non-empty renders cell, empty renders `—` | `tests/memo/test_picks_table.py::test_render_picks_table_emits_citation_markers_in_evidence_column` + `::test_render_picks_table_empty_citations_renders_dash` (item 002) | **COVERED (unit)** |
| E6    | `find_missing_citations` finding matrix (a–j: missing data leg, missing info leg, wrong-instrument, etc.) | **MISSING** — `tests/memo/test_numeric_audit.py` only covers `find_cheap_prose_when_state_is_expensive`-style numeric findings and the `find_uncited_conclusions` empty-alias precondition. The `find_missing_citations` function does **not yet exist** in `src/irc/memo/`; it is on item 009's surface (D2a-2b). **DEFERRED to item 009.** Item 008 does not add E6 tests. |
| E7    | Audit-blocking path-matrix (canonical+block / canonical+warn / non-canonical+warn / non-canonical+off) | `tests/memo/test_audit_blocking.py` exists but covers `audit_passed/failed` token blocking only — NOT the canonical-path × env-var matrix. The matrix gate itself ships with item 009. **DEFERRED to item 009.** |
| E8    | Snapshot cache freshness probe (within-window / expired / probe-fail / new-quarter) | `tests/fundamentals/test_snapshot_cache.py` covers cache write/load/round-trip + atomic tmp suffix (item 003); **freshness-probe scenarios E8(a)–(d) are MISSING.** The probe logic shipped with item 003 but the per-scenario tests did not. **Item 008 ships E8.** |
| E9    | `_build_active_fund_snapshot` empty AkShare → `failure_reasons_by_symbol` populated + downstream `evidence_gaps=["holdings_fetch_failed"]` + `opportunity_state="exclude"` | `tests/fundamentals/test_snapshot.py::test_build_snapshot_active_fund_empty_holdings_records_fund_level_failure` covers the snapshot side; **downstream propagation through `run_opportunity` is MISSING.** Item 008 ships the end-to-end half. |
| **E10** | **Coverage smoke across V1 asset classes (cn_equity_fund, cn_bond_fund, gold, cn_etf) + QDII exclusion** | `test_opportunity_cmd_h3_invariant.py` covers gapped-row partitioning for ONE row at a time; `test_opportunity_cmd_fund_level_integration.py` covers the 3-row gold+bond+cn_etf dual-coverage at `_build_rows` level only. **End-to-end across all 4 V1 + 3 QDII asset classes via `run_opportunity` is MISSING.** This is **item 008's flagship test.** |
| E11   | Manual rerun checklist for `irc run --from opportunity` | This is a docs-only manual rerun. Captured in `<id>-verify.md` at ship time per autodev workflow. **Not in scope for item 008's test code** — listed in the spec for completeness. |
| E12   | `fetch_fund_nav_report("518880")` returns `FundNavReport` with non-null `nav_latest`; unknown fund_id → `evidence_gaps=["fund_nav_unavailable"]` | `tests/fundamentals/test_fetch_fund_nav_report.py` exists (item 005). | **COVERED (unit)** |
| E13   | Live AkShare verification of `fund_announcement_em` | Item 004 PR #58 — live tests at `tests/fundamentals/test_fund_announcement_em_live.py` + failure-mode mocks. | **COVERED (live + mocked)** |
| E13b  | Citation-selector determinism across shuffled inputs | `tests/memo/test_citation_selector.py::test_select_citations_deterministic_across_shuffled_inputs` + `::test_select_citations_data_and_info_leg_invariant` + `::test_select_citations_rendering_order_scope_then_date_then_id` (item 002) | **COVERED (unit)** |
| E14   | `build_alias_maps` instrument + constituent alias correctness | `tests/memo/test_aliases.py::test_build_alias_maps_instrument_aliases_basic` + `::test_build_alias_maps_constituent_aliases_multi_owner` (item 007) | **COVERED (unit)** |
| E15   | `find_uncited_conclusions` empty-alias precondition | `tests/memo/test_numeric_audit.py::test_find_uncited_conclusions_empty_aliases_with_empty_prose_returns_empty` + `::test_find_uncited_conclusions_empty_aliases_with_non_empty_prose_returns_empty` + `::test_find_uncited_conclusions_non_empty_aliases_does_not_raise` (item 007 amended the empty-alias semantics post-grill; **raises only when prose is non-empty AND aliases are empty**, per item-007 fix-round-1) | **COVERED (unit)** |
| E16   | Multi-owner constituent resolution | `tests/memo/test_aliases.py::test_build_alias_maps_constituent_aliases_multi_owner` (item 007); the **section-header disambiguation + `ambiguous_constituent_reference` finding** is on item 009's surface. **Item 008 ships the multi-owner alias-map regression at the publishable-set level.** |
| E17   | Alias collision invariant (`InstrumentAliasCollisionError`) | `tests/memo/test_aliases.py::test_build_alias_maps_instrument_collision_raises` + `::test_build_alias_maps_collision_error_message_lists_iids_sorted` (item 007) | **COVERED (unit)** |

**Gap summary (what item 008 ships):** **E8 freshness-probe scenarios** (3 tests), **E9 downstream propagation through `run_opportunity`** (1 test), **E10 publishable-set coverage smoke across all 4 V1 + 3 QDII asset classes via `run_opportunity` end-to-end** (1 flagship test + 4–5 narrower invariant tests), **one cross-stage `run_opportunity → run_memo` SAME-3 / citation-id-subset test**, and the **pipeline-level two-run byte-equality invariant family** (new in grill — see ACs 22–23). E6 and E7 are on item 009's authoring surface and are deferred to that item.

## 3. Acceptance criteria

The publishable-set-lockdown integration tests live in **one new file**: `tests/integration/test_publishable_set_lockdown.py`. All ACs below are assertions made in that file after a `run_opportunity(repo_root=str(tmp_path))` call (or `_write_opportunity_outputs` for ACs that exercise the partition directly), with on-disk artifacts deserialized and inspected.

**Test-isolation harness (applies to all ACs):** each test sets the following env vars via `monkeypatch.setenv` to lock the cache + budget gates to deterministic defaults:
- `IRC_OPPORTUNITY_AUTOBUILD=1` (default; explicit for clarity)
- `IRC_CACHE_FRESHNESS_DAYS=7` (default; ACs 16/17 override per scenario)
- `IRC_FETCH_BUDGET=2000` (default; some ACs override to test the fatal sentinel)
- `IRC_ALLOW_STALE=1` (bypass ingest staleness so the harness can short-circuit `STALE_INGEST.md` blocking)

**Memo route mocking (applies to ACs 19/20/22/23 that invoke `run_memo`):** per the precedent locked in `tests/commands/test_memo_cmd_aliases.py:98–99`, patch both routes with `unittest.mock.patch`:
```python
with patch("irc.memo.synthesizer.call_chat", return_value=_resp("<synth body with [ref:...] markers>")), \
     patch("irc.memo.auditor.call_chat", return_value=_resp("审核通过")):
    run_memo(str(tmp_path))
```
The synth body for cross-stage ACs is built by harvesting citation_ids from the just-written `opportunity_report.json` so the memo's `[ref:...]` markers are a deterministic subset of the publishable citation universe.

### Publishable-set citation invariants (E10 family)

1. **Dual-leg coverage on every published row.** After `run_opportunity` seeds with one instrument per V1 asset class (`cn_equity_fund: 005827`, `cn_bond_fund: 000001`, `gold: 518880`, `cn_etf: 510300`) + one per QDII variant (`qdii_us`, `qdii_hk`, `qdii_global`), assert every row in `opportunity_report.json["rows"]` carries ≥1 evidence entry with `citation_kind="data"` AND ≥1 with `citation_kind="information"`. No row has both legs absent. No row has a `citation_kind` value outside `{"data","information"}` (the legacy `"both"` is forbidden per ADR 0001).

2. **Owner-instrument provenance.** For every entry in every published row's `thesis_evidence`, `entry.owner_instrument_id == row.instrument_id`. No cross-instrument leakage.

3. **Scope is publishable.** For every entry in every published row's `thesis_evidence`, `entry.scope in {"instrument", "constituent"}`. No `asset_class_macro` / `policy` -scoped evidence appears alone on a published row (macro/policy entries may co-exist alongside an instrument/constituent entry, but never as the sole evidence basis).

4. **`thesis_state` literal-only.** Every published row's `thesis_state` is exactly one of the four `ThesisState` literals: `{"intact", "under_pressure", "falsified", "evidence_insufficient"}`. No synthetic partial values (e.g., `"partial_evidence"`) appear.

5. **`evidence_gaps` empty on publish.** Every published row has `evidence_gaps == []` (serialized form of the empty tuple). The H3 universal gapped-row invariant guarantees this at `_write_opportunity_outputs` time; AC5 re-asserts it after JSON round-trip to catch serializer drift.

### QDII exclusion invariants

6. **QDII never appears in `thesis_cards.yaml`.** After the seeded run, parse `thesis_cards.yaml` and assert no card has `asset_class in {"qdii_us","qdii_hk","qdii_global","us_etf","hk_etf"}`. QDII rows MUST appear only in the discipline failure section.

7. **QDII never appears in `opportunity_report.json["rows"]`.** Same set check against the published `rows` array.

8. **QDII present in `rejections.json` with `qdii_information_unavailable` reason.** Every seeded QDII instrument appears in `rejections.json["entries"]` with `rejection_reason == "qdii_information_unavailable"`.

9. **QDII present in `discipline_report.md` failure section.** Every seeded QDII instrument's `instrument_id` appears in `discipline_report.md` *after* the `## 证据不足` heading (locked as the canonical failure-section heading by `tests/commands/test_opportunity_cmd_h3_invariant.py::test_h3_discipline_report_failure_section_includes_gapped_rows`), and does NOT appear in any bucket section above that heading.

### H3 / Policy-B precedence invariants (end-to-end)

10. **H3 partition holds across all four output surfaces.** Construct a seed mix where one row has `evidence_gaps=()` (publishable) and one has `evidence_gaps=("insufficient_info_coverage_top_half",)` (Policy-B gapped). After `run_opportunity`, assert: (a) only the publishable iid in `thesis_cards.yaml["cards"]`, (b) only the publishable iid in `opportunity_report.json["rows"]`, (c) only the publishable iid in `discipline_report.md` bucket sections, (d) only the gapped iid in `rejections.json["entries"]`, (e) the gapped iid present in `discipline_report.md` failure section.

11. **Policy-B precedence renders `qdii_information_unavailable` over Policy-B codes.** Seed a QDII row that carries BOTH `qdii_information_unavailable` AND `insufficient_info_coverage_top_half` in `evidence_gaps` (in that order, since dict-insertion order in `_GAP_TO_REASON` puts qdii first). Assert `rejections.json` classifies its `rejection_reason` as `"qdii_information_unavailable"` (precedence rule per `src/irc/opportunity/rejection_log.py::_classify_rejection_reason` + ADR 0003). **Implementation note:** AC11 hard-codes the expected string with a `# precedence per src/irc/opportunity/rejection_log.py::_GAP_TO_REASON dict-iteration order + ADR 0003` comment. The `_GAP_TO_REASON` constant IS the machine-readable precedence; AC11 asserts against the observable consequence (the rejection_reason string), not the constant's internal ordering — the constant is an implementation detail item 008 must not depend on by direct import.

12. **`fetch_budget_exhausted` is fatal at write time.** If `_write_opportunity_outputs` is invoked with any row carrying `"fetch_budget_exhausted"` in `evidence_gaps`, `RuntimeError` is raised before any `.tmp` file becomes visible. (Note: `test_opportunity_cmd_h3_invariant.py::test_h3_fetch_budget_exhausted_raises_immediately` already covers this at the partitioner level; AC12 re-asserts via `run_opportunity` to confirm the error propagates through the command layer without partial-write artifacts.)

### 持仓明细 appendix integrity (D3b)

13. **Appendix line shape per publishable row.** For every publishable `cn_equity_fund` / `cn_etf` row that has non-empty `constituent_analyses`, the `discipline_report.md` `## 持仓明细` appendix contains a `### {instrument_id} {name_cn}` subheading followed by ≥1 bullet line matching the regex `^- \S+ .+ \(权重 [\d.]+%\): (✅|❌|⚠️) .+$`. Audit-error suffix (` — audit_errors: ...`) is permitted when present.

14. **Appendix omitted for QDII.** QDII rows do NOT have a `### {instrument_id}` subheading in the `## 持仓明细` appendix (they appear in the failure section only).

### Snapshot-cache freshness (E8 family)

15. **Within-window read hits cache; zero AkShare calls.** Pre-write an `ActiveFundSnapshot` cache with `cache_probed_at` = today. Patch `_ak_call` with a call counter. Run `run_opportunity`. Assert the counter is 0 for the cached fund_id.

16. **Expired-window probe + same-quarter result reuses cache.** Pre-write an `ActiveFundSnapshot` cache with `cache_probed_at` older than `IRC_CACHE_FRESHNESS_DAYS` (default 7; CONTEXT.md "Fail-closed freshness probe"). Patch the probe call to return the same `source_report_quarter`. Run `run_opportunity`. Assert only the lightweight probe call was made (no full re-fetch) and the cache's `cache_probed_at` is updated to today.

17. **Probe failure → fail-closed re-fetch.** Pre-write a cache as in AC16. Patch the probe to raise `RuntimeError("network error")`. Run `run_opportunity`. Assert a full re-fetch is triggered (call counter > probe-only count). Per CONTEXT.md "Fail-closed freshness probe": probe failure forces full refetch — never silent-reuse.

### E9 downstream propagation

18. **Empty AkShare holdings flow to `evidence_gaps=["holdings_fetch_failed"]` + exclude.** Seed a `cn_equity_fund` row; patch `_ak_call` such that `_build_active_fund_snapshot` returns `ActiveFundSnapshot.constituent_analyses == ()` and `failure_reasons_by_symbol` non-empty. After `run_opportunity`, assert the row appears in `rejections.json` with `evidence_gaps` containing `"holdings_fetch_failed"` (or the canonical mapped equivalent) and NOT in `thesis_cards.yaml`.

### Cross-stage SAME-3 / citation-id-subset (run_opportunity → run_memo)

19. **`memo.md` cites only publishable citation_ids.** After seeding + running `run_opportunity` THEN `run_memo` against the same `tmp_path`, parse all `[ref:{id}]` markers from `memo.md` and assert each id appears in the **publishable citation universe** defined as:
    ```
    universe = {citation_id for row in opportunity_report.json["rows"]
                            for entry in row["thesis_evidence"]}
             ∪ {citation_id for entry in gold_regime.json.get("evidence", [])}
    ```
    `rejections.json` is **EXPLICITLY EXCLUDED** from the universe — `RejectionRecord` carries no `thesis_evidence` field (verified in `src/irc/opportunity/rejection_log.py:35-47`), so no citation_ids live there. No `memo.md` marker references a citation_id absent from this union. This is the cross-stage publishable-set traversal guarantee.

20. **`memo.md` picks-table citations = opportunity citations for that row (SAME-3 round-trip).** For each `cn_equity_fund` pick in the seeded run, the set of citation_ids in the picks-table `证据` cell equals the set of citation_ids in `opportunity_report.json` for that row's selected-top-3 (per `select_citations(cap=3)`). The SAME-3 invariant locked unit-style in `tests/memo/test_same_3_invariant.py` is re-asserted post-disk-roundtrip.

### Multi-owner constituent (E16 publishable-set side)

21. **Same constituent in two funds keeps separate provenance on disk.** Seed two `cn_equity_fund` rows whose top-N constituents both include `贵州茅台 (600519)`. After `run_opportunity`, the `opportunity_report.json` row for fund A's `thesis_evidence` entries with `constituent_key="600519"` have `owner_instrument_id == "A"`; fund B's entries have `owner_instrument_id == "B"`. No leakage between funds.

### Pipeline-level two-run byte equality (NEW — grill-added invariant family)

Item 007 locked **unit-level** two-run byte equality at `tests/memo/test_determinism.py::test_evidence_pool_byte_equal_across_runs` and `::test_compose_discipline_markdown_byte_equal_across_runs` — synthetic inputs through pure functions. Item 008 adds the **pipeline-level** complement: byte equality of the on-disk artifacts produced by two consecutive `run_opportunity` + `run_memo` invocations against the same seed.

22. **Two-run byte equality of `opportunity_report.json` + `thesis_cards.yaml` + `discipline_report.md` + `rejections.json` after `run_opportunity`.** Seed the publishable-set helper. Invoke `run_opportunity(repo_root=str(tmp_path))` against `tmp_path_a`. Re-seed identically under `tmp_path_b` and invoke again. Assert `sha256(tmp_path_a/outputs/<date>/{opportunity_report.json,thesis_cards.yaml,discipline_report.md,rejections.json}) == sha256(tmp_path_b/...)` for all four artifacts. Catches any non-deterministic ordering (frozenset iteration, dict hash order, `glob` ordering, timestamp injection) that the unit tests cannot see because they don't exercise the full I/O stack.

23. **Two-run byte equality of `memo.md` after `run_opportunity → run_memo`.** Same shape as AC22, but the second-stage `run_memo` produces `memo.md` after both routes are patched to return deterministic canned text. Assert `sha256(memo_a) == sha256(memo_b)`. The patched synth body is constructed identically across both runs from the just-written `opportunity_report.json` (so the synth output is itself a function of the publishable-set citation universe — any nondeterminism in the citation-id derivation surfaces here).

## 4. File-touch map

### New files

- **`tests/integration/test_publishable_set_lockdown.py`** (~600–800 LOC; budget extended for ACs 22–23) — the flagship integration test file. Contains:
  - Module-level `_seed_publishable_set_repo(tmp_path, *, include_qdii=True, asset_classes=...)` helper (modeled on `test_opportunity_cmd_acceptance.py::_seed_repo_with_active_funds` + `test_opportunity_cmd_fund_level_integration.py::_universal_side`).
  - Module-level `_patch_memo_routes(synth_text: str)` context manager helper for ACs 19/20/22/23 (wraps the `patch("irc.memo.synthesizer.call_chat", ...) + patch("irc.memo.auditor.call_chat", ...)` pair from the locked precedent in `test_memo_cmd_aliases.py:98–99`).
  - Module-level `_collect_publishable_citation_universe(out_dir) -> set[str]` helper that reads `opportunity_report.json` + `gold_regime.json` and returns the union (per AC19's resolved Q5).
  - Per-test scenarios for ACs 1–23. Grouped by invariant family with descriptive test names: `test_publishable_dual_leg_coverage`, `test_publishable_owner_instrument_provenance`, `test_publishable_scope_is_instrument_or_constituent`, `test_publishable_thesis_state_literal_only`, `test_publishable_evidence_gaps_empty_after_disk_roundtrip`, `test_qdii_never_in_thesis_cards`, `test_qdii_never_in_opportunity_report_rows`, `test_qdii_appears_in_rejections_with_qdii_reason`, `test_qdii_appears_in_discipline_failure_section`, `test_h3_partition_across_four_output_surfaces`, `test_policy_b_precedence_qdii_over_policy_b_code`, `test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity`, `test_chicang_appendix_line_shape_per_publishable_row`, `test_chicang_appendix_omits_qdii`, `test_snapshot_cache_within_window_zero_akshare_calls`, `test_snapshot_cache_expired_probe_same_quarter_reuses`, `test_snapshot_cache_probe_failure_fail_closed_refetch`, `test_empty_holdings_propagate_to_rejections_holdings_fetch_failed`, `test_memo_cites_only_publishable_citation_ids`, `test_memo_picks_table_citation_set_matches_opportunity_row`, `test_multi_owner_constituent_keeps_separate_owner_instrument_id`, `test_two_run_byte_equality_opportunity_artifacts`, `test_two_run_byte_equality_memo_after_run_memo`.

### Modified files

- **`tests/integration/__init__.py`** — no change expected (module already exists).
- **`CONTEXT.md`** — append one paragraph to the "Test infrastructure" section naming `test_publishable_set_lockdown.py` as the locked baseline. Item 009 will reference this baseline when introducing block-mode. (Added during grill phase.)
- **`docs/2026-05-22-thesis-cards-evidence-gap/PROGRESS.md`** — flip item 008's phase markers as the autodev workflow progresses (handled by orchestrator, not in this PR's diff).

### Files explicitly NOT touched

- **`src/irc/**`** — item 008 is test-only by intent. Zero production code changes in the test-authoring commit. **Drift policy (per resolved Q6, item 003 + 006 PR precedent):** if a test exposes a real bug, fix it inline as a *separate commit* on the same sub-branch; capture each production fix in `008-drift.md`. Inline-fix is the policy; do NOT spawn a follow-up issue. The sub-branch is already cut, the PR review surface absorbs the fix-and-test pair atomically, and item 009 depends on a known-clean baseline.
- **`tests/memo/**`, `tests/opportunity/**`, `tests/fundamentals/**`** — item 008 does not amend existing unit tests. The audit table in §2 documents what's already covered; items 006/007's existing tests stay as-is.
- **`tests/commands/test_opportunity_cmd_h3_invariant.py`** — already covers the `_write_opportunity_outputs` partition at the row-construction level. Item 008's tests use `run_opportunity` end-to-end, which is a distinct surface.

### Fixtures

- **No new committed fixtures.** Test seeding uses the `_ak_call` mock dispatcher pattern (alternatives B + C considered in §5; option C — per-test seeding via shared helper — wins). Pre-existing fixture JSONs under `tests/fixtures/akshare/` (item 004) MAY be loaded by the helper for realistic AkShare response shapes but no new files are committed by this item. The seed-via-`_ak_call`-patch is the established precedent locked by `tests/commands/test_opportunity_cmd_fund_level_integration.py::_universal_side`.

## 5. Decisions made (alternatives considered)

### D1: Fixture-bake vs tmp-path mock (load-bearing)

- **Option A (rejected):** Commit baked `opportunity_report.json` / `thesis_cards.yaml` / `discipline_report.md` / `rejections.json` snapshots under `tests/fixtures/publishable_set/`. Tests deserialize the fixtures and assert invariants.
  - Pro: dead-simple test code; no mocking; resilient to refactors of `_build_rows` internals.
  - Con: fixtures drift as schemas evolve (every item 002-style schema addition would break them); no test of the production code path itself — only of the fixtures' own well-formedness. The invariants would be locked against the fixtures, not against `run_opportunity`'s output.
- **Option B (rejected):** Module-scoped pytest fixture that runs `run_opportunity` once and exposes the deserialized artifacts to all tests in the file.
  - Pro: ~10x faster (one `run_opportunity` invocation total).
  - Con: tight coupling — one assertion failure cascades; tests cannot independently vary the seed (e.g., the cache-freshness scenarios need different `cache_probed_at` pre-state).
- **Option C (CHOSEN):** Per-test seeding via shared `_seed_publishable_set_repo(tmp_path, **scenario_kwargs)` helper. Each test invokes `run_opportunity` against its own `tmp_path`.
  - Pro: matches the established pattern (`test_opportunity_cmd_acceptance.py`, `test_opportunity_cmd_h3_invariant.py`, `test_opportunity_cmd_fund_level_integration.py`); test isolation; per-scenario seed flexibility; mocks force exercising the real production paths in `_build_rows` / `_write_opportunity_outputs`.
  - Con: ~3s × 23 tests = ~70s total runtime; acceptable given the determinism gain.

### D2: One file vs N narrow files

- **Option A (CHOSEN):** One file `tests/integration/test_publishable_set_lockdown.py` with N grouped scenario tests.
  - Rationale: items 006 and 007 PRs both contained ≤200-LOC integration test files; reviewers parse one well-named file faster than a split-across-multiple-files layout. The file name announces intent ("lockdown") and signals to item 009 where to find the baseline.

### D3: Use `run_opportunity` vs `_build_rows` + `_write_opportunity_outputs` directly

- **Option A (CHOSEN, primary):** Call `run_opportunity(repo_root=str(tmp_path))` for ACs 1–14, 18–23. This exercises the full command-layer wiring (config loading, scoring read, halt-state, output writes).
- **Option B (used selectively):** Call `_write_opportunity_outputs(...)` directly for ACs that need pre-built `OpportunityRow` instances with hand-controlled `evidence_gaps` shapes (similar to existing `test_opportunity_cmd_h3_invariant.py` style). Used for ACs 11, 12 where the precedence / fatal-raise behavior is easier to seed at the partitioner level.
- **Option C (rejected):** Call only `_build_rows`. Skips the on-disk serialization the spec is supposed to lock down.

### D4: Test scope — include `run_decision`?

- **Decision:** OUT of scope. `run_decision` reads from already-published outputs and is downstream of the publishable-set surface. Item 008 stops at `run_memo`'s SAME-3 cross-stage check + the two-run byte-equality across opportunity + memo (ACs 22–23).

### D5: Real AkShare vs full mocking

- **Decision:** Full mocking via `_ak_call` patch. The repo's "cached evidence" model (CONTEXT.md) means `run_opportunity` reads from `data/fundamentals/<quarter>/...` under `tmp_path`. The seed helper either pre-writes the cache OR patches `_ak_call` to dispatch synthetic frames per `(fn_name, symbol)` like `test_opportunity_cmd_fund_level_integration.py::_universal_side`. Live AkShare exercise stays in item 004's `pytest -m live_akshare` suite (Slice E13) and the per-item `<id>-verify.md` smoke.

### D6 (NEW — grill-added): Pipeline-level vs unit-level byte equality

- **Option A (CHOSEN):** Add ACs 22–23 to lock byte equality at the **artifact level** after two consecutive `run_opportunity` + `run_memo` invocations against identical seeds in distinct `tmp_path`s.
- **Option B (rejected):** Rely on item 007's unit-level byte-equality tests (`tests/memo/test_determinism.py`).
  - Why rejected: unit-level tests exercise pure functions with synthetic inputs and cannot catch determinism bugs in the full I/O stack — frozenset iteration order in alias maps, `os.walk` / `glob` ordering, dict hash order in JSON serialization, accidental `datetime.now()` injection. Pipeline-level byte equality is the only assertion that closes the determinism loop end-to-end.
- **Option C (rejected):** Single-`run_opportunity` byte-stable hash comparison against a committed expected-hash file.
  - Why rejected: brittle — every legitimate schema change requires updating the committed hash, creating churn and merge conflicts. Two-run-in-the-same-test self-equality is the right shape — it asserts determinism without anchoring to a specific value.

## 6. Resolved open questions (post-grill)

All seven open questions from the spec's original "Open questions for grill phase" were auto-resolved against existing project precedent. Verbatim resolutions:

### Q1 — `run_memo` offline mocking pattern

**RESOLVED.** The pattern is locked in `tests/commands/test_memo_cmd_aliases.py:98–99`:
```python
patch("irc.memo.synthesizer.call_chat", return_value=_resp("..."))
patch("irc.memo.auditor.call_chat", return_value=_resp("..."))
```
where `_resp(text)` returns `ChatResponse(text=text, prompt_tokens=10, completion_tokens=20, latency_ms=50, raw={})`. Item 008's `_patch_memo_routes(synth_text)` helper wraps this pair. **No lower-level `run_memo_pipeline` invocation needed** — `run_memo(str(tmp_path))` is sufficient with the routes patched. Confirmed `synth_route` + `audit_route` are resolved inside `run_memo` at `src/irc/commands/memo_cmd.py:530–531` and passed to `run_memo_pipeline(inputs, raw_ref_pool, synth_route, audit_route)` at line 532 — patching the underlying `call_chat` short-circuits both routes deterministically.

### Q2 — Env-var gates for the seed helper

**RESOLVED.** Four env vars must be controlled by the seed helper (set via `monkeypatch.setenv`):
- `IRC_OPPORTUNITY_AUTOBUILD=1` (default `"1"` per `src/irc/commands/opportunity_cmd.py:194`; explicit for clarity)
- `IRC_CACHE_FRESHNESS_DAYS=7` (default per `src/irc/commands/opportunity_cmd.py:71,199`; ACs 16/17 override)
- `IRC_FETCH_BUDGET=2000` (default per `src/irc/commands/opportunity_cmd.py:70,204`)
- `IRC_ALLOW_STALE=1` (bypass STALE_INGEST blocking from `src/irc/commands/opportunity_cmd.py:1191`)

Documented in §3 "Test-isolation harness". No new env vars are introduced by item 008.

### Q3 — QDII variant coverage scope

**RESOLVED.** Seed **one instrument per QDII variant** (`qdii_us`, `qdii_hk`, `qdii_global` = 3 rows). Locks the per-variant exclusion path in `_build_qdii_sentinel_snapshot` (CONTEXT.md "QDII V1 exclusion"). The single-QDII-total alternative would not catch variant-specific routing bugs.

### Q4 — Snapshot-cache freshness env var name

**RESOLVED.** `IRC_CACHE_FRESHNESS_DAYS` **EXISTS** in production code at `src/irc/commands/opportunity_cmd.py:71` (`IRC_CACHE_FRESHNESS_DAYS_DEFAULT = 7`) and `src/irc/commands/opportunity_cmd.py:199` (`_freshness_days()` reads `os.environ.get("IRC_CACHE_FRESHNESS_DAYS", ...)`). The term is already documented in `CONTEXT.md` "Fail-closed freshness probe" (lines 26, 71 inferred). **No new env var, no new CONTEXT.md term, no ADR amendment needed.** AC15/16/17 reference the existing constant verbatim.

### Q5 — Citation-id universe for AC19

**RESOLVED.** The universe for AC19 is:
```
universe = opportunity_report.json["rows"][*]["thesis_evidence"][*]["citation_id"]
         ∪ gold_regime.json.get("evidence", [])[*]["citation_id"]
```
**`rejections.json` is EXPLICITLY EXCLUDED** from the universe. Verified by reading `src/irc/opportunity/rejection_log.py:35–47` (`RejectionRecord` dataclass): the fields are `instrument_id, name_cn, asset_class, rejection_reason, decision_rule, rejection_at_stage, constituent_coverage, fund_level_failure_reasons, fetch_types_attempted, evidence_gaps` — **no `thesis_evidence`, no `citation_id`**. Gapped rows have not earned conclusions and carry no citations; the universe shrinks to publishable outputs only. Macro/policy evidence on `gold_regime.json` is included because `memo.md` may cite the gold-regime evidence trail directly (e.g. for the gold pick rationale).

### Q6 — Production-fix policy in a test-only PR

**RESOLVED.** **Inline-fix policy.** Item 003's PR closed Q4-prereq production drift in the same PR; item 006's PR closed `_classify_fund_level_scores` over-count in the same PR. Item 008 follows the precedent: if an AC fails because production drifted from spec, fix in a *separate commit* on the same sub-branch and capture in `008-drift.md`. Do NOT spawn a follow-up issue. The PR review surface absorbs the fix-and-test pair atomically. Locked in §4 "Files explicitly NOT touched" with the explicit drift exception.

### Q7 — Decision-rule encoding for AC11

**RESOLVED.** The precedence is **NOT** exposed as a public ordered constant. The implementation surface is the dict-iteration order of `_GAP_TO_REASON` in `src/irc/opportunity/rejection_log.py:61–88` (private module constant; `qdii_information_unavailable` is the first key, so it wins by Python ≥3.7 dict-insertion-order semantics). AC11 **MUST NOT** import `_GAP_TO_REASON` directly (private; brittle; couples item 008 to an implementation detail). Instead, AC11 hard-codes the expected `rejection_reason == "qdii_information_unavailable"` string with the comment `# precedence per src/irc/opportunity/rejection_log.py::_GAP_TO_REASON dict-iteration order + ADR 0003`. The assertion is on the observable behavior, not the internal data structure. Locked in AC11 inline.

## 7. Non-goals

- **No production code changes in the test-authoring commit.** Item 008 is test-only by intent; production fixes flagged during impl land as their own commits on the sub-branch (per resolved Q6).
- **No changes to memo synthesis (`synth_route`) or audit (`audit_route`) prompts.** AC19/AC20/AC22/AC23 mock these routes at the `call_chat` boundary per the locked precedent.
- **No live AkShare calls.** Item 004 owns live verification.
- **No `run_decision` integration.** Out of scope per D4.
- **No E6 (`find_missing_citations` matrix) or E7 (audit-blocking path matrix) tests.** Both are on item 009's authoring surface; tests land alongside the function definitions in item 009.
- **No new env vars.** All four env vars used by the seed helper exist in production code (per resolved Q2/Q4).
- **No new ADRs.** All grill resolutions land in this spec + existing CONTEXT.md terms. ADR 0001–0004 stand unmodified.

## 8. Done means

1. `tests/integration/test_publishable_set_lockdown.py` exists with all ACs 1–23 implemented.
2. `pytest tests/integration/test_publishable_set_lockdown.py -x` passes locally on the sub-branch.
3. `pytest -x` (full suite) passes on the sub-branch — item 008 must not regress any existing test.
4. `ruff check src tests` clean.
5. `CONTEXT.md` updated with a one-paragraph reference to the locked baseline file under "Test infrastructure".
6. PR opens into `autodev/thesis-cards-evidence-gap`, `/ship` workflow runs verify + inline review + code-review, merges via squash.
7. **Gating contract:** item 009 cannot enter implementation until item 008 has merged and `PROGRESS.md` shows `008-merge ✅`.
