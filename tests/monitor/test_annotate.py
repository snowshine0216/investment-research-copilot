from __future__ import annotations
import pytest
from irc.monitor.annotate import factor_annotation, composite_annotation
from irc.monitor.types import FactorContribution, SignalRecord


@pytest.mark.parametrize("value,expected", [
    (0.8, "强上行"), (0.4, "上行"), (0.0, "横盘"), (-0.4, "下行"), (-0.8, "强下行"),
])
def test_trend_bands(value, expected):
    assert factor_annotation("trend", value) == expected


@pytest.mark.parametrize("value,expected", [
    (1.0, "便宜"), (0.5, "中性偏低"), (0.0, "估值中性"), (-0.5, "偏贵"), (-1.0, "很贵"),
])
def test_valuation_bands(value, expected):
    assert factor_annotation("valuation", value) == expected


@pytest.mark.parametrize("value,expected", [
    (1.0, "强净流入"), (0.5, "净流入"), (0.0, "均衡"), (-0.5, "净流出"), (-1.0, "强净流出"),
])
def test_flow_bands(value, expected):
    assert factor_annotation("flow", value) == expected


@pytest.mark.parametrize("value,expected", [
    (0.3, "低拥挤·平静"), (-0.5, "偏拥挤"), (-1.0, "过热"),
])
def test_heat_asymmetric(value, expected):
    assert factor_annotation("heat", value) == expected


def test_macro_tilt_always_marks_news_volatile():
    assert factor_annotation("macro_tilt", 0.6) == "新闻面偏多·新闻面·易变"
    assert factor_annotation("macro_tilt", 0.0) == "中性·新闻面·易变"
    assert factor_annotation("macro_tilt", -0.6) == "偏空·新闻面·易变"


def test_constituent_marks_news():
    assert factor_annotation("constituent", 0.6) == "成分质量高·新闻面"
    assert factor_annotation("constituent", 0.0) == "中等·新闻面"
    assert factor_annotation("constituent", -0.6) == "偏弱·新闻面"


def test_na_value_returns_empty():
    assert factor_annotation("trend", None) == ""
    assert factor_annotation("valuation", None) == ""


def test_unknown_factor_returns_empty():
    assert factor_annotation("mystery", 0.5) == ""


def test_composite_annotation_names_market_vs_news():
    contribs = (
        FactorContribution("trend", .5, .1, .05, 1.0, True, ""),
        FactorContribution("macro_tilt", .5, .8, .40, 1.0, True, ""),
    )
    sig = SignalRecord("x", "ok", "ADD_BIAS", 0.45, 1.0, 1.0, (), contribs, ())
    text = composite_annotation(sig)
    assert "市场面" in text and "新闻叠加" in text
