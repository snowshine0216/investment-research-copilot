from __future__ import annotations
import pytest
import respx
import httpx
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


@pytest.fixture
def route_deepseek() -> ResolvedRoute:
    return ResolvedRoute(
        task="news_summary",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )


@respx.mock
def test_call_chat_happy_path(route_deepseek, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )
    )
    resp = call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=10)
    assert isinstance(resp, ChatResponse)
    assert resp.text == "Hello"
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 5


@respx.mock
def test_call_chat_429_raises(route_deepseek, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/v1/chat/completions").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(httpx.HTTPStatusError):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)


def test_call_chat_missing_key_raises(route_deepseek, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)
