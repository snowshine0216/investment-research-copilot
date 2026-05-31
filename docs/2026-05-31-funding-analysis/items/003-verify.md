Verdict: PASS
Subagent: sonnet
Source: Fallback used: uv run python -c / uv run pytest
Entry point exercised: uv run pytest tests/fundamentals/test_provider.py tests/fundamentals/test_tushare_provider.py tests/fundamentals/test_provider_migration.py tests/fundamentals/test_tushare_provider_live.py && uv run pytest tests/fundamentals tests/opportunity -q && uv run python -c "..." (factory, protocol, guard, swallow-log, no-import checks)

Observed behavior:
  - AC1 (Protocol defined, all three satisfy isinstance) — PASS: `isinstance(AkShareProvider(), CnFundamentalsProvider)` → True; `TushareProvider` → True; `FallbackProvider` → True. All 20 test_provider.py tests passed.
  - AC2 (AkShareProvider byte-equal to direct call) — PASS: test_provider_migration.py::test_index_metrics_via_provider_matches_pre_migration PASSED; test_provider.py::test_akshare_provider_{filing,brokers,index}_equals_direct_call all PASSED.
  - AC3 (FallbackProvider routing: primary hit/miss/raises/both-miss; target_price flows) — PASS: `test_fallback_primary_hit_skips_secondary`, `test_fallback_primary_miss_uses_secondary`, `test_fallback_primary_raises_uses_secondary`, `test_fallback_both_miss_returns_none_no_raise`, `test_fallback_target_price_flows_when_primary_brokers_empty` all PASSED.
  - AC4 (Network mocked, _tushare_call edge, pure mapping) — PASS: 18 test_tushare_provider.py tests all passed including `test_module_does_not_import_tushare_at_load`, `test_filing_routes_through_tushare_call`, `test_tushare_filing_swallow_emits_warning_and_returns_none`.
  - AC5 (Live test skips offline, live_tushare marker registered) — PASS: `uv run pytest tests/fundamentals/test_tushare_provider_live.py` → 2 skipped (not failed). `pyproject.toml` line 53 has marker `live_tushare` registered.
  - AC6 (default_cn_provider: no token → AkShareProvider; with token → FallbackProvider) — PASS: `default_cn_provider()` with empty token → `AkShareProvider`; with `"fake-token-123"` → `FallbackProvider`. Observed output: "No-token type: AkShareProvider / With token type: FallbackProvider".
  - AC7 (migration byte-identical, call-sites injected) — PASS: test_provider_migration.py 3/3 PASSED. Full suite `tests/fundamentals tests/opportunity` → 771 passed, 15 skipped, 0 failed.
  - AC8 (README updated) — PASS: README line 44 has `TUSHARE_TOKEN` in env table; lines 77-110 have "Tushare fallback (optional)" subsection. `tests/fundamentals/README-live-tests.md` lines 108-113 have live_tushare pointer.
  - AC9 (No 基金概況, invariant test extended to new modules) — PASS: `test_static_profile_invariant.py` → 3/3 PASSED including `test_static_profile_indicator_not_in_provider_modules`.
  - AC10 (Tests pass offline, ruff clean on new files, fallback miss-gated) — PASS: 771 passed offline; ruff on 003 new files all passed. NOTE: `tushare_provider.py` is 234 lines vs 200-line ideal budget, but the split into `provider.py` (149 lines) + `tushare_provider.py` was explicitly anticipated in the spec constraints ("If tushare parsing pushes provider.py over budget, split tushare_provider.py"). Budget overage is minor (34 lines) and expected. Ruff violations in `src/irc/scoring/gold_scenarios.py`, `src/irc/scoring/gold_score.py`, and several test files are all pre-existing (not introduced by item 003).
  - Swallow-logging fix: Primary that raises → FallbackProvider logs "FallbackProvider swallowed exception in fetch_filing_digest('600519'): RuntimeError: primary exploded". Result is None. WARNING logged: True.
  - No-import at load: `import irc.fundamentals.tushare_provider` then `assert 'tushare' not in sys.modules` → PASS.
  - Fiscal_period guard: unrecognized mmdd `20240228` → `_map_fina_to_digest` returns None; `20241231` → `fiscal_period="2024FY"`.

Failures: none
