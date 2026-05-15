from __future__ import annotations
from datetime import datetime, timezone

import httpx

from irc.research.search.types import ExtractedPage


_BASE = "https://r.jina.ai"


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

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            resp = httpx.get(
                f"{_BASE}/{url}",
                headers=headers,
                timeout=timeout_s or self._timeout_s,
            )
        except httpx.TimeoutException as exc:
            return ExtractedPage(
                url=url, title="", markdown="", fetched_at_iso=now,
                failure_reason=f"timeout: {exc}",
            )
        except httpx.HTTPError as exc:
            return ExtractedPage(
                url=url, title="", markdown="", fetched_at_iso=now,
                failure_reason=f"http error: {exc}",
            )
        if resp.status_code != 200:
            return ExtractedPage(
                url=url, title="", markdown="", fetched_at_iso=now,
                failure_reason=f"http {resp.status_code}: {resp.text[:200]}",
            )
        try:
            body = resp.json()
        except ValueError as exc:
            return ExtractedPage(
                url=url, title="", markdown="", fetched_at_iso=now,
                failure_reason=f"invalid JSON: {exc}",
            )
        data = body.get("data")
        if not isinstance(data, dict):
            return ExtractedPage(
                url=url, title="", markdown="", fetched_at_iso=now,
                failure_reason="missing 'data' object in response",
            )
        content = data.get("content", "") or ""
        if not content:
            return ExtractedPage(
                url=url, title=data.get("title", "") or "", markdown="",
                fetched_at_iso=now, failure_reason="empty content",
            )
        return ExtractedPage(
            url=data.get("url", url) or url,
            title=data.get("title", "") or "",
            markdown=content,
            fetched_at_iso=now,
        )
