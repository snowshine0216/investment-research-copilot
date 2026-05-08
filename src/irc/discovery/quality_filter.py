from __future__ import annotations

from typing import Any

import pandas as pd

from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.inputs import RiskBand
from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.universe import UniverseRow


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _numeric_value(metrics: dict, key: str) -> float | None:
    value = metrics.get(key)
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_quality_filter(
    rows: tuple[UniverseRow, ...],
    metrics: pd.DataFrame,
    cfg: DiscoveryConfig,
    risk_band: RiskBand,
) -> HardFilterResult:
    """Step 3 of Discovery. Combines drawdown / tracking_error / tenure rules."""
    qf = cfg.quality_filters
    dd_max = risk_band.max_drawdown[1] * qf.drawdown_3y_buffer
    by_id = metrics.set_index("instrument_id").to_dict("index")
    passed: list[UniverseRow] = []
    rejected: list[Rejection] = []
    for row in rows:
        reasons: list[str] = []
        m = by_id.get(row.instrument_id)
        if m is None:
            reasons.append("no metrics")
        else:
            drawdown = _numeric_value(m, "drawdown_3y")
            if drawdown is None:
                reasons.append("missing drawdown_3y")
            elif drawdown > dd_max:
                reasons.append(f"drawdown_3y {drawdown} > {dd_max}")
            te = _numeric_value(m, "tracking_error")
            if te is None and "etf" in row.asset_class:
                reasons.append("missing tracking_error")
            elif te is not None and te > qf.tracking_error_max and "etf" in row.asset_class:
                reasons.append(f"tracking_error {te} > {qf.tracking_error_max}")
            is_active = row.asset_class.endswith("equity_fund") or row.asset_class.endswith("bond_fund")
            tenure = _numeric_value(m, "manager_tenure_years")
            if is_active and tenure is None:
                reasons.append("missing manager_tenure_years")
            elif is_active and tenure < qf.manager_tenure_years_min:
                reasons.append(f"manager_tenure {tenure}y < {qf.manager_tenure_years_min}y")
        if reasons:
            rejected.append(Rejection(instrument_id=row.instrument_id, reasons=tuple(reasons)))
        else:
            passed.append(row)
    return HardFilterResult(passed=tuple(passed), rejected=tuple(rejected))
