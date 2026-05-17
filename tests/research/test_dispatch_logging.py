from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from irc.research.search.dispatch import provider_results, extract_top_pages
from irc.research.search.types import (
    ContentExtractor, ExtractedPage, Locale, SearchHit, SearchProvider, SearchResult,
)


@dataclass
class _StubProvider:
    name: str = "stub"
    locale: Locale = Locale.ZH

    def search(self, query: str, **_: Any) -> SearchResult:
        return SearchResult(
            query=query, locale=self.locale, provider=self.name,
            failure_reason="http 403: quota exhausted",
        )


def test_provider_results_logs_failure_at_warning(caplog):
    caplog.set_level(logging.WARNING, logger="irc.research.search.dispatch")
    out = provider_results("q", Locale.ZH, (_StubProvider(),))
    assert out[0].failure_reason
    # The failure must be visible to the console even when DEBUG=false.
    messages = [r.getMessage() for r in caplog.records]
    assert any("stub" in m and "403" in m for m in messages), messages


class _StubExtractor:
    name: str = "stub"

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        raise RuntimeError("boom")


def test_extract_top_pages_logs_exceptions_at_warning(caplog):
    caplog.set_level(logging.WARNING, logger="irc.research.search.dispatch")
    hits = (SearchHit(title="t", url="https://x", snippet=""),)
    out = extract_top_pages(hits, _StubExtractor())
    assert out[0].failure_reason.startswith("extractor raised")
    messages = [r.getMessage() for r in caplog.records]
    assert any("https://x" in m and "boom" in m for m in messages), messages
