Verdict: PASS-WITH-NITS

Subagent: sonnet (via /code-review)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/59
Skill: code-review

## Summary
- High-confidence bugs: 0
- Likely bugs (uncertain): 1
- Nits: 2
- Notes / observations: 3

## Findings

### High-confidence bugs
None.

### Likely bugs
- `src/irc/commands/opportunity_cmd.py:604` — `_classify_fund_level_scores` over-counts budget for `cn_etf` rows whose `tracked_index` maps to a QDII key — `FetchBudgetExceeded` raised for a workload that actually fits within budget.

  **Trace:** `_classify_fund_level_scores` filters on `score.asset_class in ("gold", "cn_bond_fund", "cn_etf")`. A `cn_etf` row with `tracked_index="nasdaq100"` passes this filter and gets counted as 4 calls. However `map_lookthrough` for that same row returns `LookthroughTarget(kind="qdii_us", ...)` (via `tracked in _QDII_US_KEYS`), and `_build_rows` dispatches it to the QDII sentinel path — **zero actual AkShare calls**. The `_classify` pass thus over-estimates by 4 per such row. Real-world instruments in this category: A-share QQQ ETF (513100), A-share S&P500 ETF (513500), etc. On a portfolio near the default 2000-call budget, 4+ such cn_etf rows tip `total_calls() > budget` even though actual cost is zero. Schema (`Instrument.tracked_index: str | None`) has no constraint preventing this combination.

  **Impact:** Spurious `FetchBudgetExceeded` (RuntimeError) that aborts the run for a valid workload.

### Nits
- `src/irc/opportunity/thesis_evidence.py:354-356` — QDII sentinel path returns `reason=""` (empty string) when `evidence=()` and `gaps` is non-empty. The expression `"" if gaps else "基金层级证据未能加载。"` produces empty string for the QDII case, which in `states.py:462` yields `" | ".join([..., "", ...])` — results in `"...heat |  | product..."` (double-separator) in `OpportunityRow.opportunity_reason`. Not a crash, but the intent appears to be a non-empty reason for the QDII gap (the `else` branch is the one that fires when gaps is empty/truthy semantics are swapped). Fix: swap the condition to `"" if not gaps else "QDII: 境外数据不可用"` or similar.

- `src/irc/commands/opportunity_cmd.py:279` — `_load_latest_nav_cached` uses `base.glob("*/nav/fund_{fund_id}.json")` which matches any subdirectory of `fundamentals/`, not just quarter-shaped dirs. A non-quarter directory (e.g. a manually placed `debug/nav/fund_X.json`) would be picked up and attempted. This is resilient — `load_nav_cache` returns `None` on bad JSON and the loop continues — but lexicographic sort places `d* < 2026Q*` so a `debug/` dir would be tried last. Symlinks under `fundamentals/` are also followed by `glob`. Impact: harmless extra I/O at most; no functional regression.

### Notes
- **FetchPlan arithmetic correct:** `total_calls()` formula — `(fl_misses + fl_stale) * 4` — is arithmetically correct and matches the 4-endpoint spec (1 NAV + 3 announcement endpoints). Tests confirm 3*4=12 and 62+20=82. No off-by-one.
- **Cache staleness boundary consistent:** `_is_nav_stale` uses `days > threshold_days` (not `>=`), matching the pre-existing `_is_stale` for active funds. No new boundary discrepancy introduced.
- **Test isolation clean:** All new tests use `patch.dict("os.environ", ...)` as context managers (auto-restore) and `tmp_path` fixtures (isolated dirs). No global `_TARGET_REGISTRY` mutation or module-level state modification found.

## What the inline review missed
- `_classify_fund_level_scores` counts `cn_etf` by asset class but does not exclude rows whose `tracked_index` routes to a QDII kind (zero actual cost); over-estimated budget can trigger spurious `FetchBudgetExceeded` — distinct from and independent of the `_FUND_LEVEL_KINDS` frozenset-drift latent finding already flagged.
- `derive_thesis_from_evidence` QDII sentinel path produces `reason=""` (empty string) via inverted conditional; `states.py` join produces double-separator artifact in `opportunity_reason`.

## What the inline review already caught
(do not re-flag)
- `_FUND_LEVEL_KINDS` frozenset drift between `snapshot.py` and `opportunity_cmd.py`
- `assert isinstance` for type narrowing (silent under `-O`)
- `_ann_from_dict` missing topic validation
- `_ISO_DATE_RE` accepts impossible calendar dates
- broad `except Exception` in `fetch_fund_nav_report`
- `snapshot_cache` dict namespace mixing (active-fund `fund_<id>` vs bare `<id>` for fund-level)
- `inf` NAV cache-write failure path
