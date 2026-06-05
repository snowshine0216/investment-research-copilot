from __future__ import annotations
from typing import Any, Protocol
from urllib.parse import urlparse
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed
from irc.http_proxy import resolve_proxy
from irc.llm.http_client import verify_host_resolves_publicly
from irc.spend.types import BalanceReading


class ProbeError(RuntimeError):
    """Probe failed after retries (network, 5xx, auth, or bad JSON)."""


class BalanceProbe(Protocol):
    provider: str
    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading: ...


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or 500 <= exc.response.status_code < 600
    return False


def get_json_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    timeout_s: float = 15.0,
    client: httpx.Client | None = None,
    attempts: int = 3,
    wait_seconds: float = 2.0,
) -> dict[str, Any]:
    """SSRF-guarded, proxy-aware GET with bounded retry. Raises ProbeError on any
    persistent failure so the caller can degrade to a warn-and-proceed reading.

    The SSRF DNS guard runs only on the production path (``client is None``).
    An injected client is a test seam backed by a MockTransport that performs no
    real network I/O, so resolving the host would add a non-deterministic DNS
    dependency to otherwise-hermetic unit tests for no security benefit.
    """
    parsed = urlparse(url)
    if client is None and parsed.hostname:
        verify_host_resolves_publicly(parsed.hostname)

    @retry(retry=retry_if_exception(_retryable),
           stop=stop_after_attempt(attempts), wait=wait_fixed(wait_seconds), reraise=True)
    def _do() -> dict[str, Any]:
        owned = client is None
        cli = client or httpx.Client(timeout=timeout_s, proxy=resolve_proxy())
        try:
            resp = cli.get(url, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            return resp.json()
        finally:
            if owned:
                cli.close()

    try:
        return _do()
    except Exception as exc:  # noqa: BLE001 — normalize every failure to ProbeError
        raise ProbeError(f"probe GET {url} failed: {exc}") from exc
