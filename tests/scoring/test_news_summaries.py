# tests/scoring/test_news_summaries.py
from __future__ import annotations

import pandas as pd
import pytest

from irc.research.theme_research import ThemeReport
from irc.research.synthesize import Citation
from irc.scoring.news_summaries import (
    THEMES_BY_ASSET_CLASS,
    build_news_summaries,
    themes_for_instrument,
)


# ---- themes_for_instrument: per real asset_class ----

@pytest.mark.parametrize(
    "asset_class, expected",
    [
        ("gold", ("geopolitics", "gold_drivers", "us_monetary")),
        ("cn_equity_fund", ("cn_equity_property_policy", "cn_monetary", "holdings_sector")),
        ("cn_etf", ("cn_equity_property_policy", "cn_monetary", "holdings_sector")),
        ("cn_bond_fund", ("cn_monetary",)),
        (
            "hk_etf",
            ("cn_equity_property_policy", "cn_monetary", "geopolitics", "holdings_sector"),
        ),
        ("us_etf", ("geopolitics", "us_fiscal_politics", "us_monetary")),
        ("qdii_global", ("geopolitics", "us_fiscal_politics", "us_monetary")),
    ],
)
def test_themes_for_instrument_real_asset_classes(asset_class, expected):
    assert themes_for_instrument(asset_class) == expected


def test_themes_for_instrument_unknown_returns_empty_tuple():
    assert themes_for_instrument("not_a_real_class") == ()
    assert themes_for_instrument("") == ()


def test_themes_for_instrument_returns_sorted_ascending():
    for asset_class in THEMES_BY_ASSET_CLASS:
        themes = themes_for_instrument(asset_class)
        assert list(themes) == sorted(themes), (
            f"{asset_class} mapping must be sorted ASC for determinism"
        )


def test_themes_by_asset_class_is_immutable():
    with pytest.raises(TypeError):
        THEMES_BY_ASSET_CLASS["cn_etf"] = ("anything",)  # type: ignore[index]
