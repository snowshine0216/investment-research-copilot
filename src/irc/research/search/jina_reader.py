from __future__ import annotations
import logging
from datetime import datetime, timezone

import httpx

from irc.http_proxy import resolve_proxy
from irc.research.search.types import ExtractedPage


_BASE = "https://r.jina.ai"
_log = logging.getLogger(__name__)


class JinaReader:
    """URL → clean markdown via Jina Reader (r.jina.ai).

    Free tier works without a key. Setting api_key raises rate limits and
    enables paid features. Pure adapter — failures degrade into
    ExtractedPage(failure_reason=...).
    """

    name: str = "jina"

    def __init__(self, api_key: str = "", *, timeout_s: int = 20) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    def _fail(self, *, url: str, now: str, reason: str) -> ExtractedPage:
        _log.warning("jina_reader failed on %s: %s", url, reason)
        return ExtractedPage(
            url=url, title="", markdown="", fetched_at_iso=now, failure_reason=reason,
        )

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            with httpx.Client(
                timeout=timeout_s or self._timeout_s,
                proxy=resolve_proxy(),
            ) as client:
                resp = client.get(f"{_BASE}/{url}", headers=headers)
        except httpx.TimeoutException as exc:
            return self._fail(url=url, now=now, reason=f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return self._fail(url=url, now=now, reason=f"http error: {exc}")
        if resp.status_code != 200:
            return self._fail(url=url, now=now, reason=f"http {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except ValueError as exc:
            return self._fail(url=url, now=now, reason=f"invalid JSON: {exc}")
        data = body.get("data")
        if not isinstance(data, dict):
            return self._fail(url=url, now=now, reason="missing 'data' object in response")
        content = data.get("content", "") or ""
        if not content:
            return self._fail(url=url, now=now, reason="empty content")
        return ExtractedPage(
            url=data.get("url", url) or url,
            title=data.get("title", "") or "",
            markdown=content,
            fetched_at_iso=now,
        )
