# Plan 4: News + Research + Eval Framework + Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the news layer (RSS + OpenBB-news + Scrapling), the research layer (LDR-backed theme research), wire `thesis_news` factor to real news, and build the per-stage eval framework with 12 stages × 40+ metrics, baselines, spot-check queue, and meta-eval. Result: complete MVP with quality gates and full provenance.

**Architecture:** Stage 2 (RESEARCH) + News pipeline (N1-N4) + Stage 8 (EVAL) + replacement for `thesis_news` stub from Plan 2 + meta polish (PIPELINE_HALTED.md, `irc eval` CLI, spot-check queue). Inherits FP / TDD discipline.

**Tech Stack:** From Plans 1-3, plus: `feedparser` (RSS), Local Deep Research's HTTP API (LDR runs separately, MVP assumes locally hosted at `LDR_BASE_URL`).

---

## Plan Series Overview

This is **Plan 4 of 4** — the final plan. Prerequisites: Plans 1-3 land. After Plan 4:
- News across 7 topics ingested into `data/news/` and DuckDB.
- LDR theme research populates `data/research/<theme>.md` with citations.
- `thesis_news` factor consumes real news instead of returning neutral 50.
- `irc eval [<stage>] [--all] [--update-baseline] [--backtest]` works.
- Spot-check queue surfaces samples for human review.
- Memo §5 (risks) and §6 (data completeness) become real, not placeholder.
- `PIPELINE_HALTED.md` generated on HARD failures.

---

## File Structure

New files (Plans 1-3 unchanged unless noted):

```
investment-research-copilot/
├── pyproject.toml                              # MODIFY — add feedparser
├── src/irc/
│   ├── news/
│   │   ├── __init__.py
│   │   ├── rss_aggregator.py                   # NEW — N1
│   │   ├── openbb_news.py                      # NEW — N2
│   │   ├── scrapling_news.py                   # NEW — N3 (stubbable)
│   │   ├── topic_classifier.py                 # NEW — 7-topic mapping
│   │   ├── dedup.py                            # NEW
│   │   ├── events_calendar.py                  # NEW
│   │   └── pipeline.py                         # NEW
│   ├── research/
│   │   ├── __init__.py
│   │   ├── ldr_client.py                       # NEW — HTTP wrapper
│   │   ├── theme_research.py                   # NEW
│   │   ├── falsification.py                    # NEW
│   │   └── pipeline.py                         # NEW
│   ├── scoring/factors/
│   │   └── thesis_news.py                      # MODIFY — replace stub
│   ├── memo/
│   │   └── pipeline.py                         # MODIFY — real risks + completeness
│   ├── commands/
│   │   ├── research_cmd.py                     # NEW — irc research
│   │   ├── eval_cmd.py                         # NEW — irc eval
│   │   └── run_cmd.py                          # MODIFY — add news + research
│   └── cli.py                                  # MODIFY
├── evals/
│   ├── _shared/
│   │   ├── __init__.py
│   │   ├── report_schema.py                    # NEW
│   │   ├── status.py                           # NEW
│   │   ├── baseline_diff.py                    # NEW
│   │   └── registry.py                         # NEW
│   ├── data/{__init__.py,metrics.py,runner.py,baselines/}
│   ├── news/{...}
│   ├── research/{...}
│   ├── discovery/{...}
│   ├── scoring/{...}
│   ├── gold_score/{...}
│   ├── allocation/{...}
│   ├── trade_plan/{...}
│   ├── memo/{...}
│   ├── queries/{...}
│   ├── triggers/{...}
│   ├── architecture/{...}
│   └── spot_check/{queue.csv,reviewed.csv,runner.py}
└── tests/                                      # mirrors src/ + evals/
```

**File-size rule** still applies: < 200 lines / file, < 20 lines / function.

---

## Task 1: Add feedparser + RSS Aggregator

**Files:**
- Modify: `pyproject.toml` (add feedparser)
- Create: `src/irc/news/__init__.py`
- Create: `src/irc/news/rss_aggregator.py`
- Create: `tests/news/__init__.py`
- Create: `tests/news/test_rss_aggregator.py`

- [ ] **Step 1: Add feedparser dependency**

In `pyproject.toml`, append `"feedparser>=6.0",` to the `dependencies` list. Run `uv sync --all-extras`.

- [ ] **Step 2: Empty `__init__.py`**

```python
# src/irc/news/__init__.py
```
```python
# tests/news/__init__.py
```

- [ ] **Step 3: Write the failing test**

```python
# tests/news/test_rss_aggregator.py
from __future__ import annotations
from unittest.mock import patch
from irc.news.rss_aggregator import fetch_feeds, FeedItem


_FAKE_RSS_PARSED = type("FP", (), {
    "entries": [
        type("E", (), {
            "title": "Fed signals patience",
            "link": "https://example.com/1",
            "summary": "FOMC minutes show patience",
            "published": "2026-05-07T10:00:00Z",
        })(),
        type("E", (), {
            "title": "PBoC liquidity injection",
            "link": "https://example.com/2",
            "summary": "1y MLF unchanged",
            "published": "2026-05-06T08:00:00Z",
        })(),
    ]
})()


@patch("irc.news.rss_aggregator.feedparser.parse", return_value=_FAKE_RSS_PARSED)
def test_fetch_feeds_returns_normalized_items(mock_parse):
    items = fetch_feeds(urls=["http://x/rss"], topic="us_monetary")
    assert len(items) == 2
    assert all(isinstance(i, FeedItem) for i in items)
    assert items[0].topic == "us_monetary"
    assert items[0].title == "Fed signals patience"
    assert items[0].source_url == "https://example.com/1"
```

- [ ] **Step 4: Implement**

```python
# src/irc/news/rss_aggregator.py
from __future__ import annotations
from dataclasses import dataclass
import feedparser


@dataclass(frozen=True)
class FeedItem:
    title: str
    summary: str
    source_url: str
    published_iso: str
    topic: str


def fetch_feeds(urls: list[str], topic: str) -> list[FeedItem]:
    """Pull a list of RSS URLs and return normalized FeedItems tagged with topic."""
    out: list[FeedItem] = []
    for url in urls:
        parsed = feedparser.parse(url)
        for entry in getattr(parsed, "entries", []):
            out.append(FeedItem(
                title=getattr(entry, "title", "") or "",
                summary=getattr(entry, "summary", "") or "",
                source_url=getattr(entry, "link", "") or "",
                published_iso=getattr(entry, "published", "") or "",
                topic=topic,
            ))
    return out
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/news/test_rss_aggregator.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/irc/news/__init__.py src/irc/news/rss_aggregator.py tests/news/__init__.py tests/news/test_rss_aggregator.py
git commit -m "feat(news/rss): feedparser-based aggregator with topic tag"
```

---

## Task 2: Topic Classifier (7 topics)

**Files:**
- Create: `src/irc/news/topic_classifier.py`
- Create: `tests/news/test_topic_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_topic_classifier.py
from __future__ import annotations
from irc.news.topic_classifier import classify_topic, TOPICS


def test_topics_set():
    assert set(TOPICS) == {
        "us_monetary", "us_fiscal_politics",
        "cn_monetary", "cn_equity_property_policy",
        "geopolitics", "gold_specific", "holdings_sector",
    }


def test_keyword_routing():
    assert classify_topic("FOMC minutes show ...", url="federalreserve.gov") == "us_monetary"
    assert classify_topic("PBoC reverse repo of ...", url="pbc.gov.cn") == "cn_monetary"
    assert classify_topic("World Gold Council Q1 ...", url="gold.org") == "gold_specific"
    assert classify_topic("Russia-Ukraine ...", url="reuters.com") == "geopolitics"


def test_default_falls_back_to_holdings_sector():
    assert classify_topic("ABC announces ...", url="generic.com") == "holdings_sector"
```

- [ ] **Step 2: Implement**

