from __future__ import annotations

from irc.narrative.schemas import BasketStock, Holding, NarrativeBasket, OverlapResult, ShortlistRow
from irc.narrative.screen import rank_shortlist, score_overlap


def _basket() -> NarrativeBasket:
    return NarrativeBasket(
        narrative_id="compute_metals",
        display_name_cn="算力金属",
        display_name_en="Compute-demand metals",
        thesis_cn="t",
        basket=(
            BasketStock(symbol="601899", name_cn="紫金矿业"),
            BasketStock(symbol="600362", name_cn="江西铜业"),
        ),
        industries_sw=("有色金属/工业金属",),
        min_basket_weight_pct=15.0,
        min_overlap_count=2,
        top_n=15,
    )


def test_symbol_match_sums_weight_and_counts() -> None:
    holdings = (
        Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0),
        Holding(symbol="600362", name_cn="江西铜业", weight_pct=6.0),
        Holding(symbol="600519", name_cn="贵州茅台", weight_pct=5.0),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.basket_weight_pct == 15.0
    assert ov.overlap_count == 2
    assert ov.matched_symbols == ("600362", "601899")  # sorted ASC


def test_name_match_when_symbol_differs() -> None:
    # symbol mismatch but name_cn matches a basket entry -> credited
    holdings = (Holding(symbol="999999", name_cn="紫金矿业", weight_pct=4.0),)
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 1
    assert ov.basket_weight_pct == 4.0


def test_industry_credit_for_non_basket_name() -> None:
    holdings = (
        Holding(symbol="000060", name_cn="中金岭南", weight_pct=3.0,
                sw_industry="有色金属/工业金属"),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 1
    assert ov.industry_credit_symbols == ("000060",)
    assert ov.basket_weight_pct == 3.0


def test_no_double_count_when_basket_and_industry_both_hit() -> None:
    holdings = (
        Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0,
                sw_industry="有色金属/工业金属"),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 1
    assert ov.basket_weight_pct == 9.0
    assert ov.industry_credit_symbols == ()  # basket match takes precedence


def test_empty_holdings_zero_overlap() -> None:
    ov = score_overlap((), _basket())
    assert ov.basket_weight_pct == 0.0
    assert ov.overlap_count == 0
    assert ov.matched_symbols == ()


# ── F1: score_overlap duplicate-symbol defensive dedup ───────────────────────


def test_score_overlap_deduplicates_duplicate_basket_symbol() -> None:
    """F1: input holdings with a dup basket symbol → overlap_count / weight counted once."""
    holdings = (
        Holding(symbol="601899", name_cn="紫金矿业", weight_pct=9.0),
        Holding(symbol="601899", name_cn="紫金矿业", weight_pct=5.0),  # dup
        Holding(symbol="600362", name_cn="江西铜业", weight_pct=6.0),
    )
    ov = score_overlap(holdings, _basket())
    assert ov.overlap_count == 2  # 601899 + 600362, not 3
    assert ov.basket_weight_pct == 15.0  # 9.0 + 6.0, not 20.0
    assert ov.matched_symbols.count("601899") == 1  # no dup in matched_symbols


def _row(iid: str, weight: float, count: int) -> ShortlistRow:
    ov = OverlapResult(
        basket_weight_pct=weight,
        overlap_count=count,
        matched_symbols=(),
        industry_credit_symbols=(),
    )
    return ShortlistRow(
        instrument_id=iid, name_cn=f"fund-{iid}",
        asset_class="cn_equity_fund", overlap=ov, holdings=(),
    )


def test_keeps_rows_meeting_either_threshold() -> None:
    rows = (
        _row("A", weight=20.0, count=1),  # weight threshold met
        _row("B", weight=5.0, count=2),   # count threshold met
        _row("C", weight=5.0, count=1),   # neither -> dropped
    )
    out = rank_shortlist(rows, min_basket_weight_pct=15.0, min_overlap_count=2, top_n=15)
    assert tuple(r.instrument_id for r in out) == ("A", "B")


def test_stable_sort_weight_then_count_then_id() -> None:
    rows = (
        _row("Z", weight=30.0, count=2),
        _row("Y", weight=30.0, count=3),  # higher count -> before Z
        _row("X", weight=40.0, count=1),  # higher weight -> first
        _row("W", weight=30.0, count=2),  # tie with Z on weight+count -> id asc
    )
    out = rank_shortlist(rows, min_basket_weight_pct=15.0, min_overlap_count=2, top_n=15)
    assert tuple(r.instrument_id for r in out) == ("X", "Y", "W", "Z")


def test_top_n_truncation() -> None:
    rows = tuple(_row(f"{i:03d}", weight=20.0, count=2) for i in range(20))
    out = rank_shortlist(rows, min_basket_weight_pct=15.0, min_overlap_count=2, top_n=5)
    assert len(out) == 5
