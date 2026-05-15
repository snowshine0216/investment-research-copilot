# Research Adapter Signatures

## Purpose

Replace the single LDR (Local Deep Research) integration with a pluggable, fast research stack that the opportunity-thesis-discipline layer can rely on. LDR is removed entirely.

This document fixes the **interfaces only**. Implementation lives behind these signatures.

Two layers are introduced:

1. `src/irc/research/search/` — pluggable web search + URL→markdown extractors.
2. `src/irc/fundamentals/` — structured constituent-level fetchers (filings, broker reports, holdings).

The opportunity layer's `thesis_state` and `valuation_state` classifiers consume both.

## Design Constraints

- Pure functions wherever possible. I/O (HTTP calls) is isolated to provider adapters.
- All adapters return dataclasses with a `failure_reason` field instead of raising — failure degrades evidence rather than crashing the pipeline.
- Provider selection is by `Locale` (English vs Mainland Chinese themes). The two locales use disjoint provider sets because Tavily/Brave underweight Chinese sources and Bocha underweights English sources.
- All search responses normalize to one shape (`SearchHit`) so downstream synthesis is provider-agnostic.
- Synthesis (search results → markdown report) is one bounded LLM call, not an agent loop. Wall-clock target ≤30 s per theme.

## Module Layout

```text
src/irc/research/
├── __init__.py
├── search/
│   ├── __init__.py
│   ├── types.py             # Protocol + dataclasses, no I/O
│   ├── tavily_provider.py   # EN search
│   ├── brave_provider.py    # EN news
│   ├── bocha_provider.py    # ZH search
│   ├── jina_reader.py       # URL → markdown
│   └── dispatch.py          # Locale-aware fan-out
├── synthesize.py            # search hits + extracted pages -> report_md
├── theme_research.py        # rewrite of the LDR caller
└── falsification.py         # unchanged

src/irc/fundamentals/         # new
├── __init__.py
├── types.py                  # ConstituentSnapshot, FilingDigest, BrokerReport
├── akshare_fundamentals.py  # CN holdings / filings / broker reports
├── edgar_client.py           # US 10-K / 10-Q via SEC EDGAR JSON
├── hkex_client.py            # HK disclosure
└── snapshot.py               # roll-up + on-disk cache
```

`src/irc/research/ldr_client.py` and its tests are removed. `LDRResearchResult` / `LDRCitation` are replaced by `ResearchReport` / `Citation` defined below.

## Search Layer Signatures

### `src/irc/research/search/types.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Locale(str, Enum):
    """Picks the right provider set for a theme's language / source ecosystem."""
    EN = "en"   # US / HK QDII themes, global macro, Fed / SEC primary sources
    ZH = "zh"   # Mainland China themes: eastmoney, xueqiu, cls, wallstreetcn, gov.cn


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    published_iso: str = ""    # ISO 8601 if known; empty otherwise
    source_domain: str = ""    # for include/exclude filtering


@dataclass(frozen=True)
class SearchResult:
    """One provider's response to one query. Provider-agnostic shape."""
    query: str
    locale: Locale
    hits: tuple[SearchHit, ...] = ()
    provider: str = ""           # "tavily" | "brave_news" | "bocha"
    failure_reason: str = ""     # empty on success


@dataclass(frozen=True)
class ExtractedPage:
    """One URL converted to LLM-ready markdown."""
    url: str
    title: str
    markdown: str
    fetched_at_iso: str
    failure_reason: str = ""


class SearchProvider(Protocol):
    """One adapter per (locale × kind). All adapters share this contract."""

    name: str
    locale: Locale

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult: ...


class ContentExtractor(Protocol):
    """URL → markdown converter (e.g., Jina Reader)."""

    name: str

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage: ...
```

### `src/irc/research/search/tavily_provider.py`

```python
from irc.research.search.types import Locale, SearchProvider, SearchResult


class TavilyProvider:
    """English search via Tavily (https://api.tavily.com/search).

    Config: settings.tavily_api_key. Pure adapter — no caching.
    Strong on US / EU / HK sources, weak on Mainland CN — do not use for ZH themes.
    """
    name: str = "tavily"
    locale: Locale = Locale.EN

    def __init__(self, api_key: str, *, timeout_s: int = 15) -> None: ...

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult: ...
```

### `src/irc/research/search/brave_provider.py`

```python
from irc.research.search.types import Locale, SearchProvider, SearchResult


