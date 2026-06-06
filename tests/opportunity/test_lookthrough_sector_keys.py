from __future__ import annotations

from irc.opportunity.lookthrough import (
    _BROAD_INDEX_KEYS,
    _INDEX_NAME_TO_SLUG,
    _INDEX_VALUATION_KEYS,
    _SECTOR_INDEX_DISPLAY,
    _SECTOR_INDEX_KEYS,
)
from irc.opportunity.sector_indices import (
    SECTOR_INDEX_DISPLAY,
    SECTOR_INDEX_KEYS,
)


def test_sector_display_is_sot_backed():
    # lookthrough re-exports the SoT map verbatim (no inline copy).
    assert _SECTOR_INDEX_DISPLAY == SECTOR_INDEX_DISPLAY
    assert len(_SECTOR_INDEX_DISPLAY) == 17
    # Existing metals slugs preserved (regression lock).
    assert _SECTOR_INDEX_DISPLAY["csi_nonferrous"] == "中证有色金属"


def test_sector_keys_mirror_sot_keys():
    assert _SECTOR_INDEX_KEYS == SECTOR_INDEX_KEYS == frozenset(SECTOR_INDEX_DISPLAY)


def test_index_name_to_slug_resolves_sector_names_and_aliases():
    assert _INDEX_NAME_TO_SLUG["中证有色金属"] == "csi_nonferrous"
    assert _INDEX_NAME_TO_SLUG["中证有色"] == "csi_nonferrous"  # colloquial alias preserved
    assert _INDEX_NAME_TO_SLUG["中证机床zz"] == "csi_machine_tool"  # malformed alias (lowercased)
    assert _INDEX_NAME_TO_SLUG["中证机器人"] == "csi_robotics"  # new slug


def test_index_name_to_slug_includes_broad_names():
    # Phase A: broad display names are now inverted so a tracked_index="沪深300"
    # resolves to its slug and grounds on the cached PE-TTM history. (This
    # supersedes Phase B's earlier "excludes broad names" assertion — broad
    # re-activation is exactly what Phase A delivered.)
    assert _INDEX_NAME_TO_SLUG["沪深300"] == "csi300"
    assert _INDEX_NAME_TO_SLUG["中证1000"] == "csi1000"


def test_index_valuation_keys_is_broad_union_sector():
    assert _INDEX_VALUATION_KEYS == _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
    assert "csi300" in _INDEX_VALUATION_KEYS  # broad membership backward-compatible
    assert "csi_nonferrous" in _INDEX_VALUATION_KEYS  # sector
    assert "csi_robotics" in _INDEX_VALUATION_KEYS  # new sector
