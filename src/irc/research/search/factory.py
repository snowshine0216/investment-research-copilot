from __future__ import annotations

from irc.research.search.bocha_provider import BochaProvider
from irc.research.search.brave_provider import BraveNewsProvider
from irc.research.search.jina_reader import JinaReader
from irc.research.search.tavily_provider import TavilyProvider
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.settings import Settings


def build_providers(settings: Settings) -> tuple[SearchProvider, ...]:
    """Construct one provider per configured API key. Empty tuple if none set."""
    out: list[SearchProvider] = []
    tavily = settings.tavily_api_key.get_secret_value()
    if tavily:
        out.append(TavilyProvider(tavily))
    brave = settings.brave_api_key.get_secret_value()
    if brave:
        out.append(BraveNewsProvider(brave))
    bocha = settings.bocha_api_key.get_secret_value()
    if bocha:
        out.append(BochaProvider(bocha))
    return tuple(out)


def build_extractor(settings: Settings) -> ContentExtractor:
    """JinaReader. The free tier works without a key; api_key only raises throughput."""
    return JinaReader(api_key=settings.jina_api_key.get_secret_value())
