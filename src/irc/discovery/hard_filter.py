from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.overrides import OverridesConfig
from irc.discovery.universe import UniverseRow


@dataclass(frozen=True)
class Rejection:
    instrument_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HardFilterResult:
    passed: tuple[UniverseRow, ...]
    rejected: tuple[Rejection, ...]


def _expense_max(asset_class: str, hf) -> float:
    if "etf" in asset_class:
        return hf.cn_passive_expense_ratio_max
    return hf.cn_active_expense_ratio_max


def apply_hard_filter(
    rows: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    cfg: DiscoveryConfig,
    overrides: OverridesConfig,
) -> HardFilterResult:
    """Step 2 of Discovery. Pure: rows + metadata + cfg → (passed, rejected with reasons)."""
    banned = {e.instrument_id for e in overrides.ban_list}
    by_id = metadata.set_index("instrument_id").to_dict("index")
    passed: list[UniverseRow] = []
    rejected: list[Rejection] = []
    hf = cfg.hard_filters
    for row in rows:
        reasons: list[str] = []
        if row.instrument_id in banned:
            reasons.append("ban_list override")
        m = by_id.get(row.instrument_id)
        if m is None:
            reasons.append("no metadata available")
        else:
            if (m.get("inception_years") or 0) < hf.inception_years_min:
                reasons.append(f"inception {m.get('inception_years')}y < {hf.inception_years_min}y")
            if (m.get("aum_cny") or 0) < hf.cn_fund_aum_cny_min:
                reasons.append(f"aum {m.get('aum_cny')} < {hf.cn_fund_aum_cny_min}")
            er_max = _expense_max(row.asset_class, hf)
            if (m.get("expense_ratio") or 1.0) > er_max:
                reasons.append(f"expense_ratio {m.get('expense_ratio')} > {er_max}")
            if "etf" in row.asset_class and (m.get("daily_volume_cny") or 0) < hf.etf_daily_volume_cny_min:
                reasons.append(f"daily_volume {m.get('daily_volume_cny')} < {hf.etf_daily_volume_cny_min}")
        if reasons:
            rejected.append(Rejection(instrument_id=row.instrument_id, reasons=tuple(reasons)))
        else:
            passed.append(row)
    return HardFilterResult(passed=tuple(passed), rejected=tuple(rejected))
