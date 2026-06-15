from __future__ import annotations
import pytest
import respx
import httpx
from unittest.mock import patch
from irc.http_proxy import resolve_proxy
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


def test_resolve_proxy_unset_returns_none(monkeypatch):
    monkeypatch.delenv("IRC_HTTPS_PROXY", raising=False)
    assert resolve_proxy() is None


def test_resolve_proxy_empty_returns_none(monkeypatch):
    monkeypatch.setenv("IRC_HTTPS_PROXY", "  ")
    assert resolve_proxy() is None


def test_resolve_proxy_set_returns_url(monkeypatch):
    monkeypatch.setenv("IRC_HTTPS_PROXY", "http://10.27.7.110:8080")
    assert resolve_proxy() == "http://10.27.7.110:8080"


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
    respx.post("https://api.deepseek.com/chat/completions").mock(
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
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(httpx.HTTPStatusError):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)


def test_call_chat_missing_key_raises(route_deepseek, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)


@pytest.fixture
def route_openrouter() -> ResolvedRoute:
    return ResolvedRoute(
        task="memo_synthesis",
        provider="openrouter",
        model="anthropic/claude-opus-4.7",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    )


@respx.mock
def test_call_chat_openrouter_url(route_openrouter, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Synthesis"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )
    )
    resp = call_chat(route_openrouter, messages=[{"role": "user", "content": "hi"}], timeout_s=10)
    assert resp.text == "Synthesis"


@respx.mock
def test_call_chat_with_injected_client(route_deepseek, monkeypatch):
    """Verify the client= branch: a caller-supplied httpx.Client is used directly."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "injected"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )
    )
    # Pass a pre-built client; respx intercepts at the transport level
    with httpx.Client() as shared_client:
        resp = call_chat(
            route_deepseek,
            messages=[{"role": "user", "content": "hi"}],
            timeout_s=10,
            client=shared_client,
        )
    assert resp.text == "injected"


@respx.mock
def test_call_chat_empty_choices_raises(route_deepseek, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [], "usage": {}})
    )
    with pytest.raises(ValueError, match="empty choices"):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)


@respx.mock
def test_call_chat_null_content_raises(route_deepseek, monkeypatch):
    """Null content (e.g., tool-call response) must raise ValueError, not silently return ''."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": None}}], "usage": {}},
        )
    )
    with pytest.raises(ValueError, match="null content"):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)


@patch("irc.llm.http_client.socket.gethostbyname", return_value="169.254.169.254")
def test_post_request_blocks_metadata_resolution(mock_dns):
    from irc.llm.http_client import _post_request, SSRFError
    with pytest.raises(SSRFError):
        _post_request(url="https://attacker.example.com/v1/chat", headers={}, payload={})


# --- Phase D: Task 16 tests ---


def test_resolve_base_url_prefers_literal():
    from irc.llm.http_client import _resolve_base_url
    r = ResolvedRoute(task="t", provider="deepseek", api_key_env="K",
                      base_url="https://api.deepseek.com")
    assert _resolve_base_url(r) == "https://api.deepseek.com"


def test_resolve_base_url_reads_env(monkeypatch):
    from irc.llm.http_client import _resolve_base_url
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    r = ResolvedRoute(task="t", provider="minimax", api_key_env="K",
                      base_url_env="MINIMAX_BASE_URL")
    assert _resolve_base_url(r) == "https://api.minimaxi.com/v1"


def test_env_resolved_url_reruns_ssrf_guard(monkeypatch):
    from irc.llm.http_client import _resolve_base_url, SSRFError
    monkeypatch.setenv("MINIMAX_BASE_URL", "http://169.254.169.254/v1")
    r = ResolvedRoute(task="t", provider="minimax", api_key_env="K",
                      base_url_env="MINIMAX_BASE_URL")
    with pytest.raises((SSRFError, ValueError)):
        _resolve_base_url(r)


def test_resolve_model_reads_default_model_env(monkeypatch):
    from irc.llm.http_client import _resolve_model
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")
    r = ResolvedRoute(task="t", provider="minimax", api_key_env="K",
                      base_url_env="MINIMAX_BASE_URL", default_model_env="MINIMAX_MODEL")
    assert _resolve_model(r) == "MiniMax-Text-01"


def test_resolve_model_missing_env_raises(monkeypatch):
    from irc.llm.http_client import _resolve_model
    monkeypatch.delenv("MINIMAX_MODEL", raising=False)
    r = ResolvedRoute(task="t", provider="minimax", api_key_env="K",
                      base_url_env="MINIMAX_BASE_URL", default_model_env="MINIMAX_MODEL")
    with pytest.raises(RuntimeError, match="MINIMAX_MODEL"):
        _resolve_model(r)
