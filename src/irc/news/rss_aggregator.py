from __future__ import annotations
from dataclasses import dataclass
import feedparser


@dataclass(frozen=True)
class FeedItem:
    title: str
    summary: str
    source_url: str
    published_iso: str
    topic: str


def fetch_feeds(urls: list[str], topic: str) -> list[FeedItem]:
    """Pull a list of RSS URLs and return normalized FeedItems tagged with topic."""
    out: list[FeedItem] = []
    for url in urls:
        parsed = feedparser.parse(url)
        for entry in getattr(parsed, "entries", []):
            out.append(FeedItem(
                title=getattr(entry, "title", "") or "",
                summary=getattr(entry, "summary", "") or "",
                source_url=getattr(entry, "link", "") or "",
                published_iso=getattr(entry, "published", "") or "",
                topic=topic,
            ))
    return out