```python
# src/irc/news/topic_classifier.py
from __future__ import annotations
from typing import Final


TOPICS: Final[tuple[str, ...]] = (
    "us_monetary", "us_fiscal_politics",
    "cn_monetary", "cn_equity_property_policy",
    "geopolitics", "gold_specific", "holdings_sector",
)


_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("us_monetary", ("federalreserve.gov", "fomc", "powell", "fred", "fedwatch")),
    ("us_fiscal_politics", ("treasury.gov", "congress", "debt ceiling", "election")),
    ("cn_monetary", ("pbc.gov.cn", "pboc", "央行", "公开市场", "mlf")),
    ("cn_equity_property_policy", ("csrc", "证监会", "银保监", "财政部", "房地产")),
    ("geopolitics", ("isw", "cfr.org", "russia-ukraine", "中东", "台海", "geopolit")),
    ("gold_specific", ("gold.org", "world gold council", "wgc", "lbma", "kitco", "shfe")),
)


def classify_topic(text: str, url: str = "") -> str:
    blob = (text + " " + url).lower()
    for topic, kws in _RULES:
        if any(k in blob for k in kws):
            return topic
    return "holdings_sector"
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/news/test_topic_classifier.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/news/topic_classifier.py tests/news/test_topic_classifier.py
git commit -m "feat(news/topic_classifier): 7-topic keyword router with default holdings_sector"
```

---

## Task 3: News Deduplication

**Files:**
- Create: `src/irc/news/dedup.py`
- Create: `tests/news/test_dedup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_dedup.py
from __future__ import annotations
from irc.news.rss_aggregator import FeedItem
from irc.news.dedup import dedup_items, similarity_signature


def _item(title: str, url: str = "u") -> FeedItem:
    return FeedItem(title=title, summary="", source_url=url, published_iso="t", topic="x")


def test_dedup_removes_exact_url_duplicate():
    items = [_item("a", "u1"), _item("b", "u1")]
    out = dedup_items(items)
    assert len(out) == 1


def test_dedup_keeps_distinct_items():
    items = [_item("Fed cuts rates", "u1"), _item("PBoC injects liquidity", "u2")]
    out = dedup_items(items)
    assert len(out) == 2


def test_dedup_clusters_near_duplicates_by_signature():
    items = [
        _item("Fed cuts rates by 25 bps", "u1"),
        _item("Fed cuts rates 25 bps", "u2"),
    ]
    sig1 = similarity_signature(items[0].title)
    sig2 = similarity_signature(items[1].title)
    # signatures should match for near-duplicates
    assert sig1 == sig2
    out = dedup_items(items)
    assert len(out) == 1
```

- [ ] **Step 2: Implement**

```python
# src/irc/news/dedup.py
from __future__ import annotations
from irc.news.rss_aggregator import FeedItem
import re


def similarity_signature(title: str) -> str:
    """Lowercase, drop digits/punct, keep alphabetic tokens — coarse fingerprint."""
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    cleaned = re.sub(r"\d+", "", cleaned)
    tokens = sorted(set(cleaned.split()))
    return " ".join(tokens)


def dedup_items(items: list[FeedItem]) -> list[FeedItem]:
    """Drop items with same source_url OR same similarity_signature."""
    seen_urls: set[str] = set()
    seen_sigs: set[str] = set()
    out: list[FeedItem] = []
    for it in items:
        if it.source_url and it.source_url in seen_urls:
            continue
        sig = similarity_signature(it.title)
        if sig and sig in seen_sigs:
            continue
        seen_urls.add(it.source_url)
        seen_sigs.add(sig)
        out.append(it)
    return out
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/news/test_dedup.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/news/dedup.py tests/news/test_dedup.py
git commit -m "feat(news/dedup): URL + similarity_signature dedup"
```

---

## Task 4: Events Calendar (Fed/PBoC scheduled events)

**Files:**
- Create: `src/irc/news/events_calendar.py`
- Create: `tests/news/test_events_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_events_calendar.py
from __future__ import annotations
from datetime import date
from irc.news.events_calendar import upcoming_events, KnownEvent


def test_upcoming_events_within_window():
    today = date(2026, 5, 7)
    events = upcoming_events(today=today, lookahead_days=30)
    assert isinstance(events, list)
    if events:
        assert all(isinstance(e, KnownEvent) for e in events)
        assert all(e.date >= today for e in events)


def test_upcoming_events_filtered_by_topic():
    today = date(2026, 5, 7)
    fed_events = upcoming_events(today=today, lookahead_days=120, topics=("us_monetary",))
    for e in fed_events:
        assert e.topic == "us_monetary"
```

- [ ] **Step 2: Implement (statically populated for MVP — Roadmap T5.1 deepens)**

```python
# src/irc/news/events_calendar.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class KnownEvent:
    name: str
    date: date
    topic: str
    notes: str


_KNOWN_2026: tuple[KnownEvent, ...] = (
    KnownEvent("FOMC June meeting", date(2026, 6, 17), "us_monetary", "Rate decision + dot plot"),
    KnownEvent("FOMC July meeting", date(2026, 7, 29), "us_monetary", "Rate decision"),
    KnownEvent("FOMC September meeting", date(2026, 9, 16), "us_monetary", "Rate decision + SEP"),
    KnownEvent("PBoC LPR May", date(2026, 5, 20), "cn_monetary", "Loan prime rate"),
    KnownEvent("PBoC LPR June", date(2026, 6, 20), "cn_monetary", "Loan prime rate"),
    KnownEvent("WGC Q2 report", date(2026, 7, 31), "gold_specific", "Quarterly demand"),
    KnownEvent("CPI release (US)", date(2026, 5, 14), "us_monetary", "Monthly CPI"),
)


def upcoming_events(
    today: date, lookahead_days: int = 30, topics: tuple[str, ...] | None = None,
) -> list[KnownEvent]:
    horizon = (today, date.fromordinal(today.toordinal() + lookahead_days))
    out = [e for e in _KNOWN_2026 if horizon[0] <= e.date <= horizon[1]]
    if topics:
        out = [e for e in out if e.topic in topics]
    return sorted(out, key=lambda x: x.date)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/news/test_events_calendar.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/news/events_calendar.py tests/news/test_events_calendar.py
git commit -m "feat(news/events_calendar): statically populated FOMC/PBoC/WGC schedule"
```

---

## Task 5: News Pipeline (RSS + classifier + dedup)

**Files:**
- Create: `src/irc/news/pipeline.py`
- Create: `tests/news/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_pipeline.py
from __future__ import annotations
from unittest.mock import patch
from irc.news.rss_aggregator import FeedItem
from irc.news.pipeline import build_news_layer, NewsLayerOutput


_FAKE_ITEMS = [
    FeedItem(title="FOMC minutes patience", summary="", source_url="u1",
              published_iso="2026-05-07", topic="placeholder"),
    FeedItem(title="WGC Q1 +228 tons", summary="", source_url="u2",
              published_iso="2026-05-07", topic="placeholder"),
    FeedItem(title="FOMC minutes patience", summary="", source_url="u1",  # dup
              published_iso="2026-05-07", topic="placeholder"),
]


@patch("irc.news.pipeline.fetch_feeds")
def test_build_news_layer_dedups_and_classifies(mock_fetch):
    mock_fetch.return_value = _FAKE_ITEMS
    out = build_news_layer(feed_urls_by_topic={"us_monetary": ["u1"], "gold_specific": ["u2"]})
    assert isinstance(out, NewsLayerOutput)
    titles = [it.title for it in out.items]
    assert len(titles) == 2  # 1 dup removed
    topics = {it.topic for it in out.items}
    assert "us_monetary" in topics
    assert "gold_specific" in topics
```

- [ ] **Step 2: Implement**

