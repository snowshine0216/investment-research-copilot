"""TDD tests for the rewritten theme_research module.

Composes multi_provider_search + extract_top_pages + synthesize_report.
All adapters are injected so tests run without HTTP or LLM calls.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from unittest.mock import patch

from irc.llm._types import ResolvedRoute, ChatResponse
from irc.research.search.types import (
    ExtractedPage,
    Locale,
    SearchHit,
    SearchResult,
)
from irc.research.theme_research import (
    ThemeReport,
    build_theme_reports,
    theme_locale,
)
from irc.research.synthesize import Citation


@dataclass
class _FakeProvider:
    name: str
    locale: Locale
    hits: tuple[SearchHit, ...] = ()
    failure: str = ""

    def search(self, query: str, **_) -> SearchResult:
        if self.failure:
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason=self.failure,
            )
        return SearchResult(
            query=query, locale=self.locale, hits=self.hits, provider=self.name,
        )


@dataclass
class _FakeExtractor:
    name: str = "fake"
    md_by_url: dict[str, str] = field(default_factory=dict)

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        return ExtractedPage(
            url=url, title=f"T-{url}",
            markdown=self.md_by_url.get(url, ""),
            fetched_at_iso="2026-05-15T00:00:00Z",
        )


def _route() -> ResolvedRoute:
    return ResolvedRoute(
        task="research_synth", provider="deepseek", model="deepseek-chat",
        base_url="https://api.deepseek.com/v1", api_key_env="DEEPSEEK_API_KEY",
    )


def _hit(url: str) -> SearchHit:
    return SearchHit(title=f"t-{url}", url=url, snippet="snip", published_iso="2026-05-12")


# theme_locale ---------------------------------------------------------------

def test_theme_locale_maps_us_themes_to_en():
    assert theme_locale("us_monetary") == Locale.EN
    assert theme_locale("us_fiscal_politics") == Locale.EN


def test_theme_locale_maps_cn_themes_to_zh():
    assert theme_locale("cn_monetary") == Locale.ZH
    assert theme_locale("cn_equity_property_policy") == Locale.ZH


def test_theme_locale_unknown_theme_defaults_to_en():
    # Conservative default: unknown themes use English so they still get coverage
    # from Tavily/Brave even if not explicitly registered.
    assert theme_locale("totally_new_theme") == Locale.EN


# build_theme_reports --------------------------------------------------------

def test_build_one_theme_produces_one_report_with_citations():
    en_provider = _FakeProvider(
        name="tavily", locale=Locale.EN,
        hits=(_hit("https://reuters.com/1"),),
    )
    extractor = _FakeExtractor(md_by_url={"https://reuters.com/1": "content 1"})
    with patch(
        "irc.research.synthesize.call_chat",
        return_value=ChatResponse(text="body [1]", prompt_tokens=1, completion_tokens=1, latency_ms=1, raw={}),
    ):
        out = build_theme_reports(
            themes=("us_monetary",),
            providers=(en_provider,),
            extractor=extractor,
            route=_route(),
        )
    assert len(out) == 1
    report = out[0]
    assert isinstance(report, ThemeReport)
    assert report.theme == "us_monetary"
    assert report.locale == "en"
    assert report.report_md == "body [1]"
    assert report.failure_reason == ""
    assert len(report.citations) == 1
    assert report.citations[0] == Citation(
        index=1,
        title="T-https://reuters.com/1",
        url="https://reuters.com/1",
        published_iso="2026-05-12",
    )


def test_build_routes_zh_theme_to_zh_provider():
    zh_provider = _FakeProvider(
        name="bocha", locale=Locale.ZH,
        hits=(_hit("https://eastmoney.com/1"),),
    )
    en_provider = _FakeProvider(name="tavily", locale=Locale.EN, hits=())
    extractor = _FakeExtractor(md_by_url={"https://eastmoney.com/1": "content"})
    with patch(
        "irc.research.synthesize.call_chat",
        return_value=ChatResponse(text="zh body", prompt_tokens=1, completion_tokens=1, latency_ms=1, raw={}),
    ):
        out = build_theme_reports(
            themes=("cn_monetary",),
            providers=(en_provider, zh_provider),
            extractor=extractor,
            route=_route(),
        )
    assert out[0].locale == "zh"
    assert out[0].citations[0].url == "https://eastmoney.com/1"


def test_build_returns_failure_when_no_provider_for_locale():
    en_only = _FakeProvider(name="tavily", locale=Locale.EN, hits=())
    extractor = _FakeExtractor()
    with patch("irc.research.synthesize.call_chat") as m:
        out = build_theme_reports(
            themes=("cn_monetary",),
            providers=(en_only,),
            extractor=extractor,
            route=_route(),
        )
    assert m.call_count == 0
    assert out[0].report_md == ""
    assert "zh" in out[0].failure_reason.lower()


def test_build_records_synth_failure_per_theme_without_aborting_others():
    en = _FakeProvider(
        name="tavily", locale=Locale.EN,
        hits=(_hit("https://reuters.com/1"),),
    )
    extractor = _FakeExtractor(md_by_url={"https://reuters.com/1": "x"})
    # First theme: LLM raises. Second theme: succeeds. Both should appear in output.
    responses = [
        RuntimeError("LLM down"),
        ChatResponse(text="ok", prompt_tokens=1, completion_tokens=1, latency_ms=1, raw={}),
    ]
    with patch("irc.research.synthesize.call_chat", side_effect=responses):
        out = build_theme_reports(
            themes=("us_monetary", "us_fiscal_politics"),
            providers=(en,),
            extractor=extractor,
            route=_route(),
        )
    assert len(out) == 2
    assert "LLM down" in out[0].failure_reason
    assert out[1].failure_reason == ""
    assert out[1].report_md == "ok"


def test_build_records_failure_when_search_returns_no_hits():
    en = _FakeProvider(name="tavily", locale=Locale.EN, hits=())
    extractor = _FakeExtractor()
    with patch("irc.research.synthesize.call_chat") as m:
        out = build_theme_reports(
            themes=("us_monetary",),
            providers=(en,),
            extractor=extractor,
            route=_route(),
        )
    assert m.call_count == 0
    assert "no sources" in out[0].failure_reason.lower()


def test_build_theme_reports_captures_provider_failures():
    """Provider failures are captured in provider_failures field."""
    failing_provider = _FakeProvider(name="failing", locale=Locale.EN, failure="timeout")
    ok_provider = _FakeProvider(name="ok", locale=Locale.EN, hits=(_hit("https://x"),))
    extractor = _FakeExtractor(md_by_url={"https://x": "content"})

    with patch(
        "irc.research.synthesize.call_chat",
        return_value=ChatResponse(text="body", prompt_tokens=1, completion_tokens=1, latency_ms=1, raw={}),
    ):
        reports = build_theme_reports(
            themes=("us_monetary",),
            providers=(failing_provider, ok_provider),
            extractor=extractor,
            route=_route(),
        )

    assert len(reports) == 1
    assert "failing: timeout" in reports[0].provider_failures
