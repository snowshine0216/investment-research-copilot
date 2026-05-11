from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
import time
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain, wait_fixed

if TYPE_CHECKING:
    from irc.llm._types import ResolvedRoute
    from irc.llm.http_client import ChatResponse
    from tenacity import wait_base


class AggregateTimeoutError(TimeoutError):
    """Raised when total wall time across all retry attempts exceeds deadline_s."""


class FailureKind(str, Enum):
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"


class NoRetryError(Exception):
    """Failure classes that must not be retried (auth, 4xx other)."""


def classify_failure(response: httpx.Response) -> FailureKind:
    """Pure classification of an HTTP response into retry policy buckets.
    Raises NoRetryError for 4xx that should not be retried.
    Only called for error responses (4xx/5xx); never called for 2xx success."""
    code = response.status_code
    if code == 429:
        return FailureKind.RATE_LIMITED
    if 500 <= code < 600:
        return FailureKind.SERVER_ERROR
    if code in (401, 403):
        raise NoRetryError(f"auth failure {code}; check credentials")
    raise NoRetryError(f"non-retryable {code}")


# Backoff schedule for rate-limit retries (seconds per attempt: 2s, 4s, 8s, 16s).
# stop_after_attempt(5) allows 4 retries → 4 wait steps, consuming all four values.
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


def _is_deadline_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return isinstance(exc, httpx.HTTPError) and _is_retryable(exc)


_RETRY_DECORATOR = retry(
    stop=stop_after_attempt(5),
    wait=wait_chain(*[wait_fixed(s) for s in RATE_LIMIT_BACKOFF_SECONDS]),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def _call_once(
    route: ResolvedRoute,
    messages: list[dict[str, str]],
    *,
    wait: wait_base | None = None,
    timeout_s: float = 30.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
    client: httpx.Client | None = None,
) -> ChatResponse:
    """Single attempt: call_chat wrapped with tenacity for 429/5xx/network errors."""
    from irc.llm.http_client import call_chat  # local import avoids module-level cycle
    if wait is not None:
        # Use custom wait if provided (e.g., for testing with wait_none())
        _retrying = retry(
            stop=stop_after_attempt(5),
            wait=wait,
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
    else:
        # Use module-level decorator with default backoff
        _retrying = _RETRY_DECORATOR
    return _retrying(call_chat)(
        route, messages,
        timeout_s=timeout_s,
        temperature=temperature,
        max_tokens=max_tokens,
        client=client,
    )


def retry_call_chat(
    route: ResolvedRoute,
    messages: list[dict[str, str]],
    *,
    wait: wait_base | None = None,
    timeout_s: float = 30.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
    client: httpx.Client | None = None,
    deadline_s: float = 60.0,
    attempts: int = 5,
) -> ChatResponse:
    """call_chat wrapped with tenacity retry (429/5xx/network errors → up to 5 attempts).

    ``deadline_s`` caps total wall time; ``AggregateTimeoutError`` is raised if exceeded.
    Pass ``wait=wait_none()`` in tests to skip sleeping.
    """
    started = time.monotonic()
    last_err: Exception | None = None
    kw = dict(
        wait=wait, timeout_s=timeout_s, temperature=temperature,
        max_tokens=max_tokens, client=client,
    )
    for i in range(attempts):
        if time.monotonic() - started >= deadline_s:
            raise AggregateTimeoutError(
                f"deadline {deadline_s}s exceeded after {i} attempts"
            )
        try:
            return _call_once(route, messages, **kw)
        except (ConnectionError, TimeoutError, httpx.HTTPError) as exc:
            if not _is_deadline_retryable(exc):
                raise
            last_err = exc
            elapsed = time.monotonic() - started
            if elapsed >= deadline_s:
                raise AggregateTimeoutError(
                    f"deadline {deadline_s}s exceeded after {i + 1} attempts"
                ) from exc
            if isinstance(exc, httpx.HTTPError):
                raise
            sleep_s = min(2 ** i, max(0.0, deadline_s - elapsed))
            if sleep_s > 0:
                time.sleep(sleep_s)
    raise last_err if last_err else AggregateTimeoutError("no attempts ran")