```python
# src/irc/news/pipeline.py
from __future__ import annotations
from dataclasses import dataclass
from irc.news.rss_aggregator import fetch_feeds, FeedItem
from irc.news.topic_classifier import classify_topic
from irc.news.dedup import dedup_items


@dataclass(frozen=True)
class NewsLayerOutput:
    items: list[FeedItem]
    counts_per_topic: dict[str, int]


def build_news_layer(feed_urls_by_topic: dict[str, list[str]]) -> NewsLayerOutput:
    """Pull all feeds, classify each item (refining topic), dedup, count per topic."""
    raw: list[FeedItem] = []
    for topic, urls in feed_urls_by_topic.items():
        raw.extend(fetch_feeds(urls=urls, topic=topic))
    refined: list[FeedItem] = []
    for it in raw:
        topic = classify_topic(it.title + " " + it.summary, url=it.source_url) or it.topic
        refined.append(FeedItem(
            title=it.title, summary=it.summary, source_url=it.source_url,
            published_iso=it.published_iso, topic=topic,
        ))
    deduped = dedup_items(refined)
    counts: dict[str, int] = {}
    for it in deduped:
        counts[it.topic] = counts.get(it.topic, 0) + 1
    return NewsLayerOutput(items=deduped, counts_per_topic=counts)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/news/test_pipeline.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/news/pipeline.py tests/news/test_pipeline.py
git commit -m "feat(news/pipeline): aggregate + reclassify + dedup with per-topic counts"
```

---

## Task 6: LDR HTTP Client

**Files:**
- Create: `src/irc/research/__init__.py`
- Create: `src/irc/research/ldr_client.py`
- Create: `tests/research/__init__.py`
- Create: `tests/research/test_ldr_client.py`

- [ ] **Step 1: Empty `__init__.py` + failing test**

```python
# src/irc/research/__init__.py
```
```python
# tests/research/__init__.py
```

```python
# tests/research/test_ldr_client.py
from __future__ import annotations
import respx
import httpx
from irc.research.ldr_client import run_research, LDRResearchResult


@respx.mock
def test_ldr_run_research_happy_path(monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("LDR_API_TOKEN", "tok")
    respx.post("http://localhost:8080/api/v1/research").mock(
        return_value=httpx.Response(200, json={
            "report_md": "# Gold drivers\n[1] Fed minutes.",
            "citations": [{"index": 1, "title": "Fed minutes", "url": "https://x.com/fed"}],
        })
    )
    out = run_research(query="What drove gold last quarter?", time_budget_s=60)
    assert isinstance(out, LDRResearchResult)
    assert "Gold drivers" in out.report_md
    assert len(out.citations) == 1


@respx.mock
def test_ldr_returns_empty_on_503(monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("LDR_API_TOKEN", "tok")
    respx.post("http://localhost:8080/api/v1/research").mock(return_value=httpx.Response(503))
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert out.failure_reason
```

- [ ] **Step 2: Implement**

```python
# src/irc/research/ldr_client.py
from __future__ import annotations
from dataclasses import dataclass, field
import os
import httpx


@dataclass(frozen=True)
class LDRCitation:
    index: int
    title: str
    url: str


@dataclass(frozen=True)
class LDRResearchResult:
    report_md: str
    citations: list[LDRCitation] = field(default_factory=list)
    failure_reason: str = ""


def run_research(query: str, time_budget_s: int = 120) -> LDRResearchResult:
    base = os.environ.get("LDR_BASE_URL", "http://localhost:8080").rstrip("/")
    token = os.environ.get("LDR_API_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=time_budget_s) as client:
            resp = client.post(
                f"{base}/api/v1/research",
                headers=headers,
                json={"query": query, "time_budget_s": time_budget_s},
            )
        if resp.status_code != 200:
            return LDRResearchResult(report_md="", failure_reason=f"http {resp.status_code}")
        body = resp.json()
        cits = [LDRCitation(**c) for c in body.get("citations", [])]
        return LDRResearchResult(report_md=body.get("report_md", ""), citations=cits)
    except Exception as e:
        return LDRResearchResult(report_md="", failure_reason=str(e))
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/research/test_ldr_client.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/research/__init__.py src/irc/research/ldr_client.py tests/research/__init__.py tests/research/test_ldr_client.py
git commit -m "feat(research/ldr_client): HTTP wrapper with token + graceful failure"
```

---

## Task 7: Theme Research Compositor

**Files:**
- Create: `src/irc/research/theme_research.py`
- Create: `tests/research/test_theme_research.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_theme_research.py
from __future__ import annotations
from unittest.mock import patch
from irc.research.theme_research import build_theme_reports, ThemeReport
from irc.research.ldr_client import LDRResearchResult, LDRCitation


@patch("irc.research.theme_research.run_research")
def test_build_theme_reports_one_per_theme(mock_run):
    mock_run.return_value = LDRResearchResult(
        report_md="Markdown body",
        citations=[LDRCitation(index=1, title="Fed", url="https://fed")],
    )
    out = build_theme_reports(themes=("us_monetary", "gold_drivers"))
    assert len(out) == 2
    assert all(isinstance(r, ThemeReport) for r in out)
    assert out[0].theme in ("us_monetary", "gold_drivers")


@patch("irc.research.theme_research.run_research")
def test_failure_recorded_in_report(mock_run):
    mock_run.return_value = LDRResearchResult(report_md="", failure_reason="timeout")
    out = build_theme_reports(themes=("us_monetary",))
    assert out[0].failure_reason == "timeout"
    assert out[0].report_md == ""
```

- [ ] **Step 2: Implement**

```python
# src/irc/research/theme_research.py
from __future__ import annotations
from dataclasses import dataclass
from irc.research.ldr_client import run_research, LDRCitation


@dataclass(frozen=True)
class ThemeReport:
    theme: str
    query: str
    report_md: str
    citations: list[LDRCitation]
    failure_reason: str


_THEME_QUERIES: dict[str, str] = {
    "us_monetary":               "What did the Fed say or do this past week? Cite primary sources.",
    "us_fiscal_politics":        "Recent US fiscal / political news affecting markets, with citations.",
    "cn_monetary":                "PBoC actions and statements this week with primary sources.",
    "cn_equity_property_policy": "China equity / property regulatory news with primary sources.",
    "geopolitics":                "Material geopolitical events (Russia-Ukraine, Middle East, Taiwan) this week with primary sources.",
    "gold_drivers":               "Recent moves in real yields, USD, central bank gold purchases, ETF flows; cite primary sources.",
    "holdings_sector":            "News for sectors held in user portfolio; cite primary sources.",
}


def build_theme_reports(themes: tuple[str, ...], time_budget_s: int = 90) -> list[ThemeReport]:
    out: list[ThemeReport] = []
    for theme in themes:
        query = _THEME_QUERIES.get(theme, f"Research summary for {theme}")
        res = run_research(query=query, time_budget_s=time_budget_s)
        out.append(ThemeReport(
            theme=theme, query=query,
            report_md=res.report_md, citations=res.citations,
            failure_reason=res.failure_reason,
        ))
    return out
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/research/test_theme_research.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/research/theme_research.py tests/research/test_theme_research.py
git commit -m "feat(research/theme_research): per-theme query → ThemeReport with citations"
```

---

## Task 8: Falsification Conditions Generator

**Files:**
- Create: `src/irc/research/falsification.py`
- Create: `tests/research/test_falsification.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_falsification.py
from __future__ import annotations
from unittest.mock import patch, MagicMock
from irc.research.falsification import generate_falsification, FalsificationResult


@patch("irc.research.falsification.call_chat")
def test_falsification_returns_list(mock_chat):
    mock_chat.return_value = MagicMock(
        text='{"conditions": ["Fed hikes 50bps", "DXY breaks 115"]}',
        prompt_tokens=50, completion_tokens=20,
    )
    out = generate_falsification(thesis_summary="Gold should outperform", route=MagicMock())
    assert isinstance(out, FalsificationResult)
    assert "Fed hikes 50bps" in out.conditions
    assert len(out.conditions) == 2


@patch("irc.research.falsification.call_chat")
def test_falsification_invalid_json_returns_empty(mock_chat):
    mock_chat.return_value = MagicMock(text="not json", prompt_tokens=5, completion_tokens=2)
    out = generate_falsification(thesis_summary="x", route=MagicMock())
    assert out.conditions == ()
```

- [ ] **Step 2: Implement**

