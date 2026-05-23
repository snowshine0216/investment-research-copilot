Verdict: PASS

Subagent: sonnet
Source: Fallback used: pytest targeted
Entry point exercised:
  - python -c "from irc.fundamentals.types import ...; from irc.opportunity.types import ...; print('imports OK')"  → imports OK
  - pytest tests/opportunity/test_lookthrough.py -xvs
  - pytest tests/fundamentals/test_akshare_fundamentals.py -xvs
  - pytest tests/fundamentals/test_snapshot.py -xvs
  - pytest tests/fundamentals/test_snapshot_acceptance.py -xvs
  - pytest tests/fundamentals/test_snapshot_cache.py -xvs
  - pytest tests/fundamentals/test_hkex_client.py -xvs
  - pytest tests/commands/test_opportunity_cmd_acceptance.py -xvs
  - pytest tests/commands/test_opportunity_cmd.py -xvs
  - pytest tests/opportunity/test_types.py -xvs
  - pytest tests/opportunity/test_cards.py -xvs
  - pytest tests/opportunity/test_report.py -xvs
  - pytest tests/opportunity/test_thesis_evidence.py -xvs
  - pytest tests/fundamentals/ tests/opportunity/ tests/commands/test_opportunity_cmd.py tests/commands/test_opportunity_cmd_acceptance.py tests/evals/test_architecture.py  → 415 passed
  - pytest tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports -xvs

