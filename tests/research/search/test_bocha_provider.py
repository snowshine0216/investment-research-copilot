"""TDD tests for BochaProvider (博查 AI Search).

Bocha API: POST https://api.bochaai.com/v1/web-search with Bearer auth.
Returns nested data.webPages.value[]. freshness uses oneDay/oneWeek/oneMonth/oneYear/noLimit.
"""
from __future__ import annotations
import httpx
import respx

from irc.research.search.bocha_provider import BochaProvider
from irc.research.search.types import Locale, SearchResult


BOCHA_URL = "https://api.bochaai.com/v1/web-search"


def _provider() -> BochaProvider:
    return BochaProvider(api_key="bocha-test-key", timeout_s=5)


@respx.mock
def test_search_happy_path_returns_hits():
    respx.post(BOCHA_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "msg": "success",
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "央行重启逆回购",
                                "url": "https://www.eastmoney.com/news/1",
                                "snippet": "央行今日开展逆回购操作。",
                                "datePublished": "2026-05-13T09:00:00Z",
                                "siteName": "东方财富",
                            },
                            {
                                "name": "半导体行情",
                                "url": "https://xueqiu.com/1",
                                "snippet": "半导体板块走强。",
                            },
                        ]
                    }
                },
            },
        )
    )
    out = _provider().search("央行 半导体", max_results=5)
    assert isinstance(out, SearchResult)
    assert out.failure_reason == ""
    assert out.locale == Locale.ZH
    assert out.provider == "bocha"
    assert len(out.hits) == 2
    assert out.hits[0].title == "央行重启逆回购"
    assert out.hits[0].url == "https://www.eastmoney.com/news/1"
    assert out.hits[0].published_iso == "2026-05-13T09:00:00Z"
    assert out.hits[0].source_domain == "www.eastmoney.com"
    assert out.hits[1].published_iso == ""


@respx.mock
def test_search_5xx_returns_failure_reason():
    respx.post(BOCHA_URL).mock(return_value=httpx.Response(503))
    out = _provider().search("x")
    assert out.hits == ()
    assert "503" in out.failure_reason


@respx.mock
def test_search_app_level_error_code_returns_failure_reason():
    respx.post(BOCHA_URL).mock(
        return_value=httpx.Response(200, json={"code": 401, "msg": "invalid api key"})
    )
    out = _provider().search("x")
    assert out.hits == ()
    assert "401" in out.failure_reason or "invalid api key" in out.failure_reason.lower()


@respx.mock
def test_search_malformed_response_returns_failure_reason():
    respx.post(BOCHA_URL).mock(return_value=httpx.Response(200, json={"code": 200, "msg": "ok"}))
    out = _provider().search("x")
    assert out.hits == ()
    assert out.failure_reason != ""


@respx.mock
def test_search_sends_bearer_token_and_query_payload():
    route = respx.post(BOCHA_URL).mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": {"webPages": {"value": []}}},
        )
    )
    _provider().search("央行", max_results=8, freshness_days=7)
    req = route.calls[0].request
    assert req.headers.get("authorization") == "Bearer bocha-test-key"
    body = req.read().decode()
    assert "央行" in body
    assert '"count": 8' in body or '"count":8' in body
    assert "oneWeek" in body


@respx.mock
def test_search_maps_freshness_buckets():
    route = respx.post(BOCHA_URL).mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": {"webPages": {"value": []}}},
        )
    )
    provider = _provider()
    provider.search("a", freshness_days=1)
    provider.search("b", freshness_days=30)
    provider.search("c", freshness_days=400)
    bodies = [c.request.read().decode() for c in route.calls]
    assert "oneDay" in bodies[0]
    assert "oneMonth" in bodies[1]
    assert "noLimit" in bodies[2]


def test_provider_attributes():
    p = _provider()
    assert p.name == "bocha"
    assert p.locale == Locale.ZH
