from __future__ import annotations
from dataclasses import dataclass
from irc.news.rss_aggregator import fetch_feeds, FeedItem
from irc.news.topic_classifier import classify_topic
from irc.news.dedup import dedup_items


@dataclass(frozen=True)
class NewsLayerOutput:
    items: list[FeedItem]
    counts_per_topic: dict[str, int]


def build_news_layer(feed_urls_by_topic: dict[str, list[str]]) -> NewsLayerOutput:
    """Pull all feeds, classify each item (refining topic), dedup, count per topic."""
    raw: list[FeedItem] = []
    for topic, urls in feed_urls_by_topic.items():
        raw.extend(fetch_feeds(urls=urls, topic=topic))
    refined: list[FeedItem] = []
    for it in raw:
        inferred_topic = classify_topic(it.title + " " + it.summary, url=it.source_url)
        topic = inferred_topic if inferred_topic is not None else it.topic
        refined.append(FeedItem(
            title=it.title, summary=it.summary, source_url=it.source_url,
            published_iso=it.published_iso, topic=topic,
        ))
    deduped = dedup_items(refined)
    counts: dict[str, int] = {}
    for it in deduped:
        counts[it.topic] = counts.get(it.topic, 0) + 1
    return NewsLayerOutput(items=deduped, counts_per_topic=counts)
