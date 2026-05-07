from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain, wait_fixed

if TYPE_CHECKING:
    from irc.llm._types import ResolvedRoute
    from irc.llm.http_client import ChatResponse
    from tenacity import wait_base


class FailureKind(str, Enum):
    OK = "ok"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"


class NoRetryError(Exception):
    """Failure classes that must not be retried (auth, 4xx other)."""


def classify_failure(response: httpx.Response) -> FailureKind:
    """Pure classification of an HTTP response into retry policy buckets.
    Raises NoRetryError for 4xx that should not be retried."""
    code = response.status_code
    if 200 <= code < 300:
        return FailureKind.OK
    if code == 429:
        return FailureKind.RATE_LIMITED
    if 500 <= code < 600:
        return FailureKind.SERVER_ERROR
    if code in (401, 403):
        raise NoRetryError(f"auth failure {code}; check credentials")
    raise NoRetryError(f"non-retryable {code}")


# Backoff schedule for rate-limit retries (seconds per attempt: 2s, 4s, 8s, 16s).
# All four values are used via wait_chain to produce stepped backoff.
RATE_LIMIT_BACKOFF_SECONDS: tuple[int, ...] = (2, 4, 8, 16)


def _is_retryable(exc: BaseException) -> bool:
    """True for transient failures: 429/5xx HTTP errors and network-level errors."""
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            kind = classify_failure(exc.response)
            return kind in (FailureKind.RATE_LIMITED, FailureKind.SERVER_ERROR)
        except NoRetryError:
            return False
    return False


def retry_call_chat(
    route: ResolvedRoute,
    messages: list[dict[str, str]],
    *,
    wait: wait_base | None = None,
    **kwargs,
) -> ChatResponse:
    """call_chat wrapped with tenacity retry (429/5xx → up to 4 attempts).

    Pass ``wait=wait_none()`` in tests to skip sleeping.
    """
    from irc.llm.http_client import call_chat  # local import avoids module-level cycle
    _wait = wait if wait is not None else wait_chain(*[wait_fixed(s) for s in RATE_LIMIT_BACKOFF_SECONDS])
    _retrying = retry(
        stop=stop_after_attempt(4),
        wait=_wait,
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    return _retrying(call_chat)(route, messages, **kwargs)
