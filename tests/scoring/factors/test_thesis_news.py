# tests/scoring/factors/test_thesis_news.py
from __future__ import annotations
from irc.scoring.factors.thesis_news import (
    score_thesis_news, NewsSignals, score_from_signals,
)


def test_high_positive_signals_score_higher():
    sig_pos = NewsSignals(catalyst_count=4, risk_count=1, narrative_momentum=0.8)
    sig_neg = NewsSignals(catalyst_count=1, risk_count=4, narrative_momentum=-0.5)
    assert score_from_signals(sig_pos) > score_from_signals(sig_neg)


def test_no_news_returns_neutral_with_low_completeness():
    s = score_thesis_news(news_summaries=(), raw_refs=())
    assert s.score == 50
    assert s.components["data_completeness"] == 0.0


def test_with_news_uses_signals():
    s = score_thesis_news(
        news_summaries=("Fed signals patience", "Strong demand for gold"),
        raw_refs=("ref1",),
    )
    assert 0 <= s.score <= 100
    assert s.components["data_completeness"] == 1.0
