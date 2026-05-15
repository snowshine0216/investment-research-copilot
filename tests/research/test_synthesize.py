"""TDD tests for irc.research.synthesize.

Coverage:
- happy path produces report_md + citations indexed against the source pool
- empty source pool returns a failure_reason without calling the LLM
- LLM transport failure returns a failure_reason
"""
from __future__ import annotations
from unittest.mock import patch

from irc.llm._types import ResolvedRoute, ChatResponse
from irc.research.search.types import ExtractedPage, SearchHit
from irc.research.synthesize import (
    Citation,
    ResearchReport,
    synthesize_report,
)


def _route() -> ResolvedRoute:
    return ResolvedRoute(
        task="research_synth",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )


def _chat(text: str) -> ChatResponse:
    return ChatResponse(text=text, prompt_tokens=100, completion_tokens=50, latency_ms=200, raw={})


def _hits() -> tuple[SearchHit, ...]:
    return (
        SearchHit(
            title="Fed holds rates",
            url="https://reuters.com/fed-1",
            snippet="The Fed held rates at the May meeting.",
            published_iso="2026-05-08",
        ),
        SearchHit(
            title="CPI cools",
            url="https://wsj.com/cpi-1",
            snippet="April CPI came in at 2.9% YoY.",
            published_iso="2026-05-12",
        ),
    )


def _pages() -> tuple[ExtractedPage, ...]:
    return (
        ExtractedPage(
            url="https://reuters.com/fed-1",
            title="Fed holds rates",
            markdown="# Fed holds\nThe Fed kept rates at 4.25–4.50%.",
            fetched_at_iso="2026-05-15T01:00:00Z",
        ),
    )


def test_synthesize_happy_path_returns_report_and_citations():
    """LLM markdown + the source pool we passed in produce a ResearchReport
    whose citations are indexed by source order."""
    with patch(
        "irc.research.synthesize.call_chat",
        return_value=_chat("The Fed held rates [1]. CPI cooled to 2.9% [2]."),
    ) as m:
        report = synthesize_report(
            query="What did the Fed do this week?",
            hits=_hits(),
            pages=_pages(),
            route=_route(),
        )
    assert m.called
    assert isinstance(report, ResearchReport)
    assert report.failure_reason == ""
    assert "Fed held rates" in report.report_md
    assert len(report.citations) >= 2
    assert report.citations[0] == Citation(
        index=1,
        title="Fed holds rates",
        url="https://reuters.com/fed-1",
        published_iso="2026-05-08",
    )
    assert report.citations[1].url == "https://wsj.com/cpi-1"


def test_synthesize_empty_sources_returns_failure_reason_without_calling_llm():
    with patch("irc.research.synthesize.call_chat") as m:
        report = synthesize_report(
            query="any",
            hits=(),
            pages=(),
            route=_route(),
        )
    assert not m.called
    assert report.report_md == ""
    assert report.citations == []
    assert "no sources" in report.failure_reason.lower()


def test_synthesize_llm_failure_returns_failure_reason():
    with patch(
        "irc.research.synthesize.call_chat",
        side_effect=RuntimeError("connection reset"),
    ):
        report = synthesize_report(
            query="anything",
            hits=_hits(),
            pages=(),
            route=_route(),
        )
    assert report.report_md == ""
    assert "connection reset" in report.failure_reason