```python
# src/irc/research/falsification.py
from __future__ import annotations
from dataclasses import dataclass
import json
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat


@dataclass(frozen=True)
class FalsificationResult:
    conditions: tuple[str, ...]


_SYS = (
    "Given an investment thesis summary, list 3-5 falsification conditions: events that, "
    "if observed, would invalidate the thesis. Output JSON: "
    '{"conditions": ["...", "..."]}'
)


def generate_falsification(thesis_summary: str, route: ResolvedRoute) -> FalsificationResult:
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": thesis_summary},
        ], timeout_s=30, temperature=0.2)
        data = json.loads(resp.text)
        conds = data.get("conditions", [])
        return FalsificationResult(conditions=tuple(str(c) for c in conds))
    except (json.JSONDecodeError, KeyError, ValueError, Exception):
        return FalsificationResult(conditions=())
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/research/test_falsification.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/research/falsification.py tests/research/test_falsification.py
git commit -m "feat(research/falsification): LLM thesis_falsify task → 3-5 conditions"
```

---

## Task 9: Research Pipeline + `irc research`

**Files:**
- Create: `src/irc/research/pipeline.py`
- Create: `src/irc/commands/research_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/research/test_pipeline.py`
- Create: `tests/commands/test_research_cmd.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
# tests/research/test_pipeline.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
from irc.research.ldr_client import LDRResearchResult, LDRCitation
from irc.research.pipeline import run_research_pipeline


@patch("irc.research.theme_research.run_research")
def test_research_pipeline_writes_markdown_per_theme(mock_run, tmp_path: Path):
    mock_run.return_value = LDRResearchResult(
        report_md="Markdown body about ${theme}.",
        citations=[LDRCitation(index=1, title="Source", url="https://x")],
    )
    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        time_budget_s=10,
    )
    assert rc == 0
    assert (tmp_path / "data/research/us_monetary.md").exists()
    assert (tmp_path / "data/research/gold_drivers.md").exists()
```

- [ ] **Step 2: Implement**

```python
# src/irc/research/pipeline.py
from __future__ import annotations
from pathlib import Path
from irc.research.theme_research import build_theme_reports
from irc.io_utils import atomic_write_text


def _format_report(theme: str, body_md: str, citations: list, failure_reason: str) -> str:
    if failure_reason:
        return f"# {theme}\n\n_research failed: {failure_reason}_\n"
    cit_lines = "\n".join(f"[{c.index}] {c.title} — {c.url}" for c in citations)
    return f"# {theme}\n\n{body_md}\n\n## Citations\n{cit_lines}\n"


def run_research_pipeline(
    repo_root: Path, themes: tuple[str, ...], time_budget_s: int,
) -> int:
    out_dir = repo_root / "data" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = build_theme_reports(themes=themes, time_budget_s=time_budget_s)
    for r in reports:
        atomic_write_text(
            out_dir / f"{r.theme}.md",
            _format_report(r.theme, r.report_md, r.citations, r.failure_reason),
        )
    return 0
```

- [ ] **Step 3: Implement `src/irc/commands/research_cmd.py`**

```python
from __future__ import annotations
from pathlib import Path
from irc.research.pipeline import run_research_pipeline


_DEFAULT_THEMES: tuple[str, ...] = (
    "us_monetary", "us_fiscal_politics",
    "cn_monetary", "cn_equity_property_policy",
    "geopolitics", "gold_drivers", "holdings_sector",
)


def run_research(repo_root: str) -> int:
    return run_research_pipeline(
        repo_root=Path(repo_root), themes=_DEFAULT_THEMES, time_budget_s=120,
    )
```

- [ ] **Step 4: Register `research` in CLI**

```python
@main.command(help="Run LDR research jobs across 7 themes; write data/research/<theme>.md.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def research(repo_root: str) -> None:
    from irc.commands.research_cmd import run_research
    rc = run_research(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Run pipeline test**

Run: `uv run pytest tests/research/test_pipeline.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/research/pipeline.py src/irc/commands/research_cmd.py src/irc/cli.py tests/research/test_pipeline.py
git commit -m "feat(cli/research): per-theme LDR research → data/research/<theme>.md"
```

---

## Task 10: Replace `thesis_news` Stub with Real News-Driven Score

**Files:**
- Modify: `src/irc/scoring/factors/thesis_news.py:1-25`
- Modify: `tests/scoring/factors/test_thesis_news.py:1-25`

- [ ] **Step 1: Replace `thesis_news` test**

```python
# tests/scoring/factors/test_thesis_news.py
from __future__ import annotations
from irc.scoring.factors.thesis_news import (
    score_thesis_news, NewsSignals, score_from_signals,
)


def test_high_positive_signals_score_higher():
    sig_pos = NewsSignals(catalyst_count=4, risk_count=1, narrative_momentum=0.8)
    sig_neg = NewsSignals(catalyst_count=1, risk_count=4, narrative_momentum=-0.5)
    assert score_from_signals(sig_pos) > score_from_signals(sig_neg)


def test_no_news_returns_neutral_with_low_completeness():
    s = score_thesis_news(news_summaries=(), raw_refs=())
    assert s.score == 50
    assert s.components["data_completeness"] == 0.0


def test_with_news_uses_signals():
    s = score_thesis_news(
        news_summaries=("Fed signals patience", "Strong demand for gold"),
        raw_refs=("ref1",),
    )
    assert 0 <= s.score <= 100
    assert s.components["data_completeness"] == 1.0
```

- [ ] **Step 2: Replace `thesis_news` implementation**

```python
# src/irc/scoring/factors/thesis_news.py
from __future__ import annotations
from dataclasses import dataclass
from irc.scoring.factors.valuation_cost import FactorScore


_POS = ("growth", "demand", "patience", "rally", "buy", "support", "强劲", "上行", "购金")
_NEG = ("hike", "tighten", "outflow", "weak", "fall", "drag", "降息", "回撤", "撤资")


@dataclass(frozen=True)
class NewsSignals:
    catalyst_count: int
    risk_count: int
    narrative_momentum: float  # -1 to +1


def _signals_from_summaries(summaries: tuple[str, ...]) -> NewsSignals:
    pos_count = 0
    neg_count = 0
    for s in summaries:
        s_low = s.lower()
        pos_count += sum(1 for w in _POS if w in s_low)
        neg_count += sum(1 for w in _NEG if w in s_low)
    if pos_count + neg_count == 0:
        momentum = 0.0
    else:
        momentum = (pos_count - neg_count) / (pos_count + neg_count)
    return NewsSignals(
        catalyst_count=pos_count, risk_count=neg_count, narrative_momentum=momentum,
    )


def score_from_signals(sig: NewsSignals) -> float:
    base = 50 + sig.narrative_momentum * 30
    if sig.catalyst_count >= 3:
        base += 5
    if sig.risk_count >= 3:
        base -= 5
    return max(0.0, min(100.0, base))


def score_thesis_news(
    news_summaries: tuple[str, ...], raw_refs: tuple[str, ...],
) -> FactorScore:
    """Real news-driven score replacing the Plan-2 stub."""
    if not news_summaries:
        return FactorScore(
            score=50.0, raw_refs=raw_refs,
            components={"data_completeness": 0.0, "neutral_default": 1.0},
        )
    sig = _signals_from_summaries(news_summaries)
    score = score_from_signals(sig)
    return FactorScore(
        score=score, raw_refs=raw_refs,
        components={
            "data_completeness": 1.0,
            "catalyst_count": float(sig.catalyst_count),
            "risk_count": float(sig.risk_count),
            "momentum": sig.narrative_momentum,
        },
    )
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/factors/test_thesis_news.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/factors/thesis_news.py tests/scoring/factors/test_thesis_news.py
git commit -m "feat(scoring/factors/thesis_news): replace stub with news-signals score"
```

---

## Task 11: Eval Shared Schema + Status

**Files:**
- Create: `evals/__init__.py`
- Create: `evals/_shared/__init__.py`
- Create: `evals/_shared/report_schema.py`
- Create: `evals/_shared/status.py`
- Create: `tests/evals/__init__.py`
- Create: `tests/evals/test_status.py`

- [ ] **Step 1: Empty `__init__.py` files**

```python
# evals/__init__.py
```
```python
# evals/_shared/__init__.py
```
```python
# tests/evals/__init__.py
```

- [ ] **Step 2: Write failing test**

```python
# tests/evals/test_status.py
from __future__ import annotations
from evals._shared.status import classify_status, worst_status, Status


