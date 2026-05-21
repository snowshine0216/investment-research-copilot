from __future__ import annotations
from pathlib import Path

import pytest
import yaml
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


def test_universe_theme_is_validated() -> None:
    raw = {
        "instruments": [
            {"instrument_id": "512760", "ticker": "512760", "market": "cn_on_exchange",
             "name_cn": "半导体ETF", "asset_class": "cn_etf", "currency": "cny",
             "tracked_index": "中证全指半导体", "theme": "not_a_theme",
             "venue_required": ["cn_brokerage"]},
        ]
    }
    with pytest.raises(ValidationError, match="not_a_theme"):
        UniverseConfig.model_validate(raw)


def test_instrument_accepts_qdii_global_asset_class():
    from irc.schemas.universe import Instrument

    inst = Instrument.model_validate({
        "instrument_id": "270023",
        "ticker": "270023",
        "market": "cn_off_exchange",
        "name_cn": "广发全球精选股票(QDII)人民币A",
        "asset_class": "qdii_global",
        "currency": "cny",
        "venue_required": ["cmb_fund"],
    })

    assert inst.asset_class == "qdii_global"


def test_cn_funds_template_theme_inventory() -> None:
    root = Path(__file__).parents[2]
    raw = yaml.safe_load(
        (root / "src/irc/templates/config/universe/cn_funds.yaml").read_text(encoding="utf-8")
    )
    cfg = UniverseConfig.model_validate(raw)
    themes = {i.theme for i in cfg.instruments if i.theme is not None}

    assert themes == {
        "broad", "dividend", "tech", "semiconductor", "defense", "healthcare",
        "new_energy", "consumer", "finance", "metals", "real_estate", "soe",
    }
    ids = [i.instrument_id for i in cfg.instruments]
    assert len(ids) == len(set(ids))
