# 001 — Code review verdict

- **PR:** #54
- **Date:** 2026-05-21
- **Verdict:** PASS
- **Reviewer model:** sonnet
- **Files reviewed:** 28 files, 3986 lines changed (3474 in generated YAML artifact, ~512 in source + tests)

## Summary

The PR delivers two orthogonal but well-integrated features: (1) a quality-weighted fund-ranking signal that replaces the fund_code-ascending tiebreaker in `_apply_caps` with a 1Y-return sort, and (2) a new `qdii_global` asset class for global-mandate QDII active funds. Both features are sound: branch ordering in `_infer_asset_class` correctly keeps US_MARKERS and HK_MARKERS ahead of the new qdii_global branch; `_candidate_rank_with_returns({})` is provably order-equivalent to the legacy `_candidate_rank`; `_parse_percent` handles all realistic akshare dtypes (float, np.float64, int, string, None, em-dash, "--", "N/A"); the `lru_cache` test pattern correctly clears both `_fetch_full_fund_rank_table` and `fetch_open_fund_ranks`; and the 11 downstream consumer sites all handle `qdii_global` with semantically correct treatment (foreign equity for allocation/diagnostics/states/gates, non-indexable for thesis_evidence, VIX-triggerable for triggers). All 124 PR-specific tests pass; 6 pre-existing failures are unchanged vs. main.

## Blockers (must fix before merge)

(empty)

## Latent bugs (could fire in production)

(empty)

## Nits (don't block merge)

- `src/irc/data/akshare_client.py:248` — `isinstance(value, (int,))` has a redundant trailing comma inside the tuple; `isinstance(value, int)` is idiomatic. No behavior difference.
- `src/irc/opportunity/lookthrough.py:110-112` — `qdii_global` does not apply `_normalize_qdii_key` alias normalisation the way `us_etf`/`hk_etf` do. This is intentional today (no aliases defined for global equity targets) but there is no comment noting the deliberate omission, which could surprise a future editor.
- `src/irc/data/akshare_client.py:234-241` — the commented-out per-type fallback block for `"全部"` unavailability is dead code with a TODO-style note; could become confusing if the akshare version ever changes. Acceptable for now as it documents a known workaround path.

## Style / functional-purity check

- **Pure functions:** pass — `_candidate_rank_with_returns` is a pure higher-order function (closure captures an immutable `Mapping`); no side effects in any classification or ranking function.
- **Immutability:** pass — `UniverseBuildOptions` remains a frozen dataclass; `_apply_caps` returns a new `tuple`; no in-place mutation anywhere in the diff.
- **Function size:** pass — all new functions are under 20 lines; `_candidate_rank_with_returns` inner closure is 8 lines; `_parse_percent` is 13 lines.
- **TDD evidence in commit history:** pass — commits `ffe24dd`, `89b40bb`, `c7c91e0`, `76148f2` each have corresponding test commits; the downstream fix commit `9089045` includes tests for role_bucket and lookthrough.
- **Comments only where non-obvious:** pass — the `_parse_percent` docstring explains the akshare dtype deviation from the test's string inputs; the `lru_cache` extraction comment in `_raw_fund_rank_call` explains why it is split from `_fetch_full_fund_rank_table`; no gratuitous comments elsewhere.

## Notes

**Branch ordering in `_infer_asset_class` verified:** US_MARKERS check fires before the new qdii_global branch, so a Nasdaq-100 QDII (`纳斯达克` in name) still classifies as `us_etf`. Simulated in Python: confirmed correct.

**`_parse_percent` dtype coverage:** np.float64 is a subclass of Python `float` in NumPy >= 1.20 (confirmed for this environment), so the `isinstance(value, float)` branch handles it correctly. The `str(np.float64("nan")) == "nan"` path also works via the string branch as a belt-and-suspenders fallback.

**NaN filter in `universe_cmd.py:48`:** `row.get("return_1y") == row.get("return_1y")` is `False` for NaN — correct and idiomatic for float NaN filtering without importing math.

**`qdii_global` as NON_INDEXABLE:** The placement in `thesis_evidence.NON_INDEXABLE_ASSET_CLASSES` means no snapshot lookup is attempted, and `_TARGET_REGISTRY` correctly does not need a "global equity" entry. The `test_target_registry_covers_every_lookthrough_display` test only checks `_BROAD_INDEX_DISPLAY`, `_QDII_US_DISPLAY`, `_QDII_HK_DISPLAY`, and `_SECTOR_THEME_DISPLAY` — which excludes the free-form `qdii_global` display key by design.

**Pre-existing test failures (6):** `test_fetch_macro_series_returns_dataframe`, `test_evals_runners_importable_from_installed_layout`, `test_imports` (missing `feedparser`/`scipy`/etc.), `test_eval_single_stage_data`, and 2 integration threshold tests — all present on `main` before this PR.
