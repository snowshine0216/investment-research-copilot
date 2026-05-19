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

import os

_ENV_VAR = "IRC_HTTPS_PROXY"


def resolve_proxy() -> str | None:
    """Return the configured proxy URL, or ``None`` for a direct connection."""
    return os.environ.get(_ENV_VAR, "").strip() or None
