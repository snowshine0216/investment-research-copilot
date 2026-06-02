from __future__ import annotations

from irc.narrative.schemas import (
    Holding,
    NarrativeBasket,
    OverlapResult,
    ShortlistRow,
)


def _basket_hit(holding: Holding, basket: NarrativeBasket) -> bool:
    symbols = {s.symbol for s in basket.basket}
    names = {s.name_cn for s in basket.basket}
    return holding.symbol in symbols or holding.name_cn in names


def _industry_hit(holding: Holding, basket: NarrativeBasket) -> bool:
    return bool(holding.sw_industry) and holding.sw_industry in basket.industries_sw


def score_overlap(holdings: tuple[Holding, ...], basket: NarrativeBasket) -> OverlapResult:
    """Pure: match a fund's top-10 against the basket (symbol first, name second),
    crediting SW-industry membership for non-basket names. No double-count."""
    matched: list[str] = []
    industry_credit: list[str] = []
    weight = 0.0
    seen: set[str] = set()
    for h in holdings:
        if h.symbol in seen:
            continue
        seen.add(h.symbol)
        if _basket_hit(h, basket):
            matched.append(h.symbol)
            weight += h.weight_pct
        elif _industry_hit(h, basket):
            industry_credit.append(h.symbol)
            weight += h.weight_pct
    return OverlapResult(
        basket_weight_pct=round(weight, 4),
        overlap_count=len(matched) + len(industry_credit),
        matched_symbols=tuple(sorted(matched)),
        industry_credit_symbols=tuple(sorted(industry_credit)),
    )


def _qualifies(row: ShortlistRow, min_weight: float, min_count: int) -> bool:
    ov = row.overlap
    return ov.basket_weight_pct >= min_weight or ov.overlap_count >= min_count


def _sort_key(row: ShortlistRow) -> tuple[float, int, str]:
    ov = row.overlap
    return (-ov.basket_weight_pct, -ov.overlap_count, row.instrument_id)


def rank_shortlist(
    rows: tuple[ShortlistRow, ...],
    *,
    min_basket_weight_pct: float,
    min_overlap_count: int,
    top_n: int,
) -> tuple[ShortlistRow, ...]:
    """Pure: keep rows meeting EITHER threshold, sort
    (weight DESC, count DESC, id ASC), truncate to top_n."""
    kept = [r for r in rows if _qualifies(r, min_basket_weight_pct, min_overlap_count)]
    ordered = sorted(kept, key=_sort_key)
    return tuple(ordered[:top_n])
