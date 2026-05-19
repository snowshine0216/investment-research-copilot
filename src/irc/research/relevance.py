"""Relevance filter for research citations.

Adversarial review §A1+§A2 (2026-05-19): the holdings_sector query
``用户组合涉及行业的最新新闻和研报要点`` tokenized to ``用户`` + ``研究`` +
``组合``, which matched unrelated industry-report pages on
``chinabgao.com``. A relevance gate compares each citation's title /
summary against keywords derived from the user's actual holdings
(sector codes, fund-house names, asset classes), and rejects sources
whose extracted entities don't intersect.

Pure functions. No I/O.
"""
from __future__ import annotations

from collections.abc import Iterable

from irc.research.synthesize import Citation


def normalize_keywords(raw: Iterable[str]) -> frozenset[str]:
    """Lowercase, strip whitespace, drop empties.

    Keywords are matched case-insensitively against citation text. We do
    NOT tokenize the user input — multi-word phrases like ``central bank
    purchases`` stay as a single match unit so we can target precise
    phrases when needed.
    """
    out: set[str] = set()
    for token in raw:
        if token is None:
            continue
        stripped = str(token).strip().lower()
        if stripped:
            out.add(stripped)
    return frozenset(out)


def _haystack(citation: Citation) -> str:
    return f"{citation.title or ''} {citation.url or ''}".lower()


def source_is_relevant(
    citation: Citation,
    keywords: frozenset[str],
) -> bool:
    """A citation is relevant when its title or URL mentions at least
    one keyword. Empty keywords ⇒ pass-through True (no opinion).

    Case-insensitive substring match on the haystack. The URL is
    included because some sites encode the topic in the path (e.g.
    ``/k/yhyjrj.html``) without putting it in the title.
    """
    if not keywords:
        return True
    text = _haystack(citation)
    return any(kw in text for kw in keywords)


def filter_relevant_citations(
    citations: tuple[Citation, ...],
    keywords: frozenset[str],
) -> tuple[Citation, ...]:
    """Return only citations passing ``source_is_relevant``. Pure."""
    if not keywords:
        return citations
    return tuple(c for c in citations if source_is_relevant(c, keywords))
