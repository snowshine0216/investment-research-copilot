from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlparse
import feedparser
from irc.llm.http_client import _verify_host_resolves_publicly, SSRFError


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
        host = urlparse(url).hostname or ""
        try:
            _verify_host_resolves_publicly(host)
        except SSRFError:
            continue
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
