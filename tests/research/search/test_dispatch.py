"""TDD tests for irc.research.search.dispatch.

Covers providers_for_locale, multi_provider_search (fan-out + dedupe + partial
success), and extract_top_pages (top-K extraction + failure capture).
Uses fake providers / extractors to stay I/O-free.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import pytest

from irc.research.search.dispatch import (
    extract_top_pages,
    multi_provider_search,
    provider_results,
    providers_for_locale,
)
from irc.research.search.types import (
    ExtractedPage,
    Locale,
    SearchHit,
    SearchResult,
)


@dataclass
class FakeProvider:
    name: str
    locale: Locale
    hits_to_return: tuple[SearchHit, ...] = ()
    failure: str = ""
    call_log: list[dict] = field(default_factory=list)

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult:
        self.call_log.append({
            "query": query,
            "max_results": max_results,
            "freshness_days": freshness_days,
            "include_domains": include_domains,
        })
        if self.failure:
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason=self.failure,
            )
        return SearchResult(
            query=query, locale=self.locale, hits=self.hits_to_return, provider=self.name,
        )


@dataclass
class FakeExtractor:
    name: str = "fake"
    pages_by_url: dict[str, str] = field(default_factory=dict)
    fail_urls: set[str] = field(default_factory=set)
    raise_urls: set[str] = field(default_factory=set)

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        if url in self.raise_urls:
            raise RuntimeError("extractor raised — should be caught by dispatch")
        if url in self.fail_urls:
            return ExtractedPage(
                url=url, title="", markdown="", fetched_at_iso="2026-05-15T00:00:00Z",
                failure_reason="boom",
            )
        return ExtractedPage(
            url=url, title=f"T {url}", markdown=self.pages_by_url.get(url, ""),
            fetched_at_iso="2026-05-15T00:00:00Z",
        )


# providers_for_locale -------------------------------------------------------

def test_providers_for_locale_returns_only_matching():
    en1 = FakeProvider(name="en1", locale=Locale.EN)
    en2 = FakeProvider(name="en2", locale=Locale.EN)
    zh = FakeProvider(name="zh1", locale=Locale.ZH)
    out = providers_for_locale(Locale.EN, (en1, zh, en2))
    assert out == (en1, en2)


def test_providers_for_locale_raises_when_none_match():
    zh = FakeProvider(name="zh1", locale=Locale.ZH)
    with pytest.raises(ValueError, match="no .* provider"):
        providers_for_locale(Locale.EN, (zh,))


# multi_provider_search ------------------------------------------------------

def _hit(url: str, published: str = "") -> SearchHit:
    return SearchHit(title=f"t {url}", url=url, snippet="", published_iso=published)


def test_multi_provider_search_dedupes_by_url_preferring_first_provider():
    a = FakeProvider(
        name="a", locale=Locale.EN,
        hits_to_return=(_hit("https://x/1"), _hit("https://x/2")),
    )
    b = FakeProvider(
        name="b", locale=Locale.EN,
        hits_to_return=(_hit("https://x/2"), _hit("https://x/3")),
    )
    out = multi_provider_search("q", Locale.EN, (a, b), max_results=10)
    urls = [h.url for h in out]
    assert urls == ["https://x/1", "https://x/2", "https://x/3"]


def test_multi_provider_search_respects_max_results():
    a = FakeProvider(
        name="a", locale=Locale.EN,
        hits_to_return=tuple(_hit(f"https://x/{i}") for i in range(8)),
    )
    out = multi_provider_search("q", Locale.EN, (a,), max_results=3)
    assert len(out) == 3


def test_multi_provider_search_keeps_partial_success_when_one_provider_fails():
    a = FakeProvider(name="a", locale=Locale.EN, failure="boom")
    b = FakeProvider(
        name="b", locale=Locale.EN, hits_to_return=(_hit("https://x/1"),)
    )
    out = multi_provider_search("q", Locale.EN, (a, b), max_results=5)
    assert [h.url for h in out] == ["https://x/1"]


def test_multi_provider_search_returns_empty_when_all_fail():
    a = FakeProvider(name="a", locale=Locale.EN, failure="a-boom")
    b = FakeProvider(name="b", locale=Locale.EN, failure="b-boom")
    out = multi_provider_search("q", Locale.EN, (a, b), max_results=5)
    assert out == ()


def test_multi_provider_search_skips_providers_of_other_locale():
    en = FakeProvider(name="en", locale=Locale.EN, hits_to_return=(_hit("https://x/en"),))
    zh = FakeProvider(name="zh", locale=Locale.ZH, hits_to_return=(_hit("https://x/zh"),))
    out = multi_provider_search("q", Locale.EN, (en, zh), max_results=5)
    assert [h.url for h in out] == ["https://x/en"]
    assert zh.call_log == []


def test_multi_provider_search_passes_freshness_and_filters_to_providers():
    a = FakeProvider(name="a", locale=Locale.EN, hits_to_return=())
    multi_provider_search(
        "q", Locale.EN, (a,),
        max_results=4, freshness_days=14, include_domains=("reuters.com",),
    )
    assert a.call_log == [{
        "query": "q",
        "max_results": 4,
        "freshness_days": 14,
        "include_domains": ("reuters.com",),
    }]


# extract_top_pages ----------------------------------------------------------

def test_extract_top_pages_only_extracts_top_k():
    hits = tuple(_hit(f"https://x/{i}") for i in range(5))
    extractor = FakeExtractor(pages_by_url={h.url: f"md-{i}" for i, h in enumerate(hits)})
    pages = extract_top_pages(hits, extractor, top_k=2)
    assert len(pages) == 2
    assert pages[0].markdown == "md-0"
    assert pages[1].markdown == "md-1"


def test_extract_top_pages_records_failures_without_dropping_them():
    hits = (_hit("https://x/ok"), _hit("https://x/bad"))
    extractor = FakeExtractor(
        pages_by_url={"https://x/ok": "good"},
        fail_urls={"https://x/bad"},
    )
    pages = extract_top_pages(hits, extractor, top_k=5)
    assert len(pages) == 2
    assert pages[0].failure_reason == ""
    assert pages[1].failure_reason == "boom"


def test_extract_top_pages_catches_extractor_exceptions():
    hits = (_hit("https://x/raises"), _hit("https://x/ok"))
    extractor = FakeExtractor(
        pages_by_url={"https://x/ok": "good"},
        raise_urls={"https://x/raises"},
    )
    pages = extract_top_pages(hits, extractor, top_k=5)
    assert len(pages) == 2
    assert pages[0].failure_reason != ""
    assert pages[1].failure_reason == ""


# provider_results -----------------------------------------------------------

def test_provider_results_keeps_failure_reasons():
    a = FakeProvider(name="a", locale=Locale.EN, failure="timeout")
    b = FakeProvider(name="b", locale=Locale.EN, hits_to_return=(_hit("https://x/1"),))

    results = provider_results("q", Locale.EN, (a, b), max_results=5)

    assert [r.provider for r in results] == ["a", "b"]
    assert results[0].failure_reason == "timeout"
    assert results[1].hits[0].url == "https://x/1"


def test_provider_results_skips_wrong_locale():
    en_provider = FakeProvider(name="en", locale=Locale.EN, hits_to_return=(_hit("https://x"),))
    zh_provider = FakeProvider(name="zh", locale=Locale.ZH, hits_to_return=(_hit("https://y"),))

    results = provider_results("q", Locale.EN, (en_provider, zh_provider))

    assert len(results) == 1
    assert results[0].provider == "en"


def test_provider_results_catches_exceptions():
    class RaisingProvider:
        name = "raiser"
        locale = Locale.EN

        def search(self, query, **_):
            raise RuntimeError("network error")

    results = provider_results("q", Locale.EN, (RaisingProvider(),))

    assert len(results) == 1
    assert "provider raised" in results[0].failure_reason
