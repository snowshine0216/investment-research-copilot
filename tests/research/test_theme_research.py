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
        out, responses, _units = build_theme_reports(
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
    assert len(responses) == 1
    assert responses[0].prompt_tokens == 1


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
        out, _, _units = build_theme_reports(
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
        out, _, _units = build_theme_reports(
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
    llm_responses = [
        RuntimeError("LLM down"),
        ChatResponse(text="ok", prompt_tokens=1, completion_tokens=1, latency_ms=1, raw={}),
    ]
    with patch("irc.research.synthesize.call_chat", side_effect=llm_responses):
        out, collected_responses, _units = build_theme_reports(
            themes=("us_monetary", "us_fiscal_politics"),
            providers=(en,),
            extractor=extractor,
            route=_route(),
        )
    assert len(out) == 2
    assert "LLM down" in out[0].failure_reason
    assert out[1].failure_reason == ""
    assert out[1].report_md == "ok"
    # Only the successful theme produced a ChatResponse
    assert len(collected_responses) == 1


def test_build_records_failure_when_search_returns_no_hits():
    en = _FakeProvider(name="tavily", locale=Locale.EN, hits=())
    extractor = _FakeExtractor()
    with patch("irc.research.synthesize.call_chat") as m:
        out, _, _units = build_theme_reports(
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
        reports, _, _units = build_theme_reports(
            themes=("us_monetary",),
            providers=(failing_provider, ok_provider),
            extractor=extractor,
            route=_route(),
        )

    assert len(reports) == 1
    assert "failing: timeout" in reports[0].provider_failures


# --- Task 6: freshness_days test ---

from dataclasses import dataclass as _dc, field as dc_field


@_dc
class _RecordingProvider:
    name: str = "tavily"
    locale: Locale = None  # type: ignore[assignment]
    seen: list = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        if self.locale is None:
            self.locale = Locale.EN

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple = (),
        **_,
    ) -> SearchResult:
        self.seen.append({"query": query, "freshness_days": freshness_days})
        return SearchResult(query=query, locale=self.locale, provider=self.name)


class _NoopExtractor:
    name = "noop"

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        return ExtractedPage(
            url=url, title="", markdown="x",
            fetched_at_iso="2026-05-15T00:00:00+00:00",
        )


def test_build_theme_reports_passes_freshness_per_theme(monkeypatch):
    from irc.research import theme_research
    from irc.research.theme_research import FRESHNESS_DAYS_BY_THEME, build_theme_reports

    monkeypatch.setattr(
        theme_research, "synthesize_report",
        lambda **kw: (type("R", (), {"report_md": "", "citations": [], "failure_reason": ""})(), None),
    )

    provider = _RecordingProvider()
    build_theme_reports(
        themes=("us_monetary", "gold_drivers"),
        providers=(provider,),
        extractor=_NoopExtractor(),
        route=object(),
    )

    by_query = {call["query"]: call["freshness_days"] for call in provider.seen}
    us_query = "What did the Fed say or do this past week? Cite primary sources."
    gold_query = (
        "Recent moves in real yields, USD, central bank gold purchases, ETF flows; "
        "cite primary sources."
    )
    assert by_query.get(us_query) == 7, f"us_monetary freshness wrong, got: {by_query}"
    assert by_query.get(gold_query) == FRESHNESS_DAYS_BY_THEME["gold_drivers"], (
        f"gold_drivers freshness wrong, got: {by_query}"
    )
