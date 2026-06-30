"""PURE Comp 2: render-derived per-factor + composite annotations. Sign
conventions match factor_maps.py. The two news factors (macro_tilt, constituent)
carry a ·新闻面 mark so a reader sees which annotations belong to the volatile
overlay. NO engine change — annotations are presentation only."""
from __future__ import annotations
from irc.monitor.signal import _FAMILY_OF
from irc.monitor.types import SignalRecord

_NEWS_MARK = "·新闻面"
_MACRO_MARK = "·新闻面·易变"


def _band(value: float, cuts: tuple[tuple[float, str], ...], lo: str) -> str:
    """Descending cuts: first (threshold, phrase) with value >= threshold; else lo."""
    for thr, phrase in cuts:
        if value >= thr:
            return phrase
    return lo


_TREND = ((0.6, "强上行"), (0.2, "上行"), (-0.2, "横盘"), (-0.6, "下行"))
_VALUATION = ((0.75, "便宜"), (0.25, "中性偏低"), (-0.25, "估值中性"), (-0.75, "偏贵"))
_FLOW = ((0.75, "强净流入"), (0.25, "净流入"), (-0.25, "均衡"), (-0.75, "净流出"))
_MACRO = ((0.25, "新闻面偏多"), (-0.25, "中性"))
_CONSTITUENT = ((0.25, "成分质量高"), (-0.25, "中等"))


def _heat(value: float) -> str:
    # asymmetric: heat_score caps calm at +0.3, overheated at -1.0
    if value >= 0.0:
        return "低拥挤·平静"
    if value > -0.75:
        return "偏拥挤"
    return "过热"


def factor_annotation(name: str, value: float | None, *, state=None) -> str:
    """PURE: factor name + value → short Chinese phrase; '' when value is None or
    the factor is unknown."""
    if value is None:
        return ""
    if name == "trend":
        return _band(value, _TREND, "强下行")
    if name == "valuation":
        return _band(value, _VALUATION, "很贵")
    if name == "flow":
        return _band(value, _FLOW, "强净流出")
    if name == "heat":
        return _heat(value)
    if name == "macro_tilt":
        return _band(value, _MACRO, "偏空") + _MACRO_MARK
    if name == "constituent":
        return _band(value, _CONSTITUENT, "偏弱") + _NEWS_MARK
    return ""


def _market_dir(contribs) -> str:
    s = sum(c.contribution for c in contribs if _FAMILY_OF.get(c.name) != "news")
    return "偏多" if s > 0.05 else ("偏空" if s < -0.05 else "中性")


def _news_dir(contribs) -> str:
    s = sum(c.contribution for c in contribs if _FAMILY_OF.get(c.name) == "news")
    return "偏多" if s > 0.05 else ("偏空" if s < -0.05 else "中性")


def composite_annotation(signal: SignalRecord) -> str:
    """PURE: name the market vs news drivers, e.g. '市场面中性，新闻叠加偏多'."""
    return f"市场面{_market_dir(signal.contributions)}，新闻叠加{_news_dir(signal.contributions)}"
