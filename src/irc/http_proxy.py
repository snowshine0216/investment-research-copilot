"""Single source of truth for the optional outbound HTTPS proxy.

Set ``IRC_HTTPS_PROXY`` to route geo-restricted HTTPS calls through a
forward proxy. Read sites:

- ``irc.llm.http_client`` — all LLM provider calls (DeepSeek, OpenRouter).
- ``irc.research.search._http`` — search providers (Tavily, Brave, Bocha).
- ``irc.research.search.jina_reader`` — Jina page extractor.
- ``irc.data.akshare_client`` — DXY ingest via EastMoney only; other akshare
  sources stay direct because most of them serve mainland-CN domains where
  a non-CN proxy hurts.

Empty/whitespace value behaves the same as unset → direct connection.
"""
from __future__ import annotations

import contextlib
import os
import threading
from typing import Generator

_ENV_VAR = "IRC_HTTPS_PROXY"

# Shared lock for callers that mutate the process-global proxy env via
# `proxy_env` (below). `proxy_env` itself does not lock — env mutation +
# restore is not atomic across threads, so any call site that could run
# concurrently with another proxy_env user must hold this lock around the
# `with proxy_env(...):` block. Single source of truth (was duplicated as
# akshare_client._AKSHARE_PROXY_LOCK).
AKSHARE_PROXY_LOCK = threading.Lock()


def resolve_proxy() -> str | None:
    """Return the configured proxy URL, or ``None`` for a direct connection."""
    return os.environ.get(_ENV_VAR, "").strip() or None


_CN_ENV_VAR = "IRC_CN_PROXY"
_CN_MODE_VAR = "IRC_CN_PROXY_MODE"


def resolve_cn_proxy() -> str | None:
    """CN-egress proxy for the EastMoney data plane, or None.

    Opposite direction from ``resolve_proxy`` (IRC_HTTPS_PROXY routes non-CN
    destinations); the two never mix. Accepts a URL or a bare ``host:port``
    (normalized to ``http://host:port``). ``IRC_CN_PROXY_MODE=off`` disables
    even when the URL is set; default mode is ``on`` when the URL is present.
    """
    if os.environ.get(_CN_MODE_VAR, "on").strip().lower() == "off":
        return None
    raw = os.environ.get(_CN_ENV_VAR, "").strip()
    if not raw:
        return None
    return raw if "://" in raw else "http://" + raw


@contextlib.contextmanager
def proxy_env(proxy_url: str | None) -> Generator[None, None, None]:
    """Temporarily inject HTTP/HTTPS proxy env vars so requests-based libs
    (akshare, urllib) route through the proxy. Restores originals on exit.
    Single source of truth (was duplicated in akshare_client._proxy_env).
    Passing ``None`` is a no-op (no env mutation, nothing to restore)."""
    if proxy_url is None:
        yield
        return
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ[k] = proxy_url
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