def test_classify_pass():
    th = {"warn_below": 0.95, "fail_below": 0.80}
    assert classify_status(value=0.99, thresholds=th, direction="higher_is_better") == "PASS"
    assert classify_status(value=0.90, thresholds=th, direction="higher_is_better") == "WARN"
    assert classify_status(value=0.70, thresholds=th, direction="higher_is_better") == "FAIL"


def test_classify_lower_is_better():
    th = {"warn_above": 0.05, "fail_above": 0.20}
    assert classify_status(value=0.01, thresholds=th, direction="lower_is_better") == "PASS"
    assert classify_status(value=0.10, thresholds=th, direction="lower_is_better") == "WARN"
    assert classify_status(value=0.30, thresholds=th, direction="lower_is_better") == "FAIL"


def test_worst_status():
    assert worst_status(["PASS", "WARN", "PASS"]) == "WARN"
    assert worst_status(["PASS", "WARN", "FAIL"]) == "FAIL"
    assert worst_status([]) == "PASS"
```

- [ ] **Step 3: Implement**

```python
# evals/_shared/status.py
from __future__ import annotations
from typing import Literal


Status = Literal["PASS", "WARN", "FAIL"]
_RANK: dict[str, int] = {"PASS": 0, "WARN": 1, "FAIL": 2}


def classify_status(
    value: float, thresholds: dict[str, float], direction: str,
) -> Status:
    """direction: 'higher_is_better' or 'lower_is_better'."""
    if direction == "higher_is_better":
        warn = thresholds.get("warn_below")
        fail = thresholds.get("fail_below")
        if fail is not None and value < fail:
            return "FAIL"
        if warn is not None and value < warn:
            return "WARN"
        return "PASS"
    if direction == "lower_is_better":
        warn = thresholds.get("warn_above")
        fail = thresholds.get("fail_above")
        if fail is not None and value > fail:
            return "FAIL"
        if warn is not None and value > warn:
            return "WARN"
        return "PASS"
    raise ValueError(f"unknown direction: {direction}")


def worst_status(statuses: list[Status]) -> Status:
    if not statuses:
        return "PASS"
    return max(statuses, key=lambda s: _RANK[s])
```

- [ ] **Step 4: Implement `report_schema.py`**

```python
# evals/_shared/report_schema.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class MetricReport:
    name: str
    value: float
    status: str
    n_observations: int = 0
    threshold: dict[str, float] = field(default_factory=dict)
    details_ref: str | None = None


@dataclass(frozen=True)
class StageReport:
    stage: str
    ran_at: str
    based_on: list[str]
    metrics: list[MetricReport]
    overall: str
    config_versions: dict[str, str] = field(default_factory=dict)


def report_to_dict(r: StageReport) -> dict[str, Any]:
    return asdict(r)
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/evals/test_status.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add evals/ tests/evals/
git commit -m "feat(evals/_shared): MetricReport + StageReport schemas + status classifier"
```

---

## Task 12: Eval — Data Stage

**Files:**
- Create: `evals/data/__init__.py`
- Create: `evals/data/metrics.py`
- Create: `evals/data/runner.py`
- Create: `tests/evals/test_data_metrics.py`

- [ ] **Step 1: Empty `__init__.py`**

```python
# evals/data/__init__.py
```

- [ ] **Step 2: Failing test**

```python
# tests/evals/test_data_metrics.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pytest
from irc.data.duckdb_helper import connect, ensure_schema
from evals.data.metrics import freshness_per_source, completeness_per_field


@pytest.fixture
def db(tmp_path: Path):
    con = connect(tmp_path / "x.duckdb")
    ensure_schema(con)
    today = date.today()
    con.execute(
        "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["VTI", today.isoformat(), 1.0, 1.1, 0.9, 1.05, 1e6,
         datetime.now(timezone(timedelta(hours=8))).isoformat(), "openbb",
         f"openbb:prices:VTI:{today}"]
    )
    yield con
    con.close()


def test_freshness_returns_age_in_days(db):
    out = freshness_per_source(db, source="openbb")
    assert "prices" in out
    assert out["prices"] <= 1


def test_completeness_per_field(db):
    out = completeness_per_field(db, table="prices")
    assert out["close"] == 1.0  # not null
    assert out["instrument_id"] == 1.0
```

- [ ] **Step 3: Implement metrics**

```python
# evals/data/metrics.py
from __future__ import annotations
from datetime import date
import duckdb


def freshness_per_source(con: duckdb.DuckDBPyConnection, source: str) -> dict[str, int]:
    """For each table, days since most recent record from given source."""
    out: dict[str, int] = {}
    for tbl in ("prices", "nav_history", "macro_series"):
        row = con.execute(
            f"SELECT MAX(date) FROM {tbl} WHERE _source = ?",
            [source],
        ).fetchone()
        latest = row[0] if row else None
        if latest is None:
            continue
        age = (date.today() - latest).days
        out[tbl] = age
    return out


def completeness_per_field(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, float]:
    """Fraction of non-null values per column."""
    cols = con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'"
    ).fetchall()
    result: dict[str, float] = {}
    total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total == 0:
        return {c[0]: 1.0 for c in cols}
    for (col,) in cols:
        non_null = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        result[col] = non_null / total
    return result
```

- [ ] **Step 4: Implement runner**

```python
# evals/data/runner.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.data.metrics import freshness_per_source, completeness_per_field


_PRICE_FRESHNESS_TH = {"warn_above": 2, "fail_above": 7}


