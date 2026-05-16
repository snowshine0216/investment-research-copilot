from __future__ import annotations

from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.types import OpportunityInput


def _us_etf(tracked: str | None) -> OpportunityInput:
    return OpportunityInput(
        instrument_id="X",
        asset_class="us_etf",
        market="cn_off_exchange",
        tracked_index=tracked,
    )


def _hk_etf(tracked: str | None) -> OpportunityInput:
    return OpportunityInput(
        instrument_id="X",
        asset_class="hk_etf",
        market="cn_off_exchange",
        tracked_index=tracked,
    )


def test_sp500_aliases_normalize_to_标普500():
    for alias in ("S&P 500", "s&p 500", "sp500", "SPX", "S&P500"):
        target = map_lookthrough(_us_etf(alias))
        assert target.key == "sp500", f"alias {alias!r} → key {target.key!r}"
        assert target.display_cn == "标普500", f"alias {alias!r} → display {target.display_cn!r}"


def test_nasdaq100_aliases_normalize_to_纳斯达克100():
    for alias in ("Nasdaq 100", "nasdaq 100", "NDX", "NASDAQ100", "纳斯达克100"):
        target = map_lookthrough(_us_etf(alias))
        assert target.key == "nasdaq100", f"alias {alias!r} → key {target.key!r}"
        assert target.display_cn == "纳斯达克100", f"alias {alias!r} → display {target.display_cn!r}"


def test_unknown_us_index_keeps_raw_key():
    target = map_lookthrough(_us_etf("Made Up Index"))
    assert target.kind == "qdii_us"
    assert target.key == "made up index"  # passthrough when no alias matches


def test_hk_hstech_alias():
    target = map_lookthrough(_hk_etf("恒生科技"))
    assert target.key == "hstech"
    assert target.display_cn == "恒生科技"


def test_hk_unknown_keeps_raw():
    target = map_lookthrough(_hk_etf("Something Else"))
    assert target.kind == "qdii_hk"
    assert target.key == "something else"
