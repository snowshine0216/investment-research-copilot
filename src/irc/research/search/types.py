from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Locale(str, Enum):
    EN = "en"
    ZH = "zh"


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    published_iso: str = ""
    source_domain: str = ""


@dataclass(frozen=True)
class SearchResult:
    query: str
    locale: Locale
    hits: tuple[SearchHit, ...] = ()
    provider: str = ""
    failure_reason: str = ""


@dataclass(frozen=True)
class ExtractedPage:
    url: str
    title: str
    markdown: str
    fetched_at_iso: str
    failure_reason: str = ""


class SearchProvider(Protocol):
    name: str
    locale: Locale

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult: ...


class ContentExtractor(Protocol):
    name: str

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage: ...
