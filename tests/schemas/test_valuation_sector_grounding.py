from __future__ import annotations

import pytest

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


def test_sector_grounding_rejects_typo_slug():
    """A typo slug must raise at construction — no silent no-op."""
    with pytest.raises((ValueError, Exception)) as exc_info:
        SectorIndexGroundingConfig(activated_slugs=["csi_robotic"])
    assert "csi_robotic" in str(exc_info.value)


def test_sector_grounding_rejects_unknown_slug():
    """A completely unrecognized slug must also raise with the slug named."""
    with pytest.raises((ValueError, Exception)) as exc_info:
        SectorIndexGroundingConfig(activated_slugs=["not_a_slug"])
    assert "not_a_slug" in str(exc_info.value)


def test_sector_grounding_rejects_unknown_among_valid():
    """Mix of valid + invalid slug raises and names only the bad slug."""
    with pytest.raises((ValueError, Exception)) as exc_info:
        SectorIndexGroundingConfig(activated_slugs=["csi_robotics", "csi_robotic"])
    assert "csi_robotic" in str(exc_info.value)


def test_sector_grounding_accepts_multiple_valid_slugs():
    """Multiple real slugs must construct without error."""
    cfg = SectorIndexGroundingConfig(
        activated_slugs=["csi_robotics", "csi_chip", "csi_ai_theme"]
    )
    assert cfg.activated_slugs == ["csi_robotics", "csi_chip", "csi_ai_theme"]
