from __future__ import annotations
from dataclasses import dataclass, field
import re

_INSTRUMENT_PATTERN = re.compile(r"\b(\d{6}|[A-Z]{2,5})\b")
_BULLISH_KEYWORDS = ("上涨", "看多", "看好", "为什么买", "buy", "bull")
_BEARISH_KEYWORDS = ("下跌", "看空", "看跌", "为什么卖", "sell", "bear")
_BUY_TIMING_KEYWORDS = (
    "入手", "加仓", "减仓", "该买", "该卖", "适合买", "可以买", "现在买",
    "能买", "能入手", "可以入手", "建仓", "定投", "抄底", "止盈", "止损",
)
_GOLD_KEYWORDS = ("黄金", "金价", "金条", "gold", "xau")
_US_EQUITY_KEYWORDS = (
    "美股", "标普", "标普500", "纳指", "纳斯达克", "qdii",
    "s&p", "sp500", "nasdaq", "us equity",
)
_CN_EQUITY_KEYWORDS = (
    "a股", "沪深", "中证", "红利", "央企", "国企", "创新",
    "医疗", "成长", "新能源", "消费", "科技",
)
_CN_BOND_KEYWORDS = ("债券", "国债", "政金债", "城投债", "可转债", "信用债", "bond")


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _detect_asset_class(text: str) -> str | None:
    if _has_any(text, _GOLD_KEYWORDS):
        return "gold"
    if _has_any(text, _US_EQUITY_KEYWORDS):
        return "us_equity"
    if _has_any(text, _CN_BOND_KEYWORDS):
        return "cn_bond"
    if _has_any(text, _CN_EQUITY_KEYWORDS):
        return "cn_equity"
    return None


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    instruments_mentioned: list[str]
    intent: str  # "bullish" | "bearish" | "info" | "unknown"
    context_keys: list[str]
    asset_class: str | None = None  # "gold" | "us_equity" | "cn_equity" | "cn_bond" | None


def _classify_intent(question: str, lower: str) -> str:
    if _has_any(lower, _BULLISH_KEYWORDS):
        return "bullish"
    if _has_any(lower, _BEARISH_KEYWORDS):
        return "bearish"
    if (
        "?" in question
        or "吗" in question
        or "什么" in question
        or _has_any(lower, ("how", "what", "why"))
        or _has_any(question, _BUY_TIMING_KEYWORDS)
    ):
        return "info"
    return "unknown"


def _build_context_keys(
    *, intent: str, instruments: list[str], asset_class: str | None, is_buy_timing: bool,
) -> list[str]:
    keys: list[str] = []
    needs_data = (
        bool(instruments)
        or asset_class is not None
        or intent in ("bullish", "bearish", "info")
        or is_buy_timing
    )
    if needs_data:
        keys.extend(["memo", "scores", "decision_report"])
    if asset_class == "gold":
        keys.extend(["gold_regime", "gold_band"])
    return keys


def parse_query(question: str) -> ParsedQuery:
    lower = question.lower()
    instruments = _INSTRUMENT_PATTERN.findall(question)
    intent = _classify_intent(question, lower)
    asset_class = _detect_asset_class(lower)
    is_buy_timing = _has_any(question, _BUY_TIMING_KEYWORDS)
    context_keys = _build_context_keys(
        intent=intent,
        instruments=instruments,
        asset_class=asset_class,
        is_buy_timing=is_buy_timing,
    )
    return ParsedQuery(
        raw=question,
        instruments_mentioned=instruments,
        intent=intent,
        context_keys=context_keys,
        asset_class=asset_class,
    )
