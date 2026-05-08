from __future__ import annotations

from irc.scoring.factors.valuation_cost import FactorScore


def score_thesis_news(
    news_summaries: tuple[str, ...],
    raw_refs: tuple[str, ...],
) -> FactorScore:
    """Plan-2 stub: returns neutral 50. Plan 4 swaps in real news-driven scoring."""
    return FactorScore(
        score=50.0,
        raw_refs=raw_refs,
        components={
            "stub": 1.0,
            "data_completeness": 1.0 if news_summaries else 0.0,
        },
    )
