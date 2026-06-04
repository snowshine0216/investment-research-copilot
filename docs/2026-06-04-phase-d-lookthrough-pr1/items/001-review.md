Verdict: PASS-WITH-NITS

Source: /ship steps 8 (pre-landing: pr-review-toolkit:code-reviewer + silent-failure-hunter) + 9 (adversarial review)
Subagents: sonnet ×3

All findings below were surfaced pre-push and **FIXED before the PR was opened** (commit 524ad62), per ship.md "review can demand fixes before push". Re-run after fixes: 872 passed, 3 skipped; only the 2 documented pre-existing baseline failures remain (see note). Zero remaining blockers or latent bugs.

## Findings (all fixed)

- **P0 — dormancy-lock regression (code-reviewer + adversarial, both independently)** — FIXED
  `src/irc/opportunity/inputs_loader.py:308` — the active-fund branch keyed only on `asset_class == "cn_equity_fund"`, missing the `tracked_index is None` guard. For enhanced-index `cn_equity_fund`s (沪深300/中证500/中证A500-enhanced — real in `config/universe/cn_funds.generated.yaml`), flag-OFF overwrote the index-derived `valuation_percentile_fundamental[_pb]` with `None`, breaking the spec §3.8 "prod byte-identical" guarantee. The lookthrough tests all used `tracked_index=None`, so they missed it.
  Fix: guard now `asset_class == "cn_equity_fund" and skeleton.tracked_index is None` (line 311). Two regression tests added (`test_enhanced_index_fund_flag_off_preserves_index_derived_percentile`, `test_enhanced_index_fund_flag_on_still_uses_index_path`) — confirmed FAIL before / PASS after.

- **P0 — silent fetch failure (silent-failure-hunter)** — FIXED
  `src/irc/fundamentals/akshare_stock_valuation.py` `_fetch_frame` — `except Exception: return None` had no log (Tushare path logged; AkShare was silent), so a network/API outage was indistinguishable from "no data" and invisible even to the command-level WARN. Violated spec §6.1 ("failed stocks logged at WARN with code + reason").
  Fix: added module logger + `_log.warning(...)` on exception before degrade-to-None.

- **P1 — non-DataFrame return silently normalized (silent-failure-hunter)** — FIXED
  Same fetcher: a non-DataFrame `_ak_call` return was silently coerced to an empty frame (broken response contract looked like "no data"). Fix: `_log.warning("... returned unexpected type ...")` in the else branch.

- **Note — discovery errors not surfaced consistently (code-reviewer/silent-failure-hunter)** — FIXED
  `src/irc/commands/fundamentals_cmd.py` ~126 — `_discover_ashare_codes` + staleness comprehension ran outside try/except (raw traceback vs the command's `ERROR:`-prefixed `return 1`). Fix: wrapped in `try/except` → `ERROR: ...` + `return 1`. Per-stock fetch isolation unchanged.

## Adversarial edge-case probes — all CLEAN (no action)
Empty holdings / all-None series / single date / all-negative PE / weights >100 or 0 / duplicate dates / covered code missing from series / empty-series pandas index / empty-universe diff report — all degrade to None or produce valid empty output without raising (verified by the adversarial reviewer). Harmonic sum never divides by zero (non-positive excluded; `ey <= 0` guarded). Ingestor batch is size-1 per stock (command-layer isolation), so a mid-batch rollback can't corrupt other stocks.

## Confirmed correct (no change)
- `/100` coverage-floor + per-date NAV-fraction floor (§3.2/§3.4).
- PE 120/180 gate vs PB `<30` floor asymmetry (§3.3).
- `(pe, pb)[idx-1]` metric indexing.
- `lookthrough_valuation.py` / `lookthrough_diff_report.py` purity (effects only in command + ingestor).

## Pre-existing baseline failures (NOT introduced by this PR)
`tests/commands/test_fund_eval_cmd.py::test_run_eval_funds_writes_md_and_json_with_core_dca` and `tests/commands/test_opportunity_cmd_fund_level.py::test_build_rows_qdii_row_carries_sentinel_gap` fail identically on the untouched base branch (acf026c). The QDII one is stale from the QDII-fetch-reform gap-code change. Both are among the project's documented 8 known baseline failures; neither touches the look-through path.
