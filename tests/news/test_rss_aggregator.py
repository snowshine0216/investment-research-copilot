from __future__ import annotations
from unittest.mock import patch
from irc.news.rss_aggregator import fetch_feeds, FeedItem


_FAKE_RSS_PARSED = type("FP", (), {
    "entries": [
        type("E", (), {
            "title": "Fed signals patience",
            "link": "https://example.com/1",
            "summary": "FOMC minutes show patience",
            "published": "2026-05-07T10:00:00Z",
        })(),
        type("E", (), {
            "title": "PBoC liquidity injection",
            "link": "https://example.com/2",
            "summary": "1y MLF unchanged",
            "published": "2026-05-06T08:00:00Z",
        })(),
    ]
})()


@patch("irc.news.rss_aggregator.verify_host_resolves_publicly")
@patch("irc.news.rss_aggregator.feedparser.parse", return_value=_FAKE_RSS_PARSED)
def test_fetch_feeds_returns_normalized_items(mock_parse, mock_ssrf):
    items = fetch_feeds(urls=["http://x/rss"], topic="us_monetary")
    assert len(items) == 2
    assert all(isinstance(i, FeedItem) for i in items)
    assert items[0].topic == "us_monetary"
    assert items[0].title == "Fed signals patience"
    assert items[0].source_url == "https://example.com/1"
