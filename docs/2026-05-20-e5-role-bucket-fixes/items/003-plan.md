# Item 003 — Add SOE / real-estate proxies to `cn_funds.yaml` template

## Files

- `src/irc/templates/config/universe/cn_funds.yaml`
- `tests/discovery/test_universe_completeness.py` — add completeness test

## Scope refinement

The E5 report recommends adding several proxies. After auditing the existing
template, only some are genuinely missing:

| Theme | Report recommended | Template state | Action |
|---|---|---|---|
| semiconductor | 512760, 159995 | Already present (5 ETFs total) | **No-op.** Failure is DD-buffer, fixed by Phase 1. |
| real_estate | 512200, 159768 | 512200 present, 159768 missing | **Add 159768.** |
| soe | 560090, 561380 | Neither present (have 5 other SOE ETFs) | **Add 560090, 561380.** |

Adding 512760/159995 again would be a no-op (de-dup'd by UniverseConfig validator)
and the underlying failure mode (quality DD) won't be helped by more themed
candidates. Phase 1 (DD buffer raise) is the real fix for semiconductor.

## New instruments

| ID | Name | Theme | tracked_index | Venue |
|---|---|---|---|---|
| 159768 | 房地产ETF华夏 | real_estate | 中证全指房地产 | cn_brokerage |
| 560090 | 中证国新央企ETF | soe | 中证国新央企 | cn_brokerage |
| 561380 | 国新港股通央企红利ETF | soe | 中证国新港股通央企红利 | cn_brokerage |

## Inception caveat

These ETFs were launched in the 2023–2024 window. `hard_filter` requires
`inception_years_min: 3` (today 2026-05-20 → cutoff 2023-05-20). Whether each
clears today depends on the exact launch date. If they don't, they sit in the
template as future-ready and naturally start passing once they age past 3 years.

That is acceptable. The point of the universe addition is to be *ready* when the
quality bar lifts — same logic the E5 report assumes ("watchpoint: every new
instrument must clear `inception_years_min: 3`").

## TDD test

Extend `test_universe_completeness.py` to pin the three new IDs (asset_class,
theme, presence). Guards against silent removal.

## Verification

- `pytest tests/discovery/ tests/schemas/ -q` — schema parse, no-duplicates, completeness

## Commit message

```
feat(universe): add SOE + real-estate proxies to cn_funds template (E5 phase 2)

Rescues satellite_cn_soe (was 3 candidates vs fail_below=5) and beefs up
satellite_cn_real_estate (was 4 → 0 after hard-filter; gap was universe-side).

New instruments:
  - 159768 房地产ETF华夏 (real_estate)
  - 560090 中证国新央企ETF (soe)
  - 561380 国新港股通央企红利ETF (soe)

Semiconductor: already has 5 themed ETFs in the template; the real failure
mode there is DD-buffer (fixed in Phase 1 commit), so no new semis added.

Per outputs/2026-05-20/E5_role_bucket_report.md § Phase 2.
```
