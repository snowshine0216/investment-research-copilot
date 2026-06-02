Verdict: PASS-WITH-NITS

Source: manual diff review (/code-review unavailable — skill invoked but ran as inline review agent without posting a PR comment)
PR comment URL: none posted

Findings: 4
  - src/irc/narrative/holdings_fetch.py:80 — latent-bug — `_write_cache` uses non-atomic `path.write_text` instead of `atomic_write_text`. A process kill between file open and flush produces a zero-byte or truncated file; a truncated-valid JSON body (e.g. partial holdings array) would be returned by `_read_cache` silently, permanently caching stale/incomplete holdings for that fund until the file is manually removed. The final report outputs use `atomic_write_text` correctly; this is the sole holdout.
  - src/irc/narrative/screen.py:11-14 — nit — `_basket_hit` rebuilds `{s.symbol ...}` and `{s.name_cn ...}` frozensets on every call inside the `score_overlap` loop (up to 10 calls per fund × full universe). The sets are invariant to the basket and should be precomputed once in `score_overlap` before the holdings loop.
  - src/irc/narrative/screen.py:17-18 — nit — `_industry_hit` checks `holding.sw_industry in basket.industries_sw` where `industries_sw` is a `tuple[str, ...]`, giving O(n) linear scan per holding. A `frozenset` would give O(1) and eliminate the silent string-equality ordering dependency.
  - src/irc/narrative/schemas.py:809 / screen.py:34-37 — nit — `OverlapResult.basket_weight_pct` accumulates weight for both direct basket hits AND SW-industry-credit hits, but the field name implies only basket-matched weight. Downstream consumers (MD table header "篮子权重%", JSON key "basket_weight_pct") will mislead users who assume industry-credit weight is excluded.

## Verification of previously fixed P0s

All three P0s from the pre-landing /ship review are confirmed fixed in the current diff:
- Duplicate-symbol double-count: `score_overlap` tracks a `seen` set (screen.py:27-31); `_parse` sorts descending then dedupes by symbol (holdings_fetch.py:53-62).
- NaN/inf weight → invalid JSON: `_to_holding` sanitizes via `math.isnan`/`isinf` to 0.0 (holdings_fetch.py:38-39).
- Per-fund analyze crash: `_run_analyze` wraps each fund in try/except → `error_report(row, reason)` fallback; `None` reserved for absent prerequisites (narrative_cmd.py:96-110).

## Additional checks (all clear)

- Pure cores (screen.py, risk.py, schemas.py): no logging, no I/O, no side effects. PASS.
- Determinism: `rank_shortlist` sort key is `(-weight, -count, instrument_id)` — fully deterministic, no wall-clock/random. PASS.
- `derive_position_risk_level` severity clamping: `min(len(_LADDER) - 1, sum(...))` correctly caps at index 3 ("high"). PASS.
- File-size budget (<200 lines): all 8 new files within budget. PASS.
- Citation format: `report.py` routes through `select_citations` → emits `[ref:{16-hex}]`; acceptance test confirms. PASS.
- `基金概况` literal absent from all narrative/*.py files. PASS.
- `analyze_fund` reuse of `_build_input` / `build_opportunity_row` / `build_thesis_card` mirrors the `fund_eval_cmd` pattern exactly. PASS.
- Con lifecycle in `_run_analyze`: opened by `_open_analyze_context`, closed in `finally` block (narrative_cmd.py:111-115). PASS.
- 59 tests pass, 1 skipped (live AkShare gate). PASS.
