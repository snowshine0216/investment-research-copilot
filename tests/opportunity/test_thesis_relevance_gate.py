"""Thesis intact requires a trusted-tier citation (item 002, 2026-05-19).

Adversarial review §A2: thesis_cards.yaml had 25/25 cards with
thesis_state=intact, every one citing the same two URLs (a software
report and a mysteel republisher). citation_count alone is not enough.
"""
from __future__ import annotations

from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport


def _report(citations: list[Citation]) -> ThemeReport:
    return ThemeReport(
        theme="gold_drivers",
        query="gold drivers query",
        locale="en",
        report_md="body",
        citations=citations,
        failure_reason="",
        provider_failures=(),
    )


def test_intact_requires_one_trusted_citation() -> None:
    citations = [
        Citation(index=1, title="Reuters: Fed minutes hawkish",
                 url="https://www.reuters.com/x", published_iso="2026-05-19"),
        Citation(index=2, title="ISW assessment",
                 url="https://isw.pub/post/abc", published_iso="2026-05-19"),
        Citation(index=3, title="some blog",
                 url="https://news.mysteel.com/x", published_iso="2026-05-19"),
    ]
    state, reason, _, _ = derive_thesis_from_evidence(
        snapshot=None, theme_report=_report(citations), asset_class="gold",
    )
    assert state == "intact"
    assert "一级来源" in reason


def test_all_republisher_citations_yields_evidence_insufficient() -> None:
    citations = [
        Citation(index=1, title="央行开展10亿元7天逆回购操作-我的钢铁网",
                 url="https://news.mysteel.com/a/abc.html",
                 published_iso="2026-05-18"),
        Citation(index=2, title="2026年用户研究软件行业报告",
                 url="https://www.chinabgao.com/k/yhyjrj.html",
                 published_iso="2026-05-05"),
        Citation(index=3, title="某新闻聚合",
                 url="https://m.163.com/dy/article/abc",
                 published_iso="2026-05-18"),
    ]
    state, reason, _, _ = derive_thesis_from_evidence(
        snapshot=None, theme_report=_report(citations), asset_class="gold",
    )
    assert state == "evidence_insufficient"
    assert "次级转载源" in reason


def test_below_min_citations_is_evidence_insufficient() -> None:
    citations = [
        Citation(index=1, title="Reuters article",
                 url="https://www.reuters.com/x", published_iso="2026-05-19"),
    ]
    state, _, _, _ = derive_thesis_from_evidence(
        snapshot=None, theme_report=_report(citations), asset_class="gold",
    )
    assert state == "evidence_insufficient"


def test_unknown_tier_alone_is_evidence_insufficient() -> None:
    citations = [
        Citation(index=1, title="unknown blog",
                 url="https://some-random-blog.example.com/post1",
                 published_iso="2026-05-19"),
        Citation(index=2, title="another unknown",
                 url="https://other-blog.example.org/post2",
                 published_iso="2026-05-19"),
        Citation(index=3, title="third unknown",
                 url="https://third.example.net/post3",
                 published_iso="2026-05-19"),
    ]
    state, _, _, _ = derive_thesis_from_evidence(
        snapshot=None, theme_report=_report(citations), asset_class="gold",
    )
    assert state == "evidence_insufficient"