class BraveNewsProvider:
    """English news via Brave Search News API
    (https://api.search.brave.com/res/v1/news/search).

    Config: settings.brave_api_key. Independent index, good complement to Tavily for
    breaking news and freshness filtering.
    """
    name: str = "brave_news"
    locale: Locale = Locale.EN

    def __init__(self, api_key: str, *, timeout_s: int = 10) -> None: ...

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult: ...
```

### `src/irc/research/search/bocha_provider.py`

```python
from irc.research.search.types import Locale, SearchProvider, SearchResult


class BochaProvider:
    """Mainland-China search via Bocha AI (博查, https://api.bochaai.com/v1/web-search).

    Config: settings.bocha_api_key. Covers eastmoney, xueqiu, cls.cn, wallstreetcn,
    sina finance, gov.cn policy outlets. Use for any theme with Locale.ZH.
    """
    name: str = "bocha"
    locale: Locale = Locale.ZH

    def __init__(self, api_key: str, *, timeout_s: int = 15) -> None: ...

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult: ...
```

### `src/irc/research/search/jina_reader.py`

```python
from irc.research.search.types import ContentExtractor, ExtractedPage


class JinaReader:
    """URL → clean markdown via Jina Reader (https://r.jina.ai/<url>).

    Works for both EN and ZH pages. Free tier without a key (rate-limited); paid tier
    via settings.jina_api_key for higher throughput.
    """
    name: str = "jina"

    def __init__(self, api_key: str = "", *, timeout_s: int = 20) -> None: ...

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage: ...
```

### `src/irc/research/search/dispatch.py`

```python
from irc.research.search.types import (
    ContentExtractor, Locale, SearchHit, SearchProvider,
)


def providers_for_locale(
    locale: Locale,
    providers: tuple[SearchProvider, ...],
) -> tuple[SearchProvider, ...]:
    """Filter providers down to the ones matching this locale.

    Raises ValueError if no provider matches — the caller must configure at least one
    EN provider and one ZH provider for full theme coverage.
    """
    ...


def multi_provider_search(
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    *,
    max_results: int = 10,
    freshness_days: int | None = None,
    include_domains: tuple[str, ...] = (),
) -> tuple[SearchHit, ...]:
    """Fan out to every provider matching the locale, dedupe by URL, rank by
    (freshness, provider order), and return up to max_results hits.

    Returns empty tuple if all providers fail; per-provider failures are not raised.
    """
    ...


def extract_top_pages(
    hits: tuple[SearchHit, ...],
    extractor: ContentExtractor,
    *,
    top_k: int = 5,
    timeout_s: int = 20,
) -> tuple[Locale, ...]:  # actually tuple[ExtractedPage, ...] — see types.py
    """Convert top-K hits to markdown pages in parallel. Failures are kept as
    ExtractedPage with failure_reason set, never dropped silently."""
    ...
```

### `src/irc/research/synthesize.py`

```python
from dataclasses import dataclass, field
from irc.llm._types import ResolvedRoute
from irc.research.search.types import ExtractedPage, SearchHit


@dataclass(frozen=True)
class Citation:
    index: int
    title: str
    url: str
    published_iso: str = ""


@dataclass(frozen=True)
class ResearchReport:
    """Drop-in replacement for the old LDRResearchResult.

    The (report_md, citations, failure_reason) shape is preserved so existing
    consumers need only an import rename.
    """
    report_md: str
    citations: list[Citation] = field(default_factory=list)
    failure_reason: str = ""


def synthesize_report(
    query: str,
    hits: tuple[SearchHit, ...],
    pages: tuple[ExtractedPage, ...],
    *,
    route: ResolvedRoute,
    max_tokens: int = 2000,
) -> ResearchReport:
    """One LLM call: (query + hits + pages) -> markdown report with [n] citation markers.

    Takes a ResolvedRoute (matches existing memo/synthesizer + scoring/factors pattern)
    so the model is selected via `config/llm.yaml` task routing rather than hard-coded.
    The corresponding task is `research_synth`.

    Citations are derived from the input source pool (pages preferred, then hits), so
    the LLM cannot hallucinate URLs — it only chooses which [n] markers to reference.

    Pure adapter; the LLM call is the only I/O. If the LLM call fails or no sources
    are supplied, returns ResearchReport(report_md="", failure_reason=...) — never raises.
    """
    ...
