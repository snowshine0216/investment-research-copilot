# Item 005 — Broaden `_is_hedge_low_corr` predicate (TDD)

## Files

- `src/irc/discovery/role_bucket.py`
- `tests/discovery/test_role_bucket.py`

## Current predicate

```python
def _is_hedge_low_corr(r: UniverseRow) -> bool:
    return r.asset_class == "hk_etf" and "dividend" in (r.tracked_index or "").lower()
```

Only matches index names containing the English word "dividend". HK ETF
universe has plenty of Chinese index names like "恒生中国央企红利" or
"中证港股通央企红利" that should also bucket here as hedge-low-correlation
plays.

Per E5 report § Phase 3:
> hedge_low_correlation: widen to include "HK High Dividend", "恒生中国央企红利"

## TDD: failing tests first

```python
def test_bucket_assigns_hk_high_dividend_etf_to_hedge_low_correlation() -> None:
    rows = (_row_named("3110.HK", "hk_etf", "HK High Dividend"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["hedge_low_correlation"][0].instrument_id == "3110.HK"

def test_bucket_assigns_hsi_central_soe_dividend_to_hedge_low_correlation() -> None:
    # 恒生中国央企红利 (Hang Seng China Central SOE Dividend) — Chinese-only name
    rows = (_row_named("159892", "hk_etf", "恒生中国央企红利"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["hedge_low_correlation"][0].instrument_id == "159892"

def test_bucket_assigns_hk_stock_connect_soe_dividend_to_hedge_low_correlation() -> None:
    # 中证港股通央企红利 — through-train SOE dividend
    rows = (_row_named("513920", "hk_etf", "中证港股通央企红利"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["hedge_low_correlation"][0].instrument_id == "513920"
```

Existing positive case (`Hang Seng Dividend Index`) and the non-matching
non-HK paths (e.g. `513050 中概互联`) must continue working.

## Implementation

Substring whitelist (fragments to match against lowercased `tracked_index`).
Mix of English and Chinese fragments — both treated as case-insensitive
substrings (Chinese has no case but `.lower()` is idempotent on it).

```python
_LOW_CORR_HK_INDEX_FRAGMENTS: tuple[str, ...] = (
    "dividend",          # existing — Hang Seng Dividend, HK High Dividend
    "红利",              # Chinese "dividend/red profit" — 恒生央企红利, 港股通央企红利
)

def _is_hedge_low_corr(r: UniverseRow) -> bool:
    if r.asset_class != "hk_etf":
        return False
    idx = (r.tracked_index or "").lower()
    return any(fragment in idx for fragment in _LOW_CORR_HK_INDEX_FRAGMENTS)
```

The "红利" Chinese fragment catches both 恒生中国央企红利 and 中证港股通央企红利
without me having to enumerate every variant.

## Caveat: scope of "low_corr"

A high-dividend HK ETF is a "low-correlation hedge" because it tilts toward
slow-moving SOE/utility names whose price action is decoupled from the
A-share growth cycle. This is the spirit of the existing predicate — the
broadening just catches Chinese-named indices the original `"dividend"` token
missed.

## Verification

- 3 new tests fail before impl (red)
- Full role_bucket suite green after (33 → 36 tests)
- ruff clean

## Commit message

```
feat(discovery): broaden _is_hedge_low_corr to Chinese-named HK indices (E5 phase 3)

Hang Seng / Stock Connect ETFs tracking 恒生央企红利 or 港股通央企红利 are the
same kind of slow-moving high-dividend SOE basket as Hang Seng Dividend,
but their tracked_index strings contain no English "dividend" token — the
original predicate missed them.

Add Chinese fragment "红利" to the lowercased substring whitelist; existing
"dividend" token still matches. Three new TDD cases pin the Chinese-name paths.

Per outputs/2026-05-20/E5_role_bucket_report.md § Phase 3.
```
