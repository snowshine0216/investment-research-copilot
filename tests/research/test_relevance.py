"""Relevance filter for research citations (item 001, 2026-05-19)."""
from __future__ import annotations

import pytest

from irc.research.relevance import (
    filter_relevant_citations,
    normalize_keywords,
    source_is_relevant,
)
from irc.research.synthesize import Citation


def _c(title: str, url: str = "https://example.com/x", published: str = "2026-05-19") -> Citation:
    return Citation(index=1, title=title, url=url, published_iso=published)


def test_normalize_keywords_strips_and_lowercases() -> None:
    out = normalize_keywords([" Gold ", "S&P 500", "", None, "黄金"])
    assert "gold" in out
    assert "s&p 500" in out
    assert "黄金" in out
    assert "" not in out


def test_source_is_relevant_passes_when_keyword_in_title() -> None:
    c = _c("Central banks scoop up a load of gold in Q1")
    assert source_is_relevant(c, frozenset({"gold"}))


def test_source_is_relevant_case_insensitive() -> None:
    c = _c("S&P 500 closes at record high")
    assert source_is_relevant(c, frozenset({"s&p 500"}))


def test_source_is_relevant_matches_url_path() -> None:
    c = _c("Some unrelated title",
           url="https://www.cnbc.com/2026/05/13/us-treasury-yields-investors.html")
    assert source_is_relevant(c, frozenset({"yields"}))


def test_source_is_relevant_fails_when_no_match() -> None:
    c = _c("2026 用户研究软件行业分析报告")
    assert not source_is_relevant(c, frozenset({"gold", "黄金"}))


def test_source_is_relevant_empty_keywords_passes() -> None:
    c = _c("anything")
    assert source_is_relevant(c, frozenset())


def test_filter_relevant_citations_drops_unmatched() -> None:
    cites = (
        _c("Central banks gold purchases"),
        _c("用户研究软件分析报告"),
        _c("S&P 500 closes at record"),
    )
    kept = filter_relevant_citations(cites, frozenset({"gold", "s&p 500"}))
    assert len(kept) == 2
    assert all("用户研究软件" not in c.title for c in kept)


def test_filter_relevant_citations_empty_keywords_passes_through() -> None:
    cites = (_c("anything"), _c("other"))
    assert filter_relevant_citations(cites, frozenset()) == cites
