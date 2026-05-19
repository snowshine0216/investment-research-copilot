"""Source tier classifier (item 004, 2026-05-19)."""
from __future__ import annotations

import pytest

from irc.research.source_tier import (
    SourceTier,
    classify,
    is_trusted,
)


@pytest.mark.parametrize("url,expected", [
    ("https://www.pbc.gov.cn/foo/bar", SourceTier.PRIMARY),
    ("https://www.federalreserve.gov/release/abc", SourceTier.PRIMARY),
    ("https://www.csrc.gov.cn/announce", SourceTier.PRIMARY),
    ("https://www.sse.com.cn/quote", SourceTier.PRIMARY),
    ("https://www.reuters.com/business/article", SourceTier.WIRE),
    ("https://apnews.com/story/abc", SourceTier.WIRE),
    ("https://www.kitco.com/news/article", SourceTier.WIRE),
    ("https://isw.pub/post/X", SourceTier.WIRE),
    ("https://www.nytimes.com/article", SourceTier.PAPER),
    ("https://www.wsj.com/economy/x", SourceTier.PAPER),
    ("https://www.ft.com/content/abc", SourceTier.PAPER),
    ("https://www.caixin.com/2026-05-19/abc.html", SourceTier.PAPER),
    ("https://news.mysteel.com/a/abc.html", SourceTier.REPUBLISHER),
    ("https://cj.sina.com.cn/articles/view/abc", SourceTier.REPUBLISHER),
    ("https://www.chinabgao.com/k/yhyjrj.html", SourceTier.REPUBLISHER),
    ("https://random-blog.example.com/post", SourceTier.UNKNOWN),
])
def test_classify_known_hosts(url: str, expected: SourceTier) -> None:
    assert classify(url) == expected


def test_classify_normalizes_www_prefix() -> None:
    assert classify("https://www.reuters.com/x") == SourceTier.WIRE
    assert classify("https://reuters.com/x") == SourceTier.WIRE


def test_classify_subdomain_matching() -> None:
    assert classify("https://m.163.com/dy/article/abc") == SourceTier.REPUBLISHER
    assert classify("https://tks.mysteel.com/a/abc") == SourceTier.REPUBLISHER


def test_classify_does_not_match_lookalike_hostname() -> None:
    """``mysteelxyz.com`` is not a subdomain of ``mysteel.com``."""
    assert classify("https://mysteelxyz.com/a") == SourceTier.UNKNOWN


def test_classify_empty_url_is_unknown() -> None:
    assert classify("") == SourceTier.UNKNOWN
    assert classify("not a url") == SourceTier.UNKNOWN


def test_is_trusted_threshold() -> None:
    assert is_trusted(SourceTier.PRIMARY)
    assert is_trusted(SourceTier.WIRE)
    assert is_trusted(SourceTier.PAPER)
    assert not is_trusted(SourceTier.REPUBLISHER)
    assert not is_trusted(SourceTier.UNKNOWN)


def test_tier_order_is_lower_better() -> None:
    """Test code can use < / <= on tiers."""
    assert SourceTier.PRIMARY < SourceTier.WIRE
    assert SourceTier.WIRE < SourceTier.PAPER
    assert SourceTier.PAPER < SourceTier.REPUBLISHER
    assert SourceTier.REPUBLISHER < SourceTier.UNKNOWN
