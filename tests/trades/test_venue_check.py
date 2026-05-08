from __future__ import annotations
from irc.schemas.universe import UniverseConfig
from irc.trades.venue_check import check_venue, VenueCheckResult


def _u(items: list[dict]) -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": items})


def test_compatible_when_user_has_required_venue():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["us_brokerage"],
                      universe=universe)
    assert isinstance(out, VenueCheckResult)
    assert out.compatible is True
    assert out.proxy_id is None


def test_incompatible_with_proxy_suggestion():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["cmb_fund", "cmb_gold"],
                      universe=universe)
    assert out.compatible is False
    assert out.proxy_id == "006075"


def test_no_proxy_available():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "Russell 2000", "venue_required": ["us_brokerage"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["cmb_fund"],
                      universe=universe)
    assert out.compatible is False
    assert out.proxy_id is None
