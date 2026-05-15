"""TDD tests for BraveNewsProvider.

Brave Search News API: GET https://api.search.brave.com/res/v1/news/search
Authentication: X-Subscription-Token header. Freshness: pd/pw/pm/py buckets.
"""
from __future__ import annotations
import httpx
import respx

from irc.research.search.brave_provider import BraveNewsProvider
from irc.research.search.types import Locale, SearchResult


BRAVE_URL = "https://api.search.brave.com/res/v1/news/search"


def _provider() -> BraveNewsProvider:
    return BraveNewsProvider(api_key="brv-test-key", timeout_s=5)


@respx.mock
def test_search_happy_path_returns_hits():
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "news",
                "results": [
                    {
                        "title": "Fed holds",
                        "url": "https://reuters.com/fed-1",
                        "description": "The Fed kept rates.",
                        "page_age": "2026-05-08T12:00:00",
                        "meta_url": {"hostname": "reuters.com"},
                    },
                    {
                        "title": "Markets react",
                        "url": "https://wsj.com/m-1",
                        "description": "Stocks edged higher.",
                    },
                ],
            },
        )
    )
    out = _provider().search("Fed", max_results=5)
    assert isinstance(out, SearchResult)
    assert out.failure_reason == ""
    assert out.locale == Locale.EN
    assert out.provider == "brave_news"
    assert len(out.hits) == 2
    assert out.hits[0].title == "Fed holds"
    assert out.hits[0].published_iso == "2026-05-08T12:00:00"
    assert out.hits[0].source_domain == "reuters.com"
    assert out.hits[1].published_iso == ""
    assert out.hits[1].source_domain == "wsj.com"


@respx.mock
def test_search_5xx_returns_failure_reason():
    respx.get(BRAVE_URL).mock(return_value=httpx.Response(502))
    out = _provider().search("x")
    assert out.hits == ()
    assert "502" in out.failure_reason


@respx.mock
def test_search_timeout_returns_failure_reason():
    respx.get(BRAVE_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    out = _provider().search("x")
    assert out.hits == ()
    assert out.failure_reason != ""


@respx.mock
def test_search_malformed_response_returns_failure_reason():
    respx.get(BRAVE_URL).mock(return_value=httpx.Response(200, json={"type": "news"}))
    out = _provider().search("x")
    assert out.hits == ()
    assert "results" in out.failure_reason.lower()


@respx.mock
def test_search_sends_subscription_token_header():
    route = respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(200, json={"type": "news", "results": []})
    )
    _provider().search("x")
    assert route.calls[0].request.headers.get("x-subscription-token") == "brv-test-key"
    assert route.calls[0].request.headers.get("accept") == "application/json"


@respx.mock
def test_search_passes_query_count_and_freshness_bucket():
    route = respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(200, json={"type": "news", "results": []})
    )
    _provider().search("hello", max_results=8, freshness_days=7)
    url = str(route.calls[0].request.url)
    assert "q=hello" in url
    assert "count=8" in url
    assert "freshness=pw" in url


@respx.mock
def test_search_maps_freshness_buckets():
    route = respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(200, json={"type": "news", "results": []})
    )
    provider = _provider()
    provider.search("a", freshness_days=1)
    provider.search("b", freshness_days=30)
    provider.search("c", freshness_days=365)
    urls = [str(call.request.url) for call in route.calls]
    assert "freshness=pd" in urls[0]
    assert "freshness=pm" in urls[1]
    assert "freshness=py" in urls[2]


def test_provider_attributes():
    p = _provider()
    assert p.name == "brave_news"
    assert p.locale == Locale.EN
