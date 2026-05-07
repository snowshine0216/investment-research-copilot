from __future__ import annotations
import httpx
import pytest
from irc.llm.retry import classify_failure, FailureKind, NoRetryError


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


def test_backoff_constants_are_non_empty():
    from irc.llm.retry import RATE_LIMIT_BACKOFF_SECONDS, SERVER_ERROR_BACKOFF_SECONDS
    assert len(RATE_LIMIT_BACKOFF_SECONDS) > 0
    assert len(SERVER_ERROR_BACKOFF_SECONDS) > 0
