from __future__ import annotations

from irc.schemas.universe import UniverseConfig
from irc.discovery.universe import enumerate_universe, UniverseRow


def _u(items: list[dict]) -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": items})


def test_enumerate_combines_all_universe_files() -> None:
    out = enumerate_universe(
        qdii_us=_u([{"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
                     "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
                     "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]}]),
        qdii_hk=_u([{"instrument_id": "159920", "ticker": "159920", "market": "cn_on_exchange",
                     "name_cn": "恒生ETF", "asset_class": "hk_etf", "currency": "cny",
                     "tracked_index": "Hang Seng", "venue_required": ["cn_brokerage"]}]),
        cn_funds=_u([]),
        gold=_u([{"instrument_id": "518880", "ticker": "518880", "market": "cn_on_exchange",
                  "name_cn": "华安黄金", "asset_class": "gold", "currency": "cny",
                  "venue_required": ["cn_brokerage"]}]),
    )
    assert len(out) == 3
    assert all(isinstance(r, UniverseRow) for r in out)
    ids = {r.instrument_id for r in out}
    assert ids == {"006075", "159920", "518880"}


def test_enumerate_dedups_by_instrument_id() -> None:
    dup = {"instrument_id": "X", "ticker": "X", "market": "cn_off_exchange",
           "name_cn": "x", "asset_class": "us_etf", "currency": "cny",
           "tracked_index": "i", "venue_required": []}
    out = enumerate_universe(_u([dup]), _u([dup]), _u([]), _u([]))
    assert len(out) == 1
