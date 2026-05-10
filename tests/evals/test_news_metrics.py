from __future__ import annotations
from evals.news.metrics import coverage_per_topic_per_week, dedup_rate, citation_reachability


def _make_articles():
    return [
        {"topic": "macro", "url": "https://a.com/1", "title": "Article 1"},
        {"topic": "macro", "url": "https://a.com/2", "title": "Article 2"},
        {"topic": "macro", "url": "https://a.com/3", "title": "Article 3"},
        {"topic": "equity", "url": "https://a.com/4", "title": "Article 4"},
        {"topic": "equity", "url": "", "title": "Article 5"},
        {"topic": "macro", "url": "https://a.com/1", "title": "Article 1"},  # duplicate
    ]


def test_coverage_per_topic_per_week():
    articles = _make_articles()
    cov = coverage_per_topic_per_week(articles)
    assert cov["macro"] == 4  # includes duplicate
    assert cov["equity"] == 2


def test_dedup_rate_with_duplicates():
    articles = _make_articles()
    rate = dedup_rate(articles)
    # 5 unique urls (one empty counts as unique key ""), out of 6
    assert 0 < rate < 1.0


def test_dedup_rate_all_unique():
    articles = [
        {"url": f"https://a.com/{i}", "topic": "macro"} for i in range(5)
    ]
    assert dedup_rate(articles) == 1.0


def test_dedup_rate_empty():
    assert dedup_rate([]) == 1.0


def test_citation_reachability():
    articles = _make_articles()
    rate = citation_reachability(articles)
    # 5 out of 6 have non-empty url
    assert abs(rate - 5 / 6) < 1e-9


def test_citation_reachability_empty():
    assert citation_reachability([]) == 1.0
