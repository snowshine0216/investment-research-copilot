from __future__ import annotations
from enum import Enum
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed


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


# Backoff schedules, exposed as data so caller can compose them.
RATE_LIMIT_BACKOFF_SECONDS: tuple[int, ...] = (2, 4, 8, 16)
SERVER_ERROR_BACKOFF_SECONDS: tuple[int, ...] = (1, 3, 9)


def _is_retryable(exc: BaseException) -> bool:
    """True for 429 and 5xx HTTP errors; False for auth errors and non-HTTP failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            kind = classify_failure(exc.response)
            return kind in (FailureKind.RATE_LIMITED, FailureKind.SERVER_ERROR)
        except NoRetryError:
            return False
    return False


def retry_call_chat(route, messages, *, wait=None, **kwargs):
    """call_chat wrapped with tenacity retry (429/5xx → up to 4 attempts).

    Pass ``wait=wait_none()`` in tests to skip sleeping.
    """
    from irc.llm.http_client import call_chat  # local import avoids module-level cycle
    _wait = wait if wait is not None else wait_fixed(RATE_LIMIT_BACKOFF_SECONDS[0])
    _retrying = retry(
        stop=stop_after_attempt(4),
        wait=_wait,
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    return _retrying(call_chat)(route, messages, **kwargs)
