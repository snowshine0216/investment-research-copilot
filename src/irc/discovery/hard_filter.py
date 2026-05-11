from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def _expense_max(row: UniverseRow, hf) -> float:
    if row.asset_class in ("us_etf", "hk_etf") and row.market == "cn_off_exchange":
        return hf.qdii_feeder_expense_ratio_max
    if row.asset_class in ("us_etf", "hk_etf"):
        return hf.us_etf_expense_ratio_max
    if "etf" in row.asset_class:
        return hf.cn_passive_expense_ratio_max
    return hf.cn_active_expense_ratio_max


def _aum_min(asset_class: str, currency: str, hf) -> float:
    if currency == "usd" and asset_class in ("us_etf", "hk_etf"):
        return hf.us_etf_aum_usd_min
    return hf.cn_fund_aum_cny_min


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _numeric_value(metadata: dict, key: str) -> float | None:
    value = metadata.get(key)
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_hard_filter(
    rows: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    cfg: DiscoveryConfig,
    overrides: OverridesConfig,
    excluded_themes: tuple[str, ...] = (),
) -> HardFilterResult:
    """Step 2 of Discovery. Pure: rows + metadata + cfg → (passed, rejected with reasons)."""
    banned = {e.instrument_id for e in overrides.ban_list}
    excluded = frozenset(excluded_themes)
    by_id = metadata.set_index("instrument_id").to_dict("index")
    passed: list[UniverseRow] = []
    rejected: list[Rejection] = []
    hf = cfg.hard_filters
    for row in rows:
        reasons: list[str] = []
        if row.instrument_id in banned:
            reasons.append("ban_list override")
        if row.theme in excluded:
            reasons.append(f"theme excluded: {row.theme}")
        m = by_id.get(row.instrument_id)
        if m is None:
            reasons.append("no metadata available")
        else:
            inception_years = _numeric_value(m, "inception_years")
            if inception_years is None:
                reasons.append("missing inception_years")
            elif inception_years < hf.inception_years_min:
                reasons.append(f"inception {inception_years}y < {hf.inception_years_min}y")
            aum_threshold = _aum_min(row.asset_class, row.currency, hf)
            aum_cny = _numeric_value(m, "aum_cny")
            if aum_cny is None:
                reasons.append("missing aum_cny")
            elif aum_cny < aum_threshold:
                reasons.append(f"aum {aum_cny} < {aum_threshold}")
            er_max = _expense_max(row, hf)
            expense_ratio = _numeric_value(m, "expense_ratio")
            if expense_ratio is None:
                reasons.append("missing expense_ratio")
            elif expense_ratio > er_max:
                reasons.append(f"expense_ratio {expense_ratio} > {er_max}")
            # Off-exchange feeder funds (e.g. 006075) trade at NAV — no exchange volume exists.
            requires_volume = "etf" in row.asset_class and row.market != "cn_off_exchange"
            daily_volume = _numeric_value(m, "daily_volume_cny")
            if requires_volume and daily_volume is None:
                reasons.append("missing daily_volume_cny")
            elif requires_volume and daily_volume < hf.etf_daily_volume_cny_min:
                reasons.append(f"daily_volume {daily_volume} < {hf.etf_daily_volume_cny_min}")
        if reasons:
            rejected.append(Rejection(instrument_id=row.instrument_id, reasons=tuple(reasons)))
        else:
            passed.append(row)
    return HardFilterResult(passed=tuple(passed), rejected=tuple(rejected))
