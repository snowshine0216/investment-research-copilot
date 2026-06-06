from __future__ import annotations
from dataclasses import dataclass, field

from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat
from irc.research.search.types import ExtractedPage, SearchHit


_SYSTEM = (
    "You are a careful investment research analyst. "
    "Synthesize a concise markdown report from the numbered sources provided. "
    "Reference sources inline using [n] markers that match the numbering. "
    "Do not invent facts beyond the sources. If sources conflict, say so."
)

_MAX_SOURCES = 12
_SNIPPET_TRUNC = 600


@dataclass(frozen=True)
class Citation:
    index: int
    title: str
    url: str
    published_iso: str = ""


@dataclass(frozen=True)
class ResearchReport:
    report_md: str
    citations: list[Citation] = field(default_factory=list)
    failure_reason: str = ""


def _build_sources(
    hits: tuple[SearchHit, ...],
    pages: tuple[ExtractedPage, ...],
) -> list[Citation]:
    """Index every distinct source URL once, starting at 1.
    Pages (which have full content) are preferred over hits when the URL matches,
    but hit metadata (published_iso) is preserved when present."""
    published_by_url = {h.url: h.published_iso for h in hits if h.url}
    by_url: dict[str, Citation] = {}
    next_index = 1
    for page in pages:
        if not page.url or page.failure_reason or page.url in by_url:
            continue
        by_url[page.url] = Citation(
            index=next_index,
            title=page.title or page.url,
            url=page.url,
            published_iso=published_by_url.get(page.url, ""),
        )
        next_index += 1
    for hit in hits:
        if not hit.url or hit.url in by_url:
            continue
        by_url[hit.url] = Citation(
            index=next_index,
            title=hit.title or hit.url,
            url=hit.url,
            published_iso=hit.published_iso,
        )
        next_index += 1
    return list(by_url.values())[:_MAX_SOURCES]


def _format_prompt(
    query: str,
    hits: tuple[SearchHit, ...],
    pages: tuple[ExtractedPage, ...],
    citations: list[Citation],
) -> str:
    page_by_url = {p.url: p for p in pages if not p.failure_reason}
    hit_by_url = {h.url: h for h in hits}
    blocks: list[str] = []
    for c in citations:
        page = page_by_url.get(c.url)
        if page is not None:
            body = page.markdown[:_SNIPPET_TRUNC]
        else:
            hit = hit_by_url.get(c.url)
            body = (hit.snippet if hit else "")[:_SNIPPET_TRUNC]
        blocks.append(f"[{c.index}] {c.title} ({c.url})\n{body}".strip())
    sources = "\n\n".join(blocks)
    return (
        f"Query: {query}\n\n"
        f"Sources:\n{sources}\n\n"
        "Write a concise markdown report. Cite sources inline as [n]."
    )


def synthesize_report(
    query: str,
    hits: tuple[SearchHit, ...],
    pages: tuple[ExtractedPage, ...],
    *,
    route: ResolvedRoute,
    max_tokens: int = 2000,
) -> tuple[ResearchReport, "ChatResponse | None"]:
    """One LLM call: (query + hits + pages) -> (markdown report, ChatResponse | None).

    Citations are derived from the input source pool (pages preferred, then hits),
    not from LLM output, so they cannot be hallucinated. The LLM only chooses which
    [n] to reference inline. Returns (report, None) when no LLM call was made.
    """
    from irc.llm._types import ChatResponse  # local import to avoid circular at module level
    citations = _build_sources(hits, pages)
    if not citations:
        return ResearchReport(
            report_md="",
            citations=[],
            failure_reason="no sources to synthesize from",
        ), None
    prompt = _format_prompt(query, hits, pages, citations)
    try:
        resp = call_chat(
            route=route,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        return ResearchReport(report_md="", citations=[], failure_reason=str(exc)), None
    return ResearchReport(report_md=resp.text, citations=citations), resp