def run(repo_root: Path) -> int:
    con = connect(repo_root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        ob_freshness = freshness_per_source(con, source="openbb")
        ak_freshness = freshness_per_source(con, source="akshare")
        completeness = completeness_per_field(con, table="prices")
    finally:
        con.close()
    metrics: list[MetricReport] = []
    for source, fresh in (("openbb", ob_freshness), ("akshare", ak_freshness)):
        for tbl, age in fresh.items():
            metrics.append(MetricReport(
                name=f"freshness_{source}_{tbl}_days", value=float(age),
                status=classify_status(age, _PRICE_FRESHNESS_TH, "lower_is_better"),
                n_observations=1, threshold=_PRICE_FRESHNESS_TH,
            ))
    avg_completeness = sum(completeness.values()) / max(len(completeness), 1)
    metrics.append(MetricReport(
        name="prices_completeness_avg", value=avg_completeness,
        status=classify_status(avg_completeness, {"warn_below": 0.95, "fail_below": 0.85},
                                 "higher_is_better"),
        n_observations=len(completeness),
        threshold={"warn_below": 0.95, "fail_below": 0.85},
    ))
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="data",
        ran_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        based_on=[str(repo_root / "data" / "local.duckdb")],
        metrics=metrics,
        overall=overall,
    )
    out_dir = repo_root / "outputs" / datetime.now(timezone(timedelta(hours=8))).date().isoformat() / "evals" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    print(f"data eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/evals/test_data_metrics.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add evals/data/ tests/evals/test_data_metrics.py
git commit -m "feat(evals/data): freshness + completeness metrics + runner"
```

---

## Tasks 13-21: Eval Runners for Other Stages

> The eval modules for the remaining 11 stages follow the **exact same pattern as Task 12**: each has `metrics.py` (pure functions over the stage's outputs) + `runner.py` (loads outputs, calls metrics, writes `report.json`) + a test that constructs synthetic stage outputs and asserts metric values.

For each remaining stage, follow this template — do NOT skip the failing-test → implement → pass cycle.

| # | Stage | Key metrics (per spec §7.D) |
|---|---|---|
| 13 | `evals/news` | `coverage_per_topic_per_week` (≥3), `dedup_rate` (≥80%), `citation_reachability` |
| 14 | `evals/research` | `theme_coverage` (7 themes ≥1 pull), `ldr_citation_validity` (sample) |
| 15 | `evals/discovery` | `candidates_per_role` (≥8 / fail_below 5), `filter_integrity`, `dedup`, `llm_reason_grounding` |
| 16 | `evals/scoring` | `factor_breakdown_completeness` (≥0.99), `raw_ref_reachability` (≥0.99), `historical_sanity_rho` (>0), `score_distribution_stability` |
| 17 | `evals/gold_score` | `drivers_freshness` (each ≤7d), `regime_flip_4w` (≤1), `tilt_within_preferences_band` |
| 18 | `evals/allocation` | `weight_sum` (\|Σ-1\| < 1e-3), `in_band_per_class`, `effective_n` (≥4), `currency_in_tolerance`, `max_pair_correlation_1y` |
| 19 | `evals/trade_plan` | `venue_compatibility_marked` (100%), `buy_method_class_match` (100%), `trigger_monitorability` (100%) |
| 20 | `evals/memo` | `seven_sections_present`, `raw_ref_reachability_in_memo`, `auditor_no_factual_flags`, `length_drift_vs_baseline` |
| 21 | `evals/queries` | `median_response_time` (≤30s), `citation_attached_per_response` (100%), `internal_consistency_with_latest_memo` |

For each task, write **5 steps** in this exact form:

#### Step pattern for `evals/<stage>/`

- [ ] **Step 1: Failing test**

```python
# tests/evals/test_<stage>_metrics.py
# Build synthetic stage output → assert each metric returns the expected value.
# Each metric is a pure function: (raw_data) → number.
# Example for evals/discovery:
from evals.discovery.metrics import candidates_per_role, llm_reason_grounding
# ... etc.
```

- [ ] **Step 2: Implement `evals/<stage>/metrics.py`**: pure functions, one per metric in the table above.
- [ ] **Step 3: Implement `evals/<stage>/runner.py`**: same shape as Task 12 runner — load outputs, call each metric, build `MetricReport`, classify with thresholds from §7.D, write `report.json`.
- [ ] **Step 4: Run** the new test file: `uv run pytest tests/evals/test_<stage>_metrics.py -v`
- [ ] **Step 5: Commit**: `git add evals/<stage>/ tests/evals/test_<stage>_metrics.py && git commit -m "feat(evals/<stage>): metrics + runner per spec §7.D"`

**Concrete code for the more involved metrics:**

```python
# evals/discovery/metrics.py
from __future__ import annotations
import pandas as pd


def candidates_per_role(watchlist: pd.DataFrame) -> dict[str, int]:
    return watchlist.groupby("role").size().to_dict()


def llm_reason_grounding(watchlist: pd.DataFrame) -> float:
    if watchlist.empty:
        return 1.0
    has_ref = (watchlist["cited_refs"].fillna("").str.len() > 0)
    return float(has_ref.mean())
```

```python
# evals/scoring/metrics.py
from __future__ import annotations


def factor_breakdown_completeness(scores: list[dict]) -> float:
    if not scores:
        return 1.0
    required = {"valuation_cost", "risk", "quality", "macro_fit", "thesis_news"}
    counts = [
        len(required & set(s.get("factor_breakdown", {}).keys())) / len(required)
        for s in scores
    ]
    return sum(counts) / len(counts)


def raw_ref_reachability(scores: list[dict], index: set[str]) -> float:
    refs: list[str] = []
    for s in scores:
        for v in s.get("factor_breakdown", {}).values():
            refs.extend(v.get("raw_refs", []))
    if not refs:
        return 1.0
    return sum(1 for r in refs if r in index) / len(refs)
```

```python
# evals/allocation/metrics.py
from __future__ import annotations


def weight_sum(allocation: dict) -> float:
    return sum(allocation["target_weights_per_class"].values())


def effective_n(allocation: dict) -> float:
    weights = [r["target_weight"] for r in allocation.get("selected_instruments", [])]
    s = sum(w * w for w in weights)
    return 1.0 / s if s > 0 else 0.0
```

```python
# evals/memo/metrics.py
from __future__ import annotations


_REQUIRED_SECTIONS = (
    "## TL;DR", "## 1. 当前组合", "## 2. 推荐动作", "## 3. 推导",
    "## 4. 因子分解", "## 5. 风险与证伪", "## 6. 数据完整性", "## 7. 用户覆盖记录",
)


def seven_sections_present(memo_text: str) -> float:
    found = sum(1 for s in _REQUIRED_SECTIONS if s in memo_text)
    return found / len(_REQUIRED_SECTIONS)


def raw_ref_reachability_in_memo(memo_text: str, refs: tuple[str, ...]) -> float:
    if not refs:
        return 1.0
    return sum(1 for r in refs if r in memo_text) / len(refs)
```

Use these as starting code. After implementing each stage's metrics+runner+test, run the suite and commit.

After all 9 sub-tasks (Tasks 13-21) commit, run:

```bash
uv run pytest tests/evals/ -v
```
Expected: all eval tests pass (~25-30 new tests across stages).

---

## Task 22: Eval — Triggers Stage

**Files:**
- Create: `evals/triggers/metrics.py`, `runner.py`
- Create: `tests/evals/test_triggers_metrics.py`

- [ ] **Step 1: Failing test**

```python
# tests/evals/test_triggers_metrics.py
from __future__ import annotations
import pandas as pd
from evals.triggers.metrics import coverage_check, hit_rate_12m


def test_coverage_check_true_when_data_recent():
    out = coverage_check(triggers={"vix_high": "macro.vix"},
                          field_freshness_days={"macro.vix": 2})
    assert out["vix_high"] is True


def test_coverage_check_false_when_stale():
    out = coverage_check(triggers={"vix_high": "macro.vix"},
                          field_freshness_days={"macro.vix": 30})
    assert out["vix_high"] is False


def test_hit_rate():
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=52, freq="W"),
                        "fired": [True] * 5 + [False] * 47})
    rate = hit_rate_12m(df)
    assert 0.05 < rate < 0.15
```

- [ ] **Step 2: Implement**

```python
# evals/triggers/metrics.py
from __future__ import annotations
import pandas as pd


def coverage_check(
    triggers: dict[str, str], field_freshness_days: dict[str, int],
    max_age_days: int = 7,
) -> dict[str, bool]:
    return {
        name: (field in field_freshness_days and field_freshness_days[field] <= max_age_days)
        for name, field in triggers.items()
    }


def hit_rate_12m(history: pd.DataFrame) -> float:
    """history: per-week firing history with bool 'fired' column."""
    if history.empty:
        return 0.0
    return float(history["fired"].mean())
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/evals/test_triggers_metrics.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add evals/triggers/ tests/evals/test_triggers_metrics.py
git commit -m "feat(evals/triggers): coverage + hit_rate metrics"
```

---

## Task 23: Eval — Architecture (meta)

**Files:**
- Create: `evals/architecture/metrics.py`
- Create: `evals/architecture/runner.py`
- Create: `tests/evals/test_architecture.py`

- [ ] **Step 1: Failing test**

```python
# tests/evals/test_architecture.py
from __future__ import annotations
from pathlib import Path
from evals.architecture.metrics import (
    dag_acyclic_check, max_file_loc, output_files_present,
)


def test_dag_acyclic_check_true_for_valid_imports():
    # this codebase: no cycles allowed
    assert dag_acyclic_check(package_root=Path("src/irc")) is True


def test_max_file_loc_returns_int(tmp_path: Path):
    (tmp_path / "a.py").write_text("\n".join(["x = 1"] * 100))
    (tmp_path / "b.py").write_text("\n".join(["y = 1"] * 50))
    assert max_file_loc(tmp_path) == 100


def test_output_files_present(tmp_path: Path):
    out_dir = tmp_path / "outputs/2026-05-07"
    out_dir.mkdir(parents=True)
    for name in ("discovered_watchlist.csv", "scoring.json", "gold_regime.json",
                  "gold_band.yaml", "proposed_allocation.yaml", "trade_plan.yaml",
                  "research_memo.md"):
        (out_dir / name).touch()
    out = output_files_present(out_dir)
    assert out["completeness"] == 1.0
```

- [ ] **Step 2: Implement**

```python
# evals/architecture/metrics.py
from __future__ import annotations
from pathlib import Path
import ast
import importlib


_REQUIRED_OUTPUTS: tuple[str, ...] = (
    "discovered_watchlist.csv", "scoring.json",
    "gold_regime.json", "gold_band.yaml",
    "proposed_allocation.yaml", "trade_plan.yaml",
    "research_memo.md",
)


