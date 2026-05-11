from __future__ import annotations
from irc.news.rss_aggregator import FeedItem
from irc.news.dedup import dedup_items, similarity_signature


def _item(title: str, url: str = "u") -> FeedItem:
    return FeedItem(title=title, summary="", source_url=url, published_iso="t", topic="x")


def test_dedup_removes_exact_url_duplicate():
    items = [_item("a", "u1"), _item("b", "u1")]
    out = dedup_items(items)
    assert len(out) == 1


def test_dedup_keeps_distinct_items():
    items = [_item("Fed cuts rates", "u1"), _item("PBoC injects liquidity", "u2")]
    out = dedup_items(items)
    assert len(out) == 2


def test_dedup_clusters_near_duplicates_by_signature():
    items = [
        _item("Fed cuts rates by 25 bps", "u1"),
        _item("Fed cuts rates 25 bps", "u2"),
    ]
    sig1 = similarity_signature(items[0].title)
    sig2 = similarity_signature(items[1].title)
    # signatures should match for near-duplicates
    assert sig1 == sig2
    out = dedup_items(items)
    assert len(out) == 1
