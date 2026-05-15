"""TDD tests for TavilyProvider.

Covers: happy path, HTTP 5xx, timeout, malformed response, parameter passthrough.
HTTP layer mocked with respx so no network calls.
"""
from __future__ import annotations
import httpx
import pytest
import respx

from irc.research.search.tavily_provider import TavilyProvider
from irc.research.search.types import Locale, SearchResult


TAVILY_URL = "https://api.tavily.com/search"


def _provider() -> TavilyProvider:
    return TavilyProvider(api_key="tvly-test-key", timeout_s=5)


@respx.mock
def test_search_happy_path_returns_hits():
    respx.post(TAVILY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "query": "Fed rates",
                "results": [
                    {
                        "title": "Fed holds rates",
                        "url": "https://reuters.com/fed-1",
                        "content": "The Fed kept rates at 4.25–4.50%.",
                        "published_date": "2026-05-08T12:00:00Z",
                        "score": 0.99,
                    },
                    {
                        "title": "Markets react",
                        "url": "https://wsj.com/markets-1",
                        "content": "Stocks edged higher after the decision.",
                        "score": 0.87,
                    },
                ],
            },
        )
    )
    out = _provider().search("Fed rates", max_results=5)
    assert isinstance(out, SearchResult)
    assert out.failure_reason == ""
    assert out.locale == Locale.EN
    assert out.provider == "tavily"
    assert len(out.hits) == 2
    assert out.hits[0].title == "Fed holds rates"
    assert out.hits[0].url == "https://reuters.com/fed-1"
    assert out.hits[0].published_iso == "2026-05-08T12:00:00Z"
    assert out.hits[0].source_domain == "reuters.com"
    assert out.hits[1].published_iso == ""


@respx.mock
def test_search_http_5xx_returns_failure_reason():
    respx.post(TAVILY_URL).mock(return_value=httpx.Response(503, text="upstream timeout"))
    out = _provider().search("anything")
    assert out.hits == ()
    assert "503" in out.failure_reason


@respx.mock
def test_search_timeout_returns_failure_reason():
    respx.post(TAVILY_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    out = _provider().search("anything")
    assert out.hits == ()
    assert "timeout" in out.failure_reason.lower() or "slow" in out.failure_reason.lower()


@respx.mock
def test_search_malformed_response_returns_failure_reason():
    respx.post(TAVILY_URL).mock(
        return_value=httpx.Response(200, json={"query": "x", "no_results_key": True})
    )
    out = _provider().search("x")
    assert out.hits == ()
    assert out.failure_reason != ""


@respx.mock
def test_search_passes_through_filters_and_freshness():
    route = respx.post(TAVILY_URL).mock(
        return_value=httpx.Response(200, json={"query": "x", "results": []})
    )
    _provider().search(
        "x",
        max_results=7,
        freshness_days=14,
        include_domains=("reuters.com",),
        exclude_domains=("example.spam",),
    )
    assert route.called
    body = route.calls[0].request.read().decode()
    assert '"max_results": 7' in body or '"max_results":7' in body
    assert "reuters.com" in body
    assert "example.spam" in body
    # freshness_days maps to Tavily's "days" parameter
    assert '"days": 14' in body or '"days":14' in body


@respx.mock
def test_search_uses_bearer_authorization_header():
    route = respx.post(TAVILY_URL).mock(
        return_value=httpx.Response(200, json={"query": "x", "results": []})
    )
    _provider().search("x")
    assert route.calls[0].request.headers.get("authorization") == "Bearer tvly-test-key"


def test_provider_attributes():
    p = _provider()
    assert p.name == "tavily"
    assert p.locale == Locale.EN