```

### `src/irc/research/theme_research.py` (rewrite)

```python
from dataclasses import dataclass
from irc.llm._types import ResolvedRoute
from irc.research.search.types import (
    ContentExtractor, Locale, SearchProvider,
)
from irc.research.synthesize import Citation


@dataclass(frozen=True)
class ThemeReport:
    theme: str
    query: str
    locale: str          # "en" | "zh"
    report_md: str
    citations: list[Citation]
    failure_reason: str


def theme_locale(theme: str) -> Locale:
    """Map a theme key to the search locale that fits its source ecosystem.
    us_* / gold / geopolitics -> EN; cn_* / hk_* / holdings -> ZH; default EN."""
    ...


def build_theme_reports(
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    max_hits: int = 8,
    top_pages: int = 5,
) -> list[ThemeReport]:
    """For each theme:
       1. resolve locale from theme registry (theme_locale)
       2. multi_provider_search across providers matching the locale → SearchHits
       3. extract_top_pages via the injected extractor → ExtractedPages
       4. synthesize_report → ResearchReport, mapped into ThemeReport

    Providers, extractor, and route are injected to keep the function pure and
    testable. The CLI command (research_cmd.py) builds them from Settings via
    `irc.research.search.factory.build_providers / build_extractor` and resolves
    `route = resolve_route("research_synth", bundle.llm)`.

    No background polling, no LDR. Target wall-clock per theme: ≤30 s.
    Themes that fail produce a ThemeReport with failure_reason set, not an exception.
    """
    ...
```

### `src/irc/research/search/factory.py`

```python
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.settings import Settings


def build_providers(settings: Settings) -> tuple[SearchProvider, ...]:
    """Construct one provider per configured API key. Empty tuple if none set.
    Order: Tavily, Brave, Bocha (English-first, then Chinese)."""
    ...


def build_extractor(settings: Settings) -> ContentExtractor:
    """Returns a JinaReader. Free tier works without a key."""
    ...
```

## Fundamentals Layer Signatures

### `src/irc/fundamentals/types.py`

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Constituent:
    symbol: str           # "600519.SH", "AAPL", "0700.HK"
    name: str
    weight: float          # 0..1 share of the lookthrough_target
    market: str            # "cn" | "us" | "hk"


@dataclass(frozen=True)
class FilingDigest:
    """Compact summary of the latest periodic filing — what the LLM needs to read,
    not the full 200-page PDF."""
    symbol: str
    fiscal_period: str         # "2026Q1", "2025FY"
    filed_at_iso: str
    revenue_yoy: float | None
    net_income_yoy: float | None
    gross_margin: float | None
    guidance_text: str = ""     # short excerpt from management commentary
    source_url: str = ""


@dataclass(frozen=True)
class BrokerReport:
    symbol: str
    broker: str
    rating: str                # "买入" / "增持" / "buy" / "hold" / etc.
    target_price: float | None
    published_iso: str
    title: str
    source_url: str = ""


@dataclass(frozen=True)
class ConstituentSnapshot:
    """All constituent-level evidence for one lookthrough_target at one point in time.

    Cached to disk; refreshed quarterly (aligned with earnings season).
    Consumed by opportunity.states.classify_thesis_state() to produce auditable
    `thesis_state` decisions instead of free-text LLM outputs.
    """
    lookthrough_target: str    # "半导体指数"
    as_of_iso: str
    constituents: tuple[Constituent, ...]
    filings: tuple[FilingDigest, ...]
    broker_reports: tuple[BrokerReport, ...]
    failure_reasons: tuple[str, ...] = ()  # per-source diagnostics, e.g. "edgar 503"
```

### `src/irc/fundamentals/akshare_fundamentals.py`

```python
from irc.fundamentals.types import BrokerReport, Constituent, FilingDigest


def fetch_cn_index_constituents(
    index_code: str,
    *,
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Top-N constituents of a CN index (沪深300, 中证500, 半导体指数, etc.)
    via ak.index_stock_cons_weight_csindex or equivalent."""
    ...


def fetch_cn_etf_holdings(
    symbol: str,
    *,
    as_of: str = "",
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Latest disclosed holdings for a CN ETF via ak.fund_portfolio_hold_em."""
    ...


def fetch_cn_broker_reports(
    symbol: str,
    *,
    days: int = 90,
    max_reports: int = 20,
) -> tuple[BrokerReport, ...]:
    """Recent 券商研报 for a CN stock via ak.stock_research_report_em.

    Returns reports published in the last `days` days, newest first."""
    ...


def fetch_cn_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest 年报 or 季报 digest for a CN stock via ak.stock_financial_abstract
    + ak.stock_zh_a_disclosure_relation_cninfo. Returns None on failure."""
    ...
```

