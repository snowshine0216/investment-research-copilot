from __future__ import annotations

from irc.opportunity.lookthrough import (
    _BROAD_INDEX_KEYS,
    _INDEX_NAME_TO_SLUG,
    _INDEX_VALUATION_KEYS,
    _SECTOR_INDEX_DISPLAY,
    _SECTOR_INDEX_KEYS,
)


def test_sector_index_display_has_expected_slugs():
    assert set(_SECTOR_INDEX_DISPLAY) == {
        "csi_nonferrous", "csi_resource", "csi_nonferrous_mining",
    }
    assert _SECTOR_INDEX_DISPLAY["csi_nonferrous"] == "中证有色金属"
    assert _SECTOR_INDEX_DISPLAY["csi_resource"] == "中证资源"
    assert _SECTOR_INDEX_DISPLAY["csi_nonferrous_mining"] == "中证有色金属矿业主题"


def test_sector_index_keys_mirror_display_keys():
    assert _SECTOR_INDEX_KEYS == frozenset(_SECTOR_INDEX_DISPLAY.keys())


def test_index_name_to_slug_inverts_display_names_lowercased():
    # 中文 display names resolve back to slugs (lowercasing is a no-op for CJK).
    assert _INDEX_NAME_TO_SLUG["中证有色金属"] == "csi_nonferrous"
    assert _INDEX_NAME_TO_SLUG["中证资源"] == "csi_resource"
    assert _INDEX_NAME_TO_SLUG["中证有色金属矿业主题"] == "csi_nonferrous_mining"
    # Colloquial short form also resolves.
    assert _INDEX_NAME_TO_SLUG["中证有色"] == "csi_nonferrous"


def test_index_name_to_slug_includes_broad_names():
    # Phase A: broad display names are now inverted so a tracked_index="沪深300"
    # resolves to its slug and grounds on the cached PE-TTM history.
    assert _INDEX_NAME_TO_SLUG["沪深300"] == "csi300"
    assert _INDEX_NAME_TO_SLUG["中证1000"] == "csi1000"


def test_index_valuation_keys_is_broad_union_sector():
    assert _INDEX_VALUATION_KEYS == _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
    # Broad keys still present (membership backward-compatible).
    assert "csi300" in _INDEX_VALUATION_KEYS
    assert "csi_nonferrous" in _INDEX_VALUATION_KEYS
