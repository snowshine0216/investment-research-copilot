from __future__ import annotations

from irc.schemas.valuation import (
    SectorIndexGroundingConfig,
    ValuationBucketsConfig,
)

_BUCKETS = [
    {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "x"},
    {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
]


def test_sector_grounding_defaults_to_empty_list():
    cfg = ValuationBucketsConfig(buckets=_BUCKETS)
    assert cfg.sector_index_grounding.activated_slugs == []


def test_sector_grounding_accepts_slugs():
    cfg = ValuationBucketsConfig(
        buckets=_BUCKETS,
        sector_index_grounding={"activated_slugs": ["csi_robotics"]},
    )
    assert cfg.sector_index_grounding.activated_slugs == ["csi_robotics"]


def test_sector_grounding_standalone_default():
    assert SectorIndexGroundingConfig().activated_slugs == []
