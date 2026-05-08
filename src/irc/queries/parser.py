from __future__ import annotations
from dataclasses import dataclass
import re

_INSTRUMENT_PATTERN = re.compile(r"\b(\d{6}|[A-Z]{2,5})\b")
_BULLISH_KEYWORDS = ("上涨", "看多", "看好", "为什么买", "buy", "bull")
_BEARISH_KEYWORDS = ("下跌", "看空", "看跌", "为什么卖", "sell", "bear")


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    instruments_mentioned: list[str]
    intent: str  # "bullish" | "bearish" | "info" | "unknown"
    context_keys: list[str]  # sections of the memo or scoring to attach


def parse_query(question: str) -> ParsedQuery:
    lower = question.lower()
    instruments = _INSTRUMENT_PATTERN.findall(question)
    if any(k in lower for k in _BULLISH_KEYWORDS):
        intent = "bullish"
    elif any(k in lower for k in _BEARISH_KEYWORDS):
        intent = "bearish"
    elif "?" in question or "吗" in question or "什么" in question or "how" in lower or "what" in lower or "why" in lower:
        intent = "info"
    else:
        intent = "unknown"
    context_keys = []
    if instruments:
        context_keys.append("scores")
    if intent in ("bullish", "bearish"):
        context_keys.append("memo")
    return ParsedQuery(raw=question, instruments_mentioned=instruments, intent=intent, context_keys=context_keys)
