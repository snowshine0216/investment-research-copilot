# Item 002 — Plan

## Goal
Stop forcing passive bond ETFs to fail the completeness gate over `manager_tenure_years`. Same rationale already used for gold.

## Approach

The watchlist DataFrame row carries `market` (from the universe entry). Thread that into `completeness_ratio` and `missing_required_fields` as an optional kwarg. When `asset_class == "cn_bond_fund"` AND `market == "cn_on_exchange"`, drop `manager_tenure_years` in addition to the existing drops.

The legacy/fallback path in `decision/gates.py:74` (scores without explicit `missing_data`) keeps the asset-class-only required set — conservative, but the production scoring path always populates `missing_data` so it doesn't bite real outputs.

## Steps

### 1. Failing tests first (RED)

File: `tests/decision/test_completeness.py` (append).

```python
def test_required_for_passive_bond_etf_drops_manager_tenure() -> None:
    req = required_for_instrument("cn_bond_fund", "cn_on_exchange")
    assert "manager_tenure_years" not in req
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" not in req
    assert "expense_ratio" in req


def test_required_for_active_bond_fund_keeps_manager_tenure() -> None:
    req = required_for_instrument("cn_bond_fund", "cn_off_exchange")
    assert "manager_tenure_years" in req


def test_completeness_ratio_passive_bond_etf_one_point_zero_without_tenure() -> None:
    row = {
        "expense_ratio": 0.0015,
        "drawdown_3y": 0.02,
        "vol_1y": 0.04,
        # downside_capture / holdings_concentration_top10 / manager_tenure_years all missing
    }
    assert completeness_ratio(row, asset_class="cn_bond_fund", market="cn_on_exchange") == 1.0


def test_completeness_ratio_active_bond_fund_partial_without_tenure() -> None:
    row = {
        "expense_ratio": 0.005,
        "drawdown_3y": 0.05,
        "vol_1y": 0.07,
        # manager_tenure_years missing — active fund cannot ignore it
    }
    # required set for cn_bond_fund off-exchange = 4 fields (full minus aum/holdings/downside)
    # 3/4 present → 0.75
    assert completeness_ratio(row, asset_class="cn_bond_fund", market="cn_off_exchange") == 0.75
```

Run: `uv run pytest tests/decision/test_completeness.py -x` — first test fails with `NameError` (function not imported) or `AssertionError`.

### 2. Code change (GREEN)

File: `src/irc/decision/completeness.py`

Add after `REQUIRED_METRICS_BY_ASSET_CLASS`:

```python
# Passive bond ETFs (on-exchange) drop manager_tenure_years for the same reason
# as gold ETFs: physically/passively replicated, no active manager. Keeping the
# metric required forced every bond-ETF row to data_completeness=0.75 and
# tripped the system-wide data_incomplete gate in outputs/2026-05-18/.
_PASSIVE_BOND_ETF_REQUIRED: tuple[str, ...] = tuple(
    f for f in REQUIRED_METRICS_BY_ASSET_CLASS["cn_bond_fund"]
    if f != "manager_tenure_years"
)


def required_for_instrument(
    asset_class: str | None,
    market: str | None,
) -> tuple[str, ...]:
    """Return the required-metric set for an instrument, branching on both
    asset_class and market. Today the only branch is passive bond ETFs."""
    if asset_class == "cn_bond_fund" and market == "cn_on_exchange":
        return _PASSIVE_BOND_ETF_REQUIRED
    return required_for_asset_class(asset_class)
```

Update `missing_required_fields` and `completeness_ratio` signatures:

```python
def missing_required_fields(
    row: Mapping[str, Any] | None,
    required: Sequence[str] | None = None,
    *,
    asset_class: str | None = None,
    market: str | None = None,
) -> tuple[str, ...]:
    if required is None:
        required = (
            required_for_instrument(asset_class, market)
            if asset_class is not None
            else REQUIRED_METRIC_FIELDS
        )
    ...

def completeness_ratio(
    row: Mapping[str, Any] | None,
    required: Sequence[str] | None = None,
    *,
    asset_class: str | None = None,
    market: str | None = None,
) -> float:
    if required is None:
        required = (
            required_for_instrument(asset_class, market)
            if asset_class is not None
            else REQUIRED_METRIC_FIELDS
        )
    ...
```

File: `src/irc/scoring/pipeline.py`

Lines 87-89: pass `market`:

```python
asset_class = getattr(r, "asset_class", None)
market = getattr(r, "market", None)
completeness = completeness_ratio(m, asset_class=asset_class, market=market)
missing_data = list(missing_required_fields(m, asset_class=asset_class, market=market))
```

### 3. Verify

```
uv run pytest tests/decision/test_completeness.py -v
uv run pytest tests/scoring -v
uv run pytest -q
```

Pre-existing failures from item 001 are still expected (2 unrelated).

### 4. Commit + push + PR

Same flow as 001.
