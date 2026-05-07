from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.universe import UniverseConfig


def test_universe_minimal():
    raw = {
        "instruments": [
            {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
             "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
             "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
        ]
    }
    cfg = UniverseConfig.model_validate(raw)
    assert cfg.instruments[0].instrument_id == "006075"


def test_universe_duplicate_ids_fail():
    raw = {
        "instruments": [
            {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
             "name_cn": "x", "asset_class": "us_etf", "currency": "cny",
             "tracked_index": "y", "venue_required": ["cmb_fund"]},
            {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
             "name_cn": "x", "asset_class": "us_etf", "currency": "cny",
             "tracked_index": "y", "venue_required": ["cmb_fund"]},
        ]
    }
    with pytest.raises(ValidationError, match="duplicate"):
        UniverseConfig.model_validate(raw)
