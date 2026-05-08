from __future__ import annotations
from typing import Any
from irc.schemas.triggers import TriggersConfig


def _wants_vix(asset_class: str) -> bool:
    return asset_class in ("us_etf", "hk_etf")


def _wants_real_yield(asset_class: str) -> bool:
    return asset_class == "gold"


def _wants_weekly_drawdown(buy_method: str) -> bool:
    return buy_method.startswith("dca_") or "anchor" in buy_method


def emit_triggers_for_trade(
    asset_class: str, buy_method: str, cfg: TriggersConfig,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, t in cfg.triggers.items():
        keep = (
            (name == "vix_high" and _wants_vix(asset_class))
            or (name == "real_yield_low" and _wants_real_yield(asset_class))
            or (name == "weekly_drawdown" and _wants_weekly_drawdown(buy_method))
        )
        if keep:
            out.append({"name": name, "data_field": t.data_field,
                        "comparator": t.comparator, "threshold": t.threshold})
    return out
