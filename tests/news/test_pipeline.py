from __future__ import annotations
from unittest.mock import patch
from irc.news.rss_aggregator import FeedItem
from irc.news.pipeline import build_news_layer, NewsLayerOutput


_FAKE_ITEMS = [
    FeedItem(title="FOMC minutes patience", summary="", source_url="u1",
              published_iso="2026-05-07", topic="placeholder"),
    FeedItem(title="WGC Q1 +228 tons", summary="", source_url="u2",
              published_iso="2026-05-07", topic="placeholder"),
    FeedItem(title="FOMC minutes patience", summary="", source_url="u1",  # dup
              published_iso="2026-05-07", topic="placeholder"),
]


@patch("irc.news.pipeline.fetch_feeds")
def test_build_news_layer_dedups_and_classifies(mock_fetch):
    mock_fetch.return_value = _FAKE_ITEMS
    out = build_news_layer(feed_urls_by_topic={"us_monetary": ["u1"], "gold_specific": ["u2"]})
    assert isinstance(out, NewsLayerOutput)
    titles = [it.title for it in out.items]
    assert len(titles) == 2  # 1 dup removed
    topics = {it.topic for it in out.items}
    assert "us_monetary" in topics
    assert "gold_specific" in topics
