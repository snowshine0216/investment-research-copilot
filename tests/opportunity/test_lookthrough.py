from __future__ import annotations
import pytest

from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.types import OpportunityInput


def _make(**kwargs) -> OpportunityInput:
    base = {
        "instrument_id": "X", "asset_class": "cn_etf", "market": "cn_on_exchange",
    }
    base.update(kwargs)
    return OpportunityInput(**base)


def test_broad_index_etf_maps_to_broad_index_kind():
    target = map_lookthrough(_make(
        instrument_id="510300", asset_class="cn_etf",
        tracked_index="csi300", theme="broad",
    ))
    assert target.kind == "broad_index"
    assert target.key == "csi300"
    assert target.display_cn == "沪深300"


def test_sector_etf_uses_theme_when_tracked_index_unknown():
    target = map_lookthrough(_make(
        instrument_id="512760", asset_class="cn_etf",
        tracked_index=None, theme="semiconductor",
    ))
    assert target.kind == "sector_theme"
    assert target.key == "semiconductor"
    assert target.display_cn == "半导体"


def test_us_qdii_maps_to_qdii_us_kind():
    target = map_lookthrough(_make(
        instrument_id="513100", asset_class="us_etf",
        tracked_index="nasdaq100", theme="tech",
    ))
    assert target.kind == "qdii_us"
    assert target.key == "nasdaq100"
    assert target.display_cn == "纳斯达克100"


def test_hk_qdii_maps_to_qdii_hk_kind():
    target = map_lookthrough(_make(
        instrument_id="513180", asset_class="hk_etf",
        tracked_index="hstech", theme="tech",
    ))
    assert target.kind == "qdii_hk"
    assert target.key == "hstech"
    assert target.display_cn == "恒生科技"


def test_bond_fund_maps_to_bond_kind():
    target = map_lookthrough(_make(
        instrument_id="511010", asset_class="cn_bond_fund",
        tracked_index=None, theme=None,
    ))
    assert target.kind == "bond"
    assert target.key == "cn_bond"


def test_gold_maps_to_gold_kind():
    target = map_lookthrough(_make(
        instrument_id="518880", asset_class="gold",
        tracked_index=None, theme="metals",
    ))
    assert target.kind == "gold"
    assert target.key == "gold"


def test_active_cn_equity_fund_uses_theme_or_active_fund_fallback():
    # theme present -> sector_theme; theme absent -> active_fund
    with_theme = map_lookthrough(_make(
        instrument_id="000001", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme="consumer",
    ))
    assert with_theme.kind == "sector_theme"
    assert with_theme.key == "consumer"

    without_theme = map_lookthrough(_make(
        instrument_id="000002", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme=None,
    ))
    assert without_theme.kind == "active_fund"
    assert without_theme.key == "active_cn_equity"


def test_unknown_index_falls_back_to_kind_with_display_key():
    target = map_lookthrough(_make(
        instrument_id="999999", asset_class="cn_etf",
        tracked_index="some_obscure_index_v2", theme="broad",
    ))
    assert target.kind == "broad_index"
    assert target.key == "some_obscure_index_v2"
    assert target.display_cn  # non-empty fallback
