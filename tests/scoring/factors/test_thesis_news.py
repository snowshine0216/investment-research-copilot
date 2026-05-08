from __future__ import annotations

from irc.scoring.factors.thesis_news import score_thesis_news


def test_thesis_news_stub_returns_neutral_until_plan4() -> None:
    s = score_thesis_news(news_summaries=("placeholder",), raw_refs=("r",))
    assert s.score == 50
    assert "stub" in s.components


def test_thesis_news_stub_no_news_zero_data_completeness() -> None:
    s = score_thesis_news(news_summaries=(), raw_refs=())
    assert s.score == 50
    assert s.components["data_completeness"] == 0.0
