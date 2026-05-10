from __future__ import annotations
from irc.news.rss_aggregator import FeedItem
import re


def similarity_signature(title: str) -> str:
    """Lowercase, drop digits/punct, keep alphabetic tokens — coarse fingerprint."""
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    cleaned = re.sub(r"\d+", "", cleaned)
    # Remove common stop words
    stop_words = {"a", "an", "the", "and", "or", "by", "in", "at", "to", "for", "of"}
    tokens = [t for t in cleaned.split() if t not in stop_words]
    tokens = sorted(set(tokens))
    return " ".join(tokens)


def dedup_items(items: list[FeedItem]) -> list[FeedItem]:
    """Drop items with same source_url OR same similarity_signature."""
    seen_urls: set[str] = set()
    seen_sigs: set[str] = set()
    out: list[FeedItem] = []
    for it in items:
        if it.source_url and it.source_url in seen_urls:
            continue
        sig = similarity_signature(it.title)
        if sig and sig in seen_sigs:
            continue
        seen_urls.add(it.source_url)
        seen_sigs.add(sig)
        out.append(it)
    return out
