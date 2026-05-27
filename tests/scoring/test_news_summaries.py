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


# ---- build_news_summaries: empty input ----

def _watchlist(*rows: dict) -> pd.DataFrame:
    """Tiny helper: build a watchlist DataFrame for tests."""
    return pd.DataFrame(list(rows))


def _report(theme: str, report_md: str = "", failure_reason: str = "") -> ThemeReport:
    return ThemeReport(
        theme=theme,
        query="",
        locale="EN",
        report_md=report_md,
        citations=[],
        failure_reason=failure_reason,
        provider_failures=(),
    )


def test_build_news_summaries_empty_reports_and_empty_watchlist():
    out = build_news_summaries(reports={}, watchlist=_watchlist())
    assert out == {}


def test_build_news_summaries_empty_reports_populated_watchlist():
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports={}, watchlist=wl)
    # Key present, but value is empty tuple (gold has mapped themes, none populated)
    assert out == {"518880": ()}


def test_build_news_summaries_gold_uses_mapped_themes():
    reports = {
        "us_monetary": _report("us_monetary", "Fed signals patience on hikes."),
        "gold_drivers": _report("gold_drivers", "Strong demand for gold ETFs."),
        "geopolitics": _report("geopolitics", "Middle East tensions rise."),
        "cn_monetary": _report("cn_monetary", "PBoC unrelated text."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # Sorted ASC by theme name: geopolitics, gold_drivers, us_monetary
    assert out == {
        "518880": (
            "Middle East tensions rise.",
            "Strong demand for gold ETFs.",
            "Fed signals patience on hikes.",
        ),
    }


def test_build_news_summaries_qdii_global_themes():
    reports = {
        "us_monetary": _report("us_monetary", "Fed text."),
        "us_fiscal_politics": _report("us_fiscal_politics", "Fiscal text."),
        "geopolitics": _report("geopolitics", "Geopolitics text."),
    }
    wl = _watchlist({"instrument_id": "QD0001", "asset_class": "qdii_global"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # Sorted ASC: geopolitics, us_fiscal_politics, us_monetary
    assert out == {
        "QD0001": ("Geopolitics text.", "Fiscal text.", "Fed text."),
    }


def test_build_news_summaries_skips_failed_reports_silently():
    reports = {
        "us_monetary": _report("us_monetary", "", failure_reason="provider 503"),
        "gold_drivers": _report("gold_drivers", "Real gold-drivers prose."),
        "geopolitics": _report("geopolitics", "Real geopolitics prose."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # us_monetary skipped (failure_reason set); only the two populated themes survive.
    assert out == {"518880": ("Real geopolitics prose.", "Real gold-drivers prose.")}


def test_build_news_summaries_skips_empty_report_md():
    reports = {
        "us_monetary": _report("us_monetary", ""),  # empty prose, no failure_reason
        "gold_drivers": _report("gold_drivers", "Real gold-drivers prose."),
        "geopolitics": _report("geopolitics", "Real geopolitics prose."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {"518880": ("Real geopolitics prose.", "Real gold-drivers prose.")}


def test_build_news_summaries_unknown_asset_class_gives_empty_tuple():
    reports = {"us_monetary": _report("us_monetary", "anything")}
    wl = _watchlist({"instrument_id": "X1", "asset_class": "totally_new_class"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {"X1": ()}


def test_build_news_summaries_mixed_watchlist_keys_every_row():
    reports = {
        "cn_monetary": _report("cn_monetary", "PBoC text."),
        "gold_drivers": _report("gold_drivers", "Gold text."),
        "geopolitics": _report("geopolitics", "Geo text."),
        "us_monetary": _report("us_monetary", "Fed text."),
    }
    wl = _watchlist(
        {"instrument_id": "511880", "asset_class": "cn_bond_fund"},
        {"instrument_id": "518880", "asset_class": "gold"},
        {"instrument_id": "MM01", "asset_class": "totally_new_class"},
    )
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {
        "511880": ("PBoC text.",),
        "518880": ("Geo text.", "Gold text.", "Fed text."),
        "MM01": (),
    }


def test_build_news_summaries_is_deterministic_two_calls_equal():
    reports = {
        "us_monetary": _report("us_monetary", "Fed text."),
        "gold_drivers": _report("gold_drivers", "Gold text."),
        "geopolitics": _report("geopolitics", "Geo text."),
        "cn_monetary": _report("cn_monetary", "PBoC text."),
    }
    wl = _watchlist(
        {"instrument_id": "518880", "asset_class": "gold"},
        {"instrument_id": "511880", "asset_class": "cn_bond_fund"},
    )
    a = build_news_summaries(reports=reports, watchlist=wl)
    b = build_news_summaries(reports=reports, watchlist=wl)
    assert a == b
    # Stronger: the serialised form must be byte-identical too (sorted tuples
    # protect against dict-ordering drift in the per-instrument value).
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
