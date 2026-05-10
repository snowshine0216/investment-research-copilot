from __future__ import annotations
import json
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


def test_classify_403_raises_no_retry():
    resp = httpx.Response(status_code=403)
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


@respx.mock
def test_retry_call_chat_forwards_explicit_params(monkeypatch):
    """Verify temperature and max_tokens are forwarded through retry_call_chat to the HTTP payload."""
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
    captured: list[dict] = []

    def _capture(request):  # respx callback: only request needed
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "forwarded"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=_capture)
    result = retry_call_chat(
        route,
        [{"role": "user", "content": "hi"}],
        wait=wait_none(),
        temperature=0.1,
        max_tokens=10,
    )
    assert result.text == "forwarded"
    assert captured[0]["temperature"] == pytest.approx(0.1)
    assert captured[0]["max_tokens"] == 10


import time
from unittest.mock import patch
import pytest
from irc.llm.retry import retry_call_chat, AggregateTimeoutError


def test_retry_aggregates_to_deadline():
    def slow(*a, **kw):
        time.sleep(0.6)
        raise ConnectionError("boom")
    with patch("irc.llm.retry._call_once", side_effect=slow):
        with pytest.raises(AggregateTimeoutError):
            retry_call_chat(route=None, messages=[], deadline_s=1.0, attempts=10)


import irc.llm.retry as retry_mod


def test_retry_decorator_built_at_import_time():
    # decorator is bound at module load — not rebuilt per call
    assert hasattr(retry_mod, "_RETRY_DECORATOR")
    fn = retry_mod._RETRY_DECORATOR
    assert callable(fn)
