from __future__ import annotations
from enum import Enum
import httpx


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