### `src/irc/fundamentals/edgar_client.py`

```python
from irc.fundamentals.types import FilingDigest


def fetch_us_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest 10-K / 10-Q digest for a US-listed company via SEC EDGAR JSON API
    (https://data.sec.gov/submissions/CIK*.json). Returns None on failure.

    Pure adapter; uses irc.llm.http_client for SSRF safety."""
    ...
```

### `src/irc/fundamentals/hkex_client.py`

```python
from irc.fundamentals.types import FilingDigest


def fetch_hk_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest interim / annual digest for a HK-listed company via HKEX
    disclosure feed. Returns None on failure."""
    ...
```

### `src/irc/fundamentals/snapshot.py`

```python
from pathlib import Path
from irc.fundamentals.types import ConstituentSnapshot


def build_snapshot(
    lookthrough_target: str,
    *,
    top_n: int = 10,
) -> ConstituentSnapshot:
    """Compose Constituents -> BrokerReports -> FilingDigests for one theme.

    Pure orchestration: looks up constituent symbols, then dispatches by market
    to akshare_fundamentals / edgar_client / hkex_client. Per-symbol failures
    are recorded in ConstituentSnapshot.failure_reasons, not raised.
    """
    ...


def cache_path(lookthrough_target: str, quarter: str, root: Path) -> Path:
    """data/<root>/fundamentals/<quarter>/<lookthrough_target>.json"""
    ...


def load_cached_snapshot(
    lookthrough_target: str,
    quarter: str,
    root: Path,
) -> ConstituentSnapshot | None:
    """Return the cached snapshot if present and well-formed, else None."""
    ...


def write_snapshot(snapshot: ConstituentSnapshot, root: Path) -> Path:
    """Write snapshot as JSON under cache_path(). Returns the written path."""
    ...
```

## Configuration

Adapters read API keys from `irc.settings.Settings`. New fields, all optional `SecretStr` defaulting to empty:

```python
# src/irc/settings.py — additions
tavily_api_key: SecretStr = SecretStr("")
brave_api_key:  SecretStr = SecretStr("")
bocha_api_key:  SecretStr = SecretStr("")
jina_api_key:   SecretStr = SecretStr("")   # optional; free tier works without
```

The old `ldr_*` fields are removed from `Settings`.

A provider is constructed only if its key is set. If no EN provider is configured, EN themes produce `failure_reason="no en search provider configured"`. Same for ZH. The pipeline never crashes from missing keys.

The pipeline-level gate flips from `LDR_ENABLED=true` to `RESEARCH_ENABLED=true`. The default `irc run` still skips research unless this is set, matching the previous LDR-gated default. The research stage itself loads `Settings`, builds providers via `factory.build_providers`, and skips with a clear message if none are configured — `RESEARCH_ENABLED=true` without keys does not crash.

`config/llm.yaml` gains a `research_synth` task entry. The default mapping points at `deepseek-chat` (cheap, fast); users can override per their setup.

## Test Surface

Each provider gets its own unit-test module that mocks `httpx`:

- `tests/research/search/test_tavily_provider.py`
- `tests/research/search/test_brave_provider.py`
- `tests/research/search/test_bocha_provider.py`
- `tests/research/search/test_jina_reader.py`
- `tests/research/search/test_dispatch.py`
- `tests/research/test_synthesize.py` (mocks LLM)
- `tests/research/test_theme_research.py` (rewrite; mocks search + synth)
- `tests/fundamentals/test_akshare_fundamentals.py`
- `tests/fundamentals/test_edgar_client.py`
- `tests/fundamentals/test_snapshot.py`

`tests/research/test_ldr_client.py` is deleted.

## Out of Scope

- Caching layer at the search level (LRU, on-disk). Add only if profiling shows duplicate queries within a single weekly run.
- Streaming synthesis. One-shot LLM call is enough for ≤30 s budget.
- Authenticated paid databases (Wind, Bloomberg). All sources here are free or low-cost APIs.
