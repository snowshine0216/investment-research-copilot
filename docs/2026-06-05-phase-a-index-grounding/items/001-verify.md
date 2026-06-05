Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct uv run pytest / uv run python -c / uv run irc --help invocations
Entry point exercised:
  - uv run irc --help
  - uv run irc run --help
  - uv run pytest tests/opportunity/test_inputs_loader.py -k "broad_display_name or sp_dividend or speculative_slug" -v
  - uv run pytest tests/data/test_index_valuation_ingestor.py -v
  - uv run pytest tests/fundamentals/test_akshare_index_valuation.py tests/opportunity/test_lookthrough.py tests/test_config_loader.py -q
  - uv run pytest tests/fundamentals/test_index_valuation_live.py -q
  - uv run pytest tests/ -k "161721 or 003318 or seed_override or tracked_index_none" -v
  - uv run python -c "..." (direct function smoke)

Observed behavior:

  - Gate #1 (CLI boots / import graph intact): `uv run irc --help` and `uv run irc run --help` → exit 0, no ImportError. All changed modules import cleanly.

  - Gate #2 (TDD tests green): All relevant test suites pass.

  - D1 (rolling PE-TTM only, never static): `tests/fundamentals/test_akshare_index_valuation.py` — 32 tests pass. Verified that `_LEGULEGU_PE_TTM_COL = "滚动市盈率"` is the sole PE column; static fallback removed. Rolling extraction picks `滚动市盈率`, returns `None` when absent.

  - D2 (production allowlist = {csi300, csi500, csi1000, sse50} only): Direct smoke confirms `_LEGULEGU_INDEX_SYMBOL.keys() == {'csi300', 'csi500', 'csi1000', 'sse50'}`. `fetch_cn_index_valuation('chinext')` → `None` (speculative slug unreachable via production path). 32 tests in `test_akshare_index_valuation.py` pass.

  - D3 (`标普红利低波50` stays on NAV, unmapped): Direct smoke confirms `'标普红利低波50' not in _INDEX_NAME_TO_SLUG`. `test_sp_dividend_low_vol_tracked_index_stays_none` PASSED — tracked_index="标普红利低波50" resolves to None pe_pct.

  - D4 (`chinext` and `chinext50` are distinct exact slugs): Direct smoke confirms `_INDEX_NAME_TO_SLUG['创业板指'] == 'chinext'` and `_INDEX_NAME_TO_SLUG['创业板50'] == 'chinext50'` (distinct). `chinext50 in _BROAD_INDEX_KEYS` → True. `tests/opportunity/test_lookthrough.py` (32 tests) green.

  - D5 (`161721` seed override strips `沪深300` tag): `config/universe/cn_funds.yaml` seed entry for `161721` has no `tracked_index` field. `test_phase_a_seed_overrides_strip_broad_tracked_index` PASSED — both 161721 and 003318 resolve to `tracked_index=None`.

  - D6 (`003318` seed override strips `中证500` tag): Same test + same seed entry confirms `003318` without `tracked_index`. Seed wins by instrument_id.

  - D7 (honest coverage ~9): Verified indirectly via D5/D6 and D2 — only {csi300, csi500, csi1000, sse50} populate the ingestor, mis-tagged funds (161721, 003318) stripped, 标普红利低波50 unmapped. Coverage ~9 is structural. Measurement deferred to operator gate #3.

  - D8 (broad leg = per-key full replace; sector leg = append; empty fetch never wipes cache):
    - `test_replace_keys_deletes_prior_rows_on_nonempty_fetch` PASSED
    - `test_replace_keys_preserves_rows_on_none_fetch` PASSED
    - `test_replace_keys_skips_key_when_fetch_lacks_pe_ttm` PASSED (PE-less frame does not wipe good cache)
    - `test_default_append_mode_accumulates_across_calls` PASSED
    All 7 `test_index_valuation_ingestor.py` tests green.

  - End-to-end grounding path (D1/D2 integrated): `test_broad_display_name_tracked_index_grounds_pe_percentile` PASSED — seeded in-memory DuckDB with `tracked_index="沪深300"`, display name → `_INDEX_NAME_TO_SLUG` inversion → `csi300` → cached `index_valuation_history` read → non-None `valuation_percentile_fundamental`. `test_speculative_slug_with_empty_table_stays_none` PASSED — `star50` with empty table → None.

  - Default suite stays offline: `tests/fundamentals/test_index_valuation_live.py` → 5 skipped, 0 passed. No network fired.

Deferred (operator/live gates, not failures):
  - Gate #3 (coverage ≥9 measured): requires `irc run --from ingest` + `irc opportunity` with warm market cache — network/live-data gate.
  - Gate #4 (live confirmation): requires `IRC_RUN_LIVE_AKSHARE=1` and real AkShare network — live gate.
  - Gate #5 (before/after artifact): requires two `irc opportunity` runs with real ingested data — operator gate.

Failures: none
