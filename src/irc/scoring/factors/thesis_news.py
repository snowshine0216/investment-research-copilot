# src/irc/scoring/factors/thesis_news.py
from __future__ import annotations
from dataclasses import dataclass
from irc.scoring.factors.valuation_cost import FactorScore


_POS = ("growth", "demand", "patience", "rally", "buy", "support", "强劲", "上行", "购金")
_NEG = ("hike", "tighten", "outflow", "weak", "fall", "drag", "降息", "回撤", "撤资")


@dataclass(frozen=True)
class NewsSignals:
    catalyst_count: int
    risk_count: int
    narrative_momentum: float  # -1 to +1


def _signals_from_summaries(summaries: tuple[str, ...]) -> NewsSignals:
    pos_count = 0
    neg_count = 0
    for s in summaries:
        s_low = s.lower()
        pos_count += sum(1 for w in _POS if w in s_low)
        neg_count += sum(1 for w in _NEG if w in s_low)
    if pos_count + neg_count == 0:
        momentum = 0.0
    else:
        momentum = (pos_count - neg_count) / (pos_count + neg_count)
    return NewsSignals(
        catalyst_count=pos_count, risk_count=neg_count, narrative_momentum=momentum,
    )


def score_from_signals(sig: NewsSignals) -> float:
    base = 50 + sig.narrative_momentum * 30
    if sig.catalyst_count >= 3:
        base += 5
    if sig.risk_count >= 3:
        base -= 5
    return max(0.0, min(100.0, base))


def score_thesis_news(
    news_summaries: tuple[str, ...], raw_refs: tuple[str, ...],
) -> FactorScore:
    """Real news-driven score replacing the Plan-2 stub."""
    if not news_summaries:
        return FactorScore(
            score=50.0, raw_refs=raw_refs,
            components={"data_completeness": 0.0, "neutral_default": 1.0},
        )
    sig = _signals_from_summaries(news_summaries)
    score = score_from_signals(sig)
    return FactorScore(
        score=score, raw_refs=raw_refs,
        components={
            "data_completeness": 1.0,
            "catalyst_count": float(sig.catalyst_count),
            "risk_count": float(sig.risk_count),
            "momentum": sig.narrative_momentum,
        },
    )
