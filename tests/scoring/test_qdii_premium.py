from __future__ import annotations

from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES


def test_qdii_asset_classes_is_frozenset_with_three_members() -> None:
    """_QDII_ASSET_CLASSES is the canonical immutable set; consumers import it."""
    assert isinstance(_QDII_ASSET_CLASSES, frozenset)
    assert _QDII_ASSET_CLASSES == frozenset({"us_etf", "hk_etf", "qdii_global"})