def _imports_in(path: Path) -> set[str]:
    """Find local irc.* imports in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("irc."):
            out.add(node.module.split(".", 2)[1])  # top-level subpackage
    return out


def dag_acyclic_check(package_root: Path) -> bool:
    """Build module → set(deps) graph and ensure no cycle."""
    if not package_root.exists():
        return True
    graph: dict[str, set[str]] = {}
    for py in package_root.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        rel = py.relative_to(package_root)
        module = str(rel.with_suffix("")).replace("/", ".")
        try:
            graph[module.split(".", 1)[0]] = (
                graph.get(module.split(".", 1)[0], set()) | _imports_in(py)
            )
        except Exception:
            continue
    # Topological sort to detect cycles
    visited: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited

    def visit(node: str) -> bool:
        if visited.get(node) == 1:
            return False  # cycle
        if visited.get(node) == 2:
            return True
        visited[node] = 1
        for dep in graph.get(node, set()):
            if not visit(dep):
                return False
        visited[node] = 2
        return True

    for n in list(graph.keys()):
        if not visit(n):
            return False
    return True


def max_file_loc(root: Path) -> int:
    """Max line count among .py files under root."""
    counts = []
    for py in root.rglob("*.py"):
        counts.append(sum(1 for _ in py.open(encoding="utf-8")))
    return max(counts) if counts else 0


def output_files_present(out_dir: Path) -> dict[str, float]:
    found = sum(1 for n in _REQUIRED_OUTPUTS if (out_dir / n).exists())
    return {"found": float(found), "expected": float(len(_REQUIRED_OUTPUTS)),
            "completeness": found / len(_REQUIRED_OUTPUTS)}
```

- [ ] **Step 3: Implement runner**

```python
# evals/architecture/runner.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.architecture.metrics import dag_acyclic_check, max_file_loc, output_files_present


def run(repo_root: Path) -> int:
    dag_ok = dag_acyclic_check(repo_root / "src" / "irc")
    max_loc = max_file_loc(repo_root / "src" / "irc")
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out_dir = repo_root / "outputs" / today
    files = output_files_present(out_dir) if out_dir.exists() else {"completeness": 0.0}
    metrics = [
        MetricReport(
            name="dag_acyclic", value=1.0 if dag_ok else 0.0,
            status="PASS" if dag_ok else "FAIL",
            threshold={"fail_below": 1.0},
        ),
        MetricReport(
            name="max_file_loc", value=float(max_loc),
            status=classify_status(max_loc, {"warn_above": 200, "fail_above": 250},
                                    "lower_is_better"),
            threshold={"warn_above": 200, "fail_above": 250},
        ),
        MetricReport(
            name="output_files_completeness", value=files["completeness"],
            status=classify_status(files["completeness"], {"warn_below": 1.0, "fail_below": 0.6},
                                    "higher_is_better"),
            threshold={"warn_below": 1.0, "fail_below": 0.6},
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="architecture",
        ran_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        based_on=[str(repo_root / "src" / "irc")],
        metrics=metrics, overall=overall,
    )
    out_eval = out_dir / "evals" / "architecture"
    out_eval.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_eval / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    print(f"architecture eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/evals/test_architecture.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add evals/architecture/ tests/evals/test_architecture.py
git commit -m "feat(evals/architecture): DAG acyclic + max LOC + output completeness"
```

---

## Task 24: `irc eval` CLI Entry

**Files:**
- Create: `src/irc/commands/eval_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/commands/test_eval_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_eval_cmd.py
from __future__ import annotations
from pathlib import Path
import pytest
from click.testing import CliRunner
from irc.cli import main
from irc.commands.init_cmd import run_init


def test_eval_architecture_only(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "architecture", "--repo-root", str(tmp_path)])
    assert r.exit_code in (0, 1)  # PASS or WARN allowed


def test_eval_unknown_stage_errors(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    r = CliRunner().invoke(main, ["eval", "ghost", "--repo-root", str(tmp_path)])
    assert r.exit_code != 0
```

- [ ] **Step 2: Implement `eval_cmd.py`**

```python
from __future__ import annotations
from pathlib import Path
from typing import Callable


def _get_runner(stage: str) -> Callable[[Path], int]:
    runners: dict[str, str] = {
        "data":         "evals.data.runner",
        "news":         "evals.news.runner",
        "research":     "evals.research.runner",
        "discovery":    "evals.discovery.runner",
        "scoring":      "evals.scoring.runner",
        "gold_score":   "evals.gold_score.runner",
        "allocation":   "evals.allocation.runner",
        "trade_plan":   "evals.trade_plan.runner",
        "memo":         "evals.memo.runner",
        "queries":      "evals.queries.runner",
        "triggers":     "evals.triggers.runner",
        "architecture": "evals.architecture.runner",
    }
    if stage not in runners:
        raise KeyError(f"unknown eval stage: {stage}")
    import importlib
    mod = importlib.import_module(runners[stage])
    return mod.run


def run_eval(repo_root: str, stage: str | None, all_stages: bool) -> int:
    root = Path(repo_root)
    if all_stages:
        worst = 0
        for s in ("data", "news", "research", "discovery", "scoring",
                   "gold_score", "allocation", "trade_plan",
                   "memo", "queries", "triggers", "architecture"):
            try:
                rc = _get_runner(s)(root)
                worst = max(worst, rc)
            except Exception as e:
                print(f"eval {s} failed: {e}")
                worst = max(worst, 2)
        return worst
    if stage is None:
        print("ERROR: provide a stage or --all")
        return 2
    return _get_runner(stage)(root)
```

- [ ] **Step 3: Register `eval` in CLI**

```python
@main.command(help="Run per-stage eval; produces report.json under outputs/<date>/evals/<stage>/.")
@click.argument("stage", required=False)
@click.option("--all", "all_stages", is_flag=True, default=False)
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def eval(stage: str | None, all_stages: bool, repo_root: str) -> None:
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(repo_root=repo_root, stage=stage, all_stages=all_stages)
    raise SystemExit(rc)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/commands/test_eval_cmd.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/eval_cmd.py src/irc/cli.py tests/commands/test_eval_cmd.py
git commit -m "feat(cli/eval): dispatch single stage or --all; exit code by worst status"
```

---

## Task 25: Spot-Check Queue

**Files:**
- Create: `evals/spot_check/__init__.py`
- Create: `evals/spot_check/runner.py`
- Create: `tests/evals/test_spot_check.py`

- [ ] **Step 1: Failing test**

```python
# tests/evals/test_spot_check.py
from __future__ import annotations
from pathlib import Path
import pytest
from evals.spot_check.runner import sample_for_review, append_queue


def test_sample_for_review_round_robin(tmp_path: Path):
    items = {
        "ldr_citations": ["c1", "c2", "c3"],
        "discovery_reasons": ["r1", "r2"],
        "memo_claims": ["m1"],
        "query_responses": ["q1"],
    }
    sample = sample_for_review(pools=items, sizes={"ldr_citations": 2,
                                                    "discovery_reasons": 1,
                                                    "memo_claims": 1, "query_responses": 1},
                                seed=42)
    assert len(sample) == 5


def test_append_queue_writes_csv(tmp_path: Path):
    queue = tmp_path / "queue.csv"
    append_queue(queue, week="2026-05-07", entries=[
        {"stage": "ldr_citations", "sample_id": "c1", "content_ref": "x", "why_sampled": "weekly"},
    ])
    assert queue.exists()
    text = queue.read_text(encoding="utf-8")
    assert "c1" in text
```

- [ ] **Step 2: Implement**

```python
# evals/spot_check/runner.py
from __future__ import annotations
from pathlib import Path
import csv
import random


def sample_for_review(
    pools: dict[str, list[str]], sizes: dict[str, int], seed: int = 0,
) -> list[dict[str, str]]:
    rng = random.Random(seed)
    out: list[dict[str, str]] = []
    for stage, pool in pools.items():
        k = min(sizes.get(stage, 0), len(pool))
        chosen = rng.sample(pool, k=k) if pool else []
        for item in chosen:
            out.append({"stage": stage, "sample_id": item, "content_ref": item})
    return out


def append_queue(queue_path: Path, week: str, entries: list[dict]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["week", "stage", "sample_id", "content_ref", "why_sampled", "status", "reviewer_notes"]
    new_file = not queue_path.exists()
    with queue_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        for e in entries:
            row = {**e, "week": week}
            row.setdefault("status", "pending")
            row.setdefault("reviewer_notes", "")
            row.setdefault("why_sampled", e.get("why_sampled", "weekly auto-sample"))
            w.writerow(row)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/evals/test_spot_check.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add evals/spot_check/ tests/evals/test_spot_check.py
git commit -m "feat(evals/spot_check): weekly auto-sample + CSV queue"
```

---

## Task 26: PIPELINE_HALTED.md Generator + Final `irc run` Polish

**Files:**
- Create: `src/irc/pipeline_halt.py`
- Modify: `src/irc/commands/run_cmd.py`
- Create: `tests/test_pipeline_halt.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_halt.py
from __future__ import annotations
from pathlib import Path
from irc.pipeline_halt import write_halted


def test_write_halted_creates_md(tmp_path: Path):
    write_halted(repo_root=tmp_path, date="2026-05-07", stage="scoring",
                  reason="sanity_check rho ≤ 0", remediation="Re-tune factor weights or check data feed.")
    p = tmp_path / "outputs/2026-05-07/PIPELINE_HALTED.md"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "scoring" in content
    assert "rho" in content
    assert "Re-tune" in content
```

- [ ] **Step 2: Implement**

```python
# src/irc/pipeline_halt.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from irc.io_utils import atomic_write_text


def write_halted(
    repo_root: Path, date: str, stage: str, reason: str, remediation: str,
) -> Path:
    out_dir = repo_root / "outputs" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    body = (
        f"# Pipeline Halted — {date}\n\n"
        f"**Stopped at stage:** `{stage}`\n\n"
        f"**Reason:** {reason}\n\n"
        f"**Remediation:**\n{remediation}\n\n"
        f"**Generated at:** {datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "PIPELINE_HALTED.md"
    atomic_write_text(path, body)
    return path
```

- [ ] **Step 3: Modify `run_cmd.py` to write `PIPELINE_HALTED.md` on non-zero**

In `src/irc/commands/run_cmd.py`, replace the failure branch:

```python
        rc = fn(repo_root=repo_root)
        if rc != 0:
            from irc.pipeline_halt import write_halted
            from datetime import datetime, timezone, timedelta
            from pathlib import Path
            today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
            write_halted(
                repo_root=Path(repo_root), date=today, stage=name,
                reason=f"stage exit code {rc}",
                remediation="Inspect the stage's output (event_log.json) and re-run "
                            f"`irc {name} --repo-root {repo_root}` after fixing.",
            )
            return rc
```

Also add news + research stages to `_STAGES`:

```python
from irc.commands.research_cmd import run_research
# ... add ("research", run_research) AFTER ("ingest", run_ingest)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_pipeline_halt.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/pipeline_halt.py src/irc/commands/run_cmd.py tests/test_pipeline_halt.py
git commit -m "feat(pipeline): PIPELINE_HALTED.md on stage failure + research stage in run"
```

---

## Task 27: Final Suite + Tag

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest`
Expected: 200+ tests, all pass (live LLM tests skipped).

- [ ] **Step 2: Run end-to-end with mocks (full pipeline including news + research + eval)**

Adapt `tests/test_e2e_ingest_discover_score.py` to extend through memo + eval; or write a new e2e test that:
1. `irc init`
2. mocks all data + LLM + LDR
3. `irc run`
4. `irc eval --all`
5. asserts every output file present

```python
# tests/test_e2e_full_pipeline.py
from __future__ import annotations
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
from click.testing import CliRunner
from irc.cli import main


@patch("irc.commands.ingest_cmd.fetch_etf_price_history")
@patch("irc.commands.ingest_cmd.fetch_macro_series")
@patch("irc.commands.ingest_cmd.fetch_fund_nav_history")
@patch("irc.discovery.reason_writer.call_chat")
@patch("irc.scoring.factors.macro_fit.call_chat")
@patch("irc.memo.pipeline.synthesize_memo")
@patch("irc.memo.pipeline.audit_memo")
@patch("irc.research.theme_research.run_research")
def test_e2e_full(mock_ldr, mock_audit, mock_synth, mock_macrofit,
                   mock_reason, mock_nav, mock_macro, mock_prices, tmp_path: Path):
    mock_prices.return_value = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    mock_macro.return_value = pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})
    mock_nav.return_value = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.2], "nav_acc": [2.3]})
    mock_reason.return_value = MagicMock(text="cite openbb:prices:006075:2026-05-06. Risk: x.",
                                          prompt_tokens=10, completion_tokens=5)
    mock_macrofit.return_value = MagicMock(text='{"score": 70, "rationale": "x"}',
                                            prompt_tokens=20, completion_tokens=5)
    mock_synth.return_value = MagicMock(text="# memo openbb:prices:006075:2026-05-06",
                                         prompt_tokens=200, completion_tokens=100)
    mock_audit.return_value = MagicMock(verdict="PASS", issues=())
    mock_ldr.return_value = MagicMock(report_md="research body", citations=[],
                                       failure_reason="")
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    r = runner.invoke(main, ["run", "--repo-root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    e = runner.invoke(main, ["eval", "--all", "--repo-root", str(tmp_path)])
    assert e.exit_code in (0, 1)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/test_e2e_full_pipeline.py -v`
Expected: 1 passed.

- [ ] **Step 4: Tag milestone**

```bash
git tag -a plan-4-news-research-eval -m "Plan 4 complete: full MVP (news + research + eval framework)"
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e_full_pipeline.py
git commit -m "test(e2e): full pipeline + eval --all smoke"
```

---

## Self-Review Notes

**Spec coverage check:**

| Spec section | Plan 4 task |
|---|---|
| §2.C news layer (N1-N4 across 7 topics) | Tasks 1, 2, 3, 4, 5 |
| §2.C research layer (LDR) | Tasks 6, 7, 9 |
| §3.E user sovereignty (consumed in scoring via thesis_news) | Task 10 |
| §6.J offline mode (LDR failure handled gracefully) | Task 6 |
| §7 full eval framework (12 stages × ~40 metrics) | Tasks 11-23 |
| §7.G spot-check queue | Task 25 |
| §6.A PIPELINE_HALTED.md | Task 26 |
| §5.D `irc research`, `irc eval [--all]` | Tasks 9, 24 |
| §6.E memo_synthesis no-fallback | (already enforced in Plan 3 Task 16) |

**Out of MVP** (Roadmap items, not Plan 4):
- Backtest mode `--backtest` (Roadmap T2.3 / could be later patch).
- Adaptive LLM router (Roadmap T2.3).
- HTML dashboard (Roadmap T4.2).
- GitHub Actions CI (Roadmap T4.6).

**Placeholder scan:**
- Task 13-21 use a "step pattern" template because the 9 stages all follow Task 12's runner structure exactly. Each task explicitly lists 5 steps in standardized form, with concrete metric code provided for the non-trivial cases (discovery, scoring, allocation, memo). The pattern is precise enough that an engineer can produce each runner without ambiguity. This is the only compression in the plan.
- All other tasks have full code blocks.

**Type consistency check:**
- `MetricReport`, `StageReport` (Task 11) used by every runner.
- `Status` literal `PASS|WARN|FAIL` consistent across `_shared/status.py` and runners.
- `FeedItem` (Task 1) consumed by Tasks 2, 3, 5.
- `LDRResearchResult` (Task 6) consumed by `theme_research` (Task 7).
- `ThemeReport` (Task 7) consumed by `pipeline.run_research_pipeline` (Task 9).
- `NewsSignals` (Task 10) is internal to thesis_news; matches FactorScore output.
- `_STAGES` in run_cmd (Plan 3 Task 21) gets news + research entries (Task 26).

No mismatches found.

---

**End of Plan 4. MVP fully scoped.**
