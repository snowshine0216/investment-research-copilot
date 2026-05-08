from __future__ import annotations

import pandas as pd

from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.inputs import RiskBand
from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.universe import UniverseRow


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
            if (m.get("drawdown_3y") or 0) > dd_max:
                reasons.append(f"drawdown_3y {m.get('drawdown_3y')} > {dd_max}")
            te = m.get("tracking_error")
            if te is not None and te > qf.tracking_error_max and "etf" in row.asset_class:
                reasons.append(f"tracking_error {te} > {qf.tracking_error_max}")
            is_active = row.asset_class.endswith("equity_fund") or row.asset_class.endswith("bond_fund")
            tenure = m.get("manager_tenure_years")
            if is_active and (tenure or 0) < qf.manager_tenure_years_min:
                reasons.append(f"manager_tenure {tenure}y < {qf.manager_tenure_years_min}y")
        if reasons:
            rejected.append(Rejection(instrument_id=row.instrument_id, reasons=tuple(reasons)))
        else:
            passed.append(row)
    return HardFilterResult(passed=tuple(passed), rejected=tuple(rejected))
