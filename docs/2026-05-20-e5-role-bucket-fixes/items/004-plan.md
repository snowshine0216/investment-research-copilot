# Item 004 — Broaden `_is_core_us` predicate (TDD)

## Files

- `src/irc/discovery/role_bucket.py` — predicate change
- `tests/discovery/test_role_bucket.py` — new failing tests first

## Current predicate

```python
def _is_core_us(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and (r.tracked_index or "").lower() in ("s&p 500", "msci usa")
```

Only matches two literal index names. Misses legitimate broad-US trackers like
Russell 1000, CRSP US Total Market, Russell 3000. E5 report § Phase 3 calls
this out for `core_us_equity` (4 of 12 hard-passers actually bucketed as core).

## TDD: write tests first

```python
def test_bucket_assigns_russell_1000_etf_to_core_us_equity() -> None:
    rows = (_row("IWB", "us_etf", "Russell 1000"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_us_equity"][0].instrument_id == "IWB"

def test_bucket_assigns_crsp_total_market_etf_to_core_us_equity() -> None:
    rows = (_row("VTI", "us_etf", "CRSP US Total Market"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_us_equity"][0].instrument_id == "VTI"

def test_bucket_assigns_russell_3000_etf_to_core_us_equity() -> None:
    rows = (_row("IWV", "us_etf", "Russell 3000"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_us_equity"][0].instrument_id == "IWV"

def test_bucket_does_not_assign_nasdaq_to_core_us_equity() -> None:
    """Sector/factor US ETFs must NOT bucket as core_us — they belong in tech."""
    rows = (_row("QQQ", "us_etf", "Nasdaq 100"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_us_equity"] == ()
    assert out.buckets["satellite_us_tech"][0].instrument_id == "QQQ"

def test_bucket_does_not_assign_sector_us_etf_to_core_us_equity() -> None:
    """E.g. tech-sector SPDR / energy-sector SPDR — not core."""
    rows = (_row("XLK", "us_etf", "Technology Select Sector"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_us_equity"] == ()
```

Existing tests `test_bucket_assigns_us_etf_to_core_us_equity` (S&P 500) and
`test_bucket_assigns_nasdaq_etf_to_satellite_us_tech` (Nasdaq 100) must still
pass.

## Implementation

Switch from a fixed-set check to a substring whitelist. Keeps narrow positive
hits, prevents sector/factor pollution:

```python
_BROAD_US_INDEX_FRAGMENTS = (
    "s&p 500",
    "msci usa",
    "russell 1000",
    "russell 3000",
    "crsp us total market",
)

def _is_core_us(r: UniverseRow) -> bool:
    if r.asset_class != "us_etf":
        return False
    idx = (r.tracked_index or "").lower()
    return any(fragment in idx for fragment in _BROAD_US_INDEX_FRAGMENTS)
```

Note: order matters in `ROLE_RULES`. `core_us_equity` comes before
`satellite_us_tech`. The Nasdaq 100 test expects QQQ to go to tech — which
requires "nasdaq" NOT to match any broad fragment (it doesn't).

## Verification

- New tests fail without impl change (red)
- After impl, all role_bucket tests pass (green)
- ruff check clean

## Commit message

```
feat(discovery): broaden _is_core_us to common broad-market indices (E5 phase 3)

Adds "Russell 1000", "Russell 3000", "CRSP US Total Market" to the core_us
predicate using substring matching instead of fixed-set equality. Per the
E5 report, ~8 broad-US ETFs in the user's universe failed to bucket as core
because their tracked_index wasn't exactly "S&P 500" or "MSCI USA".

Sector / factor ETFs (Nasdaq 100, sector SPDRs) still route to their own
buckets — explicit tests guard against regression.

Per outputs/2026-05-20/E5_role_bucket_report.md § Phase 3.
```
