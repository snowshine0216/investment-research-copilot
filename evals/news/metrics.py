from __future__ import annotations
from collections import defaultdict


def coverage_per_topic_per_week(articles: list[dict]) -> dict[str, int]:
    """Count articles per topic in the most recent week bucket."""
    counts: dict[str, int] = defaultdict(int)
    for a in articles:
        topic = a.get("topic", "unknown")
        counts[topic] += 1
    return dict(counts)


def dedup_rate(articles: list[dict]) -> float:
    """Fraction of articles that are unique (no duplicate url/title)."""
    if not articles:
        return 1.0
    seen: set[str] = set()
    unique = 0
    for a in articles:
        key = a.get("url") or a.get("title", "")
        if key not in seen:
            seen.add(key)
            unique += 1
    return unique / len(articles)


def citation_reachability(articles: list[dict]) -> float:
    """Fraction of articles whose url is non-empty (reachable)."""
    if not articles:
        return 1.0
    reachable = sum(1 for a in articles if a.get("url", "").strip())
    return reachable / len(articles)
