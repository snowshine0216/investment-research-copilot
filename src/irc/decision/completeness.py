from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


REQUIRED_METRIC_FIELDS: tuple[str, ...] = (
    "expense_ratio",
    "drawdown_3y",
    "vol_1y",
    "downside_capture",
    "aum_stability_pct",
    "manager_tenure_years",
    "holdings_concentration_top10",
)

MIN_BUY_COMPLETENESS: float = 0.80

# Per-asset-class required metric subsets. Universally dropped:
#   - aum_stability_pct (we do not yet ingest a multi-period AUM history —
#     see metrics_loader.py:54). Keeping it as "required" would bias completeness
#     down across every instrument; honest drop until the data lands.
# Asset-class-specific drops:
#   - holdings_concentration_top10: dropped for index ETFs (the benchmark
#     dictates concentration, not the fund) and for bond/gold (no equity-style
#     top-10). Kept for active equity funds.
#   - downside_capture: dropped for bonds and gold (different reference market;
#     the computed value is not semantically meaningful).
_FULL_MINUS_AUM_STABILITY: tuple[str, ...] = tuple(
    f for f in REQUIRED_METRIC_FIELDS if f != "aum_stability_pct"
)

REQUIRED_METRICS_BY_ASSET_CLASS: Mapping[str, tuple[str, ...]] = {
    "cn_equity_fund": _FULL_MINUS_AUM_STABILITY,
    "cn_etf": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY if f != "holdings_concentration_top10"
    ),
    "us_etf": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY if f != "holdings_concentration_top10"
    ),
    "hk_etf": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY if f != "holdings_concentration_top10"
    ),
    "cn_bond_fund": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY
        if f not in ("holdings_concentration_top10", "downside_capture")
    ),
    "gold": tuple(
        f for f in _FULL_MINUS_AUM_STABILITY
        if f not in (
            "holdings_concentration_top10",
            "downside_capture",
            # Gold ETFs are physically/passively backed — manager tenure is not
            # a meaningful concept and the metric is never ingested. Keeping it
            # required forced every gold row to data_completeness=0.75 and
            # tripped the system-wide data_incomplete blocking gate.
            "manager_tenure_years",
        )
    ),
}


def required_for_asset_class(asset_class: str | None) -> tuple[str, ...]:
    """Return the required-metric set for the given asset_class.

    Unrecognized or `None` asset_class falls back to the full required set
    minus `aum_stability_pct` (the universal drop).
    """
    if asset_class is None:
        return _FULL_MINUS_AUM_STABILITY
    return REQUIRED_METRICS_BY_ASSET_CLASS.get(asset_class, _FULL_MINUS_AUM_STABILITY)


# On-exchange bond ETFs (e.g. 511010 国债ETF国泰, 511260 十年国债ETF国泰,
# 511020, 511520, 511220, 511180, 511380, 159650) are passively replicated.
# Manager-tenure is not meaningful and we never ingest it for them. Keeping
# it required forced every passive bond-ETF row to data_completeness=0.75
# (3/4), tripping the system-wide data_incomplete gate in 2026-05-18.
# Same rationale gold already uses (see _FULL_MINUS_AUM_STABILITY drops above).
_PASSIVE_BOND_ETF_REQUIRED: tuple[str, ...] = tuple(
    f for f in REQUIRED_METRICS_BY_ASSET_CLASS["cn_bond_fund"]
    if f != "manager_tenure_years"
)


def required_for_instrument(
    asset_class: str | None,
    market: str | None,
) -> tuple[str, ...]:
    """Return the required-metric set for an instrument, branching on both
    asset_class and market.

    Today the only market-aware branch is passive bond ETFs (on-exchange
    bond funds). Other asset classes ignore market and fall through to
    ``required_for_asset_class``.

    When ``market`` is None we conservatively keep the asset-class default —
    don't silently apply the passive-bond drop if the caller doesn't know
    the market.
    """
    if asset_class == "cn_bond_fund" and market == "cn_on_exchange":
        return _PASSIVE_BOND_ETF_REQUIRED
    return required_for_asset_class(asset_class)


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def missing_required_fields(
    row: Mapping[str, Any] | None,
    required: Sequence[str] | None = None,
    *,
    asset_class: str | None = None,
    market: str | None = None,
) -> tuple[str, ...]:
    """Return the names of required fields that are missing on `row`.

    Precedence: explicit `required` > `(asset_class, market)`-derived set
    via ``required_for_instrument`` > full required.
    """
    if required is None:
        required = (
            required_for_instrument(asset_class, market)
            if asset_class is not None
            else REQUIRED_METRIC_FIELDS
        )
    if row is None:
        return tuple(required)
    return tuple(field for field in required if is_missing(row.get(field)))


def completeness_ratio(
    row: Mapping[str, Any] | None,
    required: Sequence[str] | None = None,
    *,
    asset_class: str | None = None,
    market: str | None = None,
) -> float:
    """Fraction of required fields present on `row`. 1.0 when nothing is required."""
    if required is None:
        required = (
            required_for_instrument(asset_class, market)
            if asset_class is not None
            else REQUIRED_METRIC_FIELDS
        )
    if not required:
        return 1.0
    missing = missing_required_fields(row, required)
    return (len(required) - len(missing)) / len(required)


def summarize_completeness(rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    if not rows:
        return {"overall_avg": 1.0, "by_asset_class": {}}
    values = [float(row.get("data_completeness", 0.0)) for row in rows]
    by_class_values: dict[str, list[float]] = {}
    for row in rows:
        asset_class = str(row.get("asset_class", "unknown"))
        by_class_values.setdefault(asset_class, []).append(
            float(row.get("data_completeness", 0.0))
        )
    by_asset_class = {
        asset_class: sum(class_values) / len(class_values)
        for asset_class, class_values in by_class_values.items()
    }
    return {"overall_avg": sum(values) / len(values), "by_asset_class": by_asset_class}
