"""PURE Comp 1: render-derived market composite (news-excluded, renormalized) +
news overlay delta. NO engine change — reads signal.contributions only. The
market/news split reuses signal._FAMILY_OF (one source of truth, shared with
backtest.py)."""
from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.signal import _FAMILY_OF, _bias
from irc.monitor.types import SignalRecord

_NEWS_FAMILY = "news"


@dataclass(frozen=True)
class MarketCompositeView:
    composite: float          # renormalized market-only composite
    bias: str                 # _bias(composite, fund.bands)
    news_delta: float         # C - composite
    eligible_market_factors: int


def _is_market(name: str) -> bool:
    return _FAMILY_OF.get(name) != _NEWS_FAMILY


def market_composite_view(
    signal: SignalRecord, *, bands: dict[str, float],
) -> MarketCompositeView | None:
    """Renormalize the non-news contributions to sum-of-weights 1 and map the
    market-only composite to a bias via the SAME bands the full signal uses.
    Returns None iff no market factor is present."""
    market = [c for c in signal.contributions if _is_market(c.name)]
    total_w = sum(c.renorm_weight for c in market)
    if not market or total_w <= 0:
        return None
    composite = round(sum((c.renorm_weight / total_w) * c.value for c in market), 4)
    return MarketCompositeView(
        composite=composite,
        bias=_bias(composite, bands),
        news_delta=round(signal.composite - composite, 4),
        eligible_market_factors=len(market),
    )