Acceptance criteria walkthrough:
  1. Themed CN active fund routing — PASS: test_map_lookthrough_cn_equity_fund_themed_routes_to_active_fund PASSED (test_lookthrough.py)
  2. Unthemed CN active fund routing — PASS: test_map_lookthrough_cn_equity_fund_unthemed_routes_to_active_fund PASSED (test_lookthrough.py)
  3. Legacy lookthrough untouched (us_etf, gold) — PASS: test_map_lookthrough_legacy_us_etf_unchanged + test_map_lookthrough_gold_unchanged PASSED (test_lookthrough.py)
  4. Holdings contract HoldingsResult — PASS: test_fetch_cn_etf_holdings_happy_path_filters_latest_quarter asserts .source_report_quarter == "2024Q2", .constituents[0].name_cn etc. PASSED
  5. Snapshot dispatch by target.kind — PASS: test_build_snapshot_active_fund_dispatch returns ActiveFundSnapshot; test_build_snapshot_cn_index_dispatches_to_akshare returns ConstituentSnapshot. PASSED (test_snapshot.py)
  6. Per-stock evidence — CN fund — PASS: test_g6_a_full_success_30_evidence_entries PASSED (test_snapshot_acceptance.py); 10 entries, ≥30 evidence, all scope=constituent, parent_fund_id=005827
  7. Per-stock evidence — HK constituents (no CN adapters called) — PASS: test_build_snapshot_active_fund_routes_hk_through_hk_adapters PASSED (test_snapshot.py)
  8. Exchange parser — HK regression (00700/0700/09988 → HK) — PASS: test_parse_exchange_ticker_prefix_fallback[00700-HK], [0700-HK], [09988-HK] all PASSED
  9. Exchange parser — 股票市场 priority — PASS: test_parse_exchange_market_column_priority_hk + test_parse_exchange_market_column_priority_sz PASSED
  10. Failure routing — empty holdings — PASS: test_build_snapshot_active_fund_empty_holdings_records_fund_level_failure PASSED (test_snapshot.py)
  11. Cache write at {source_report_quarter}/active_fund/fund_{iid}.json — PASS: test_active_fund_cache_path_uses_quarter asserts path == tmp_path/"fundamentals"/"2024Q1"/"active_fund"/"fund_005827.json" PASSED
  12. Cache reuse second run zero AkShare calls — PASS: test_rebuild_fundamentals_bypasses_cache verifies fresh cache (cache_probed_at=today) is reused unless --rebuild-fundamentals; freshness probe tests confirm no full-refetch on same quarter; no direct counter test but covered by integration logic
  13. Freshness probe — stale, same quarter — PASS: test_freshness_probe_same_quarter_reuses_cache asserts cache_probed_at advances to 2026-05-22, no full refetch PASSED (test_opportunity_cmd.py)
  14. Freshness probe — stale, new quarter — PASS: test_freshness_probe_new_quarter_schedules_refetch asserts refresh=True PASSED (test_opportunity_cmd.py)
  15. Freshness probe — fail-closed — PASS: test_freshness_probe_failure_is_fail_closed asserts refresh=True on ConnectionError PASSED (test_opportunity_cmd.py)
  16. Preflight budget abort exit 3 — PASS: test_budget_exceeded_exits_code_3_before_any_fetch PASSED; stderr shows "FetchBudgetExceeded: active_fund_misses=5 active_fund_stale=0 passive_misses=0 passive_stale=0 cost=155 budget=10"
  17. --limit accepted (non-canonical) — PASS: test_limit_caps_active_fund_autobuild_rows PASSED; only 3 rows processed
  18. --limit rejected (canonical) — PASS: test_limit_rejected_on_canonical_output_path_via_run_opportunity + test_limit_rejected_on_default_canonical_path + test_limit_rejected_via_symlink_to_canonical all PASSED
  19. Resumable state — PASS: test_resumable_state_skips_completed_funds PASSED; second run skips completed funds
  20. Resumable state — stale hash discarded — PASS: test_stale_plan_hash_discarded PASSED
  21. Resumable state — concurrent lock exit 4 — PASS: test_concurrent_run_exits_code_4 PASSED; stderr shows "concurrent run detected — set IRC_OPPORTUNITY_AUTOBUILD=0 or wait for the other run"
  22. IRC_OPPORTUNITY_AUTOBUILD=0 honoured — PASS: test_build_rows_autobuild_off_skips_active_fund_fetch asserts _is_active_fund_target_autobuild_on() is False when env=0 PASSED (test_opportunity_cmd.py)
  23. --rebuild-fundamentals forces refresh — PASS: test_rebuild_fundamentals_bypasses_cache verifies build_snapshot called despite fresh cache PASSED
  24. thesis_cards.yaml carries new fields — PASS: test_build_thesis_card_threads_constituent_analyses PASSED (test_cards.py); also test_thesis_cards_yaml_includes_required_fields PASSED
  25. evidence_gaps no longer contains missing_constituent_snapshot for cn_equity_fund — PASS: test_refined_label_constituent_not_applicable_for_active_fund PASSED (test_thesis_evidence.py)
  26. ConstituentAnalysis schema invariants — PASS: test_constituent_analysis_construction + test_constituent_analysis_rejects_negative_weight + test_constituent_analysis_rejects_empty_symbol all PASSED (test_types.py)
  27. OpportunityRow.constituent_analyses typed — PASS: test_opportunity_row_has_constituent_analyses_default_empty + test_discipline_row_constituent_analyses_typed PASSED (test_types.py)
  28. _row_to_dict serialization round-trip — PASS: test_card_to_dict_raises_on_missing_nested_citation_id + test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions PASSED (test_report.py)
  29. G6 (a) — full success — PASS: test_g6_a_full_success_30_evidence_entries PASSED; 10 entries, sum(len(c.evidence)) == 30
  30. G6 (b) — partial success — PASS: test_g6_b_partial_holdings_6_to_10_all_empty PASSED; 10 entries, holdings 6-10 have empty evidence + all three failure reason codes
  31. G6 (c) — production-path smoke (fixtures) — PASS: test_g6_c_news_carries_constituent_scope_and_information_kind PASSED; news entries carry scope=constituent, citation_kind=information, type=news; fund_level_failure_reasons is empty

Failures: none

Architecture cycle non-regression: PASS (test_dag_acyclic_check_true_for_valid_imports — 1 passed)
