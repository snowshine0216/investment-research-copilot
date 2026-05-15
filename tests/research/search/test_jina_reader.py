"""TDD tests for JinaReader (r.jina.ai URL → markdown converter).

JSON mode: GET https://r.jina.ai/<url> with Accept: application/json.
Auth optional — free tier works without a key.
"""
from __future__ import annotations
import httpx
import respx

from irc.research.search.jina_reader import JinaReader
from irc.research.search.types import ExtractedPage


def _jina_url(url: str) -> str:
    return f"https://r.jina.ai/{url}"


@respx.mock
def test_extract_happy_path_returns_markdown():
    target = "https://reuters.com/fed-1"
    respx.get(_jina_url(target)).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "status": 20000,
                "data": {
                    "title": "Fed holds rates",
                    "url": target,
                    "content": "# Fed holds\n\nThe Fed kept rates at 4.25–4.50%.",
                },
            },
        )
    )
    reader = JinaReader()
    page = reader.extract(target)
    assert isinstance(page, ExtractedPage)
    assert page.failure_reason == ""
    assert page.url == target
    assert page.title == "Fed holds rates"
    assert "kept rates" in page.markdown
    assert page.fetched_at_iso != ""


@respx.mock
def test_extract_5xx_returns_failure_reason():
    target = "https://example.com/x"
    respx.get(_jina_url(target)).mock(return_value=httpx.Response(503))
    page = JinaReader().extract(target)
    assert page.markdown == ""
    assert "503" in page.failure_reason


@respx.mock
def test_extract_timeout_returns_failure_reason():
    target = "https://example.com/x"
    respx.get(_jina_url(target)).mock(side_effect=httpx.ConnectTimeout("slow"))
    page = JinaReader().extract(target)
    assert page.markdown == ""
    assert page.failure_reason != ""


@respx.mock
def test_extract_malformed_response_returns_failure_reason():
    target = "https://example.com/x"
    respx.get(_jina_url(target)).mock(
        return_value=httpx.Response(200, json={"code": 200, "no_data": True})
    )
    page = JinaReader().extract(target)
    assert page.markdown == ""
    assert page.failure_reason != ""


@respx.mock
def test_extract_without_api_key_omits_authorization_header():
    target = "https://example.com/x"
    route = respx.get(_jina_url(target)).mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": {"title": "t", "url": target, "content": "c"}},
        )
    )
    JinaReader().extract(target)
    assert "authorization" not in {h.lower() for h in route.calls[0].request.headers.keys()}


@respx.mock
def test_extract_with_api_key_sends_bearer_authorization():
    target = "https://example.com/x"
    route = respx.get(_jina_url(target)).mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": {"title": "t", "url": target, "content": "c"}},
        )
    )
    JinaReader(api_key="jina-test-key").extract(target)
    assert route.calls[0].request.headers.get("authorization") == "Bearer jina-test-key"


def test_reader_name():
    assert JinaReader().name == "jina"
