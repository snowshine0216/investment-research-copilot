from __future__ import annotations
import httpx
import pytest
import respx
from irc.llm.retry import classify_failure, FailureKind, NoRetryError, _is_retryable, retry_call_chat, RATE_LIMIT_BACKOFF_SECONDS


def test_classify_429_is_rate_limit():
    resp = httpx.Response(status_code=429)
    assert classify_failure(resp) == FailureKind.RATE_LIMITED


def test_classify_500_is_server_error():
    resp = httpx.Response(status_code=503)
    assert classify_failure(resp) == FailureKind.SERVER_ERROR


def test_classify_401_raises_no_retry():
    resp = httpx.Response(status_code=401)
    with pytest.raises(NoRetryError, match="auth"):
        classify_failure(resp)


def test_classify_400_other_no_retry():
    resp = httpx.Response(status_code=404)
    with pytest.raises(NoRetryError):
        classify_failure(resp)


def test_classify_2xx_returns_ok():
    resp = httpx.Response(status_code=200)
    assert classify_failure(resp) == FailureKind.OK


def test_backoff_constants_are_stepped():
    """All four stepped values must be present and strictly increasing."""
    assert len(RATE_LIMIT_BACKOFF_SECONDS) == 4
    assert list(RATE_LIMIT_BACKOFF_SECONDS) == sorted(RATE_LIMIT_BACKOFF_SECONDS)


# --- _is_retryable ---

def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError(str(code), request=req, response=resp)


def test_is_retryable_429():
    assert _is_retryable(_status_error(429)) is True


def test_is_retryable_503():
    assert _is_retryable(_status_error(503)) is True


def test_is_retryable_401_false():
    assert _is_retryable(_status_error(401)) is False


def test_is_retryable_200_false():
    # Boundary test: httpx only raises HTTPStatusError on 4xx/5xx, never 2xx.
    # This asserts that even if a 200-wrapped error were constructed manually
    # it falls through the OK classification and returns False.
    assert _is_retryable(_status_error(200)) is False


def test_is_retryable_connect_error_true():
    assert _is_retryable(httpx.ConnectError("connection refused")) is True


def test_is_retryable_timeout_true():
    assert _is_retryable(httpx.TimeoutException("timed out")) is True


def test_is_retryable_remote_protocol_error_true():
    assert _is_retryable(httpx.RemoteProtocolError("peer closed connection")) is True


def test_is_retryable_non_http_error_false():
    assert _is_retryable(ValueError("boom")) is False


# --- retry_call_chat ---

@respx.mock
def test_retry_call_chat_success(monkeypatch):
    from irc.llm._types import ResolvedRoute
    from tenacity import wait_none
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    route = ResolvedRoute(
        task="news_summary",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )
    )
    result = retry_call_chat(route, [{"role": "user", "content": "hi"}], wait=wait_none())
    assert result.text == "ok"


@respx.mock
def test_retry_call_chat_retries_on_429(monkeypatch):
    from irc.llm._types import ResolvedRoute
    from tenacity import wait_none
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    route = ResolvedRoute(
        task="news_summary",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )
    # Fail 4 times with 429, succeed on 5th (stop_after_attempt(5) = 4 retries)
    respx.post("https://api.deepseek.com/chat/completions").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "retried"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                },
            ),
        ]
    )
    result = retry_call_chat(route, [{"role": "user", "content": "hi"}], wait=wait_none())
    assert result.text == "retried"
    assert respx.calls.call_count == 5


@respx.mock
def test_retry_call_chat_raises_after_max_attempts(monkeypatch):
    from irc.llm._types import ResolvedRoute
    from tenacity import wait_none
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    route = ResolvedRoute(
        task="news_summary",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(httpx.HTTPStatusError):
        retry_call_chat(route, [{"role": "user", "content": "hi"}], wait=wait_none())
    assert respx.calls.call_count == 5
