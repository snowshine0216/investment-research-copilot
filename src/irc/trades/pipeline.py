from __future__ import annotations
from typing import Any, TypedDict
from irc.schemas.universe import UniverseConfig
from irc.schemas.valuation import ValuationBucketsConfig
from irc.schemas.triggers import TriggersConfig
from irc.trades.buy_method import default_buy_method
from irc.trades.valuation_percentile import method_for_percentile
from irc.trades.venue_check import check_venue
from irc.trades.triggers import emit_triggers_for_trade


class TradePlanRow(TypedDict):
    target: str
    asset_class: str
    role: str
    target_weight: float
    intra_class_share: float
    composite_score: float
    buy_method: str
    granularity: str
    venue_compatible: bool
    venue_note: str
    proxy_id: str | None
    triggers: list[dict[str, Any]]


def build_trade_plan(
    selected_instruments: list[dict[str, Any]],
    mode: str,
    valuation_percentiles: dict[str, float],
    available_venues: list[str],
    universe: UniverseConfig,
    valuation: ValuationBucketsConfig,
    triggers: TriggersConfig,
) -> list[TradePlanRow]:
    rows: list[TradePlanRow] = []
    for sel in selected_instruments:
        ac = sel["asset_class"]
        venue = check_venue(sel["instrument_id"], available_venues, universe)
        target_id = sel["instrument_id"] if venue.compatible or venue.proxy_id is None else venue.proxy_id
        proxy_class = ac
        if venue.proxy_id is not None and target_id == venue.proxy_id:
            proxy_obj = next(
                (i for i in universe.instruments if i.instrument_id == venue.proxy_id), None
            )
            if proxy_obj is not None:
                proxy_class = proxy_obj.asset_class
        pct = valuation_percentiles.get(proxy_class)
        if pct is not None:
            choice = method_for_percentile(pct, valuation)
            method = choice.buy_method
            granularity = choice.granularity
        else:
            method = default_buy_method(asset_class=proxy_class, mode=mode)  # type: ignore[arg-type]
            granularity = "default"
        trigs = emit_triggers_for_trade(asset_class=proxy_class, buy_method=method, cfg=triggers)
        rows.append(TradePlanRow(
            target=target_id, asset_class=proxy_class,
            role=sel.get("role", ""),
            target_weight=sel["target_weight"], intra_class_share=sel["intra_class_share"],
            composite_score=sel["composite_score"],
            buy_method=method, granularity=granularity,
            venue_compatible=venue.compatible, venue_note=venue.note,
            proxy_id=venue.proxy_id,
            triggers=trigs,
        ))
    return rows
