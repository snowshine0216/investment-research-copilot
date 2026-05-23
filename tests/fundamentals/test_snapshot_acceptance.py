"""Spec §Acceptance criteria 6, 7, 8, 9, 10, 11, 29, 30, 31."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals import snapshot as snap_mod
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.types import (
    ActiveFundSnapshot, BrokerReport, FilingDigest, FundHolding,
    HoldingsResult, NewsItem,
)
from irc.opportunity.types import LookthroughTarget


def _cn_holdings(symbols):
    return HoldingsResult(
        constituents=tuple(
            FundHolding(s, s, 10.0 - i, "SH" if s.startswith("6") else "SZ", s)
            for i, s in enumerate(symbols)
        ),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )


def test_g6_a_full_success_30_evidence_entries(monkeypatch) -> None:
    """Spec §29 G6 (a): 10-stock fund, all adapters succeed."""
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: _cn_holdings([f"60001{i}" for i in range(10)]),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_filing_digest",
        lambda s: FilingDigest(
            symbol=s, fiscal_period="2024Q1", filed_at_iso="2024-04-15",
            revenue_yoy=0.10, net_income_yoy=0.12, gross_margin=0.45,
            source_url=f"https://x/{s}",
        ),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_broker_reports",
        lambda s: (BrokerReport(
            symbol=s, broker="中信", rating="买入", target_price=100.0,
            published_iso="2024-04-10", title="买入", source_url="https://x/b",
        ),),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_stock_news",
        lambda s, top_k=3: (NewsItem(s, "新品", "https://x", "2024-04-15", "", "stock_news_em"),),
    )
    target = LookthroughTarget("active_fund", "fund_005827", "fund", "005827")
    snap = build_snapshot(target, top_n=10)
    assert isinstance(snap, ActiveFundSnapshot)
    assert len(snap.constituent_analyses) == 10
    total = sum(len(c.evidence) for c in snap.constituent_analyses)
    assert total == 30  # 10 filing + 10 broker + 10 news


def test_g6_b_partial_holdings_6_to_10_all_empty(monkeypatch) -> None:
    """Spec §30 G6 (b): holdings 6–10 all have filing_empty + broker_empty + news_empty."""
    symbols = [f"6000{i:02d}" for i in range(10)]
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: _cn_holdings(symbols),
    )

    def selective_filing(s):
        idx = int(s[-2:])
        if idx >= 5:
            return None
        return FilingDigest(s, "2024Q1", "2024-04-15", 0.1, 0.1, 0.3, "", "")

    monkeypatch.setattr(snap_mod, "fetch_cn_filing_digest", selective_filing)

    def selective_brokers(s):
        idx = int(s[-2:])
        if idx >= 5:
            return ()
        return (BrokerReport(s, "中信", "买入", None, "2024-04-10", "x", "https://x"),)

    monkeypatch.setattr(snap_mod, "fetch_cn_broker_reports", selective_brokers)

    def selective_news(s, top_k=3):
        idx = int(s[-2:])
        if idx >= 5:
            return ()
        return (NewsItem(s, "x", "https://x", "2024-04-15", "", "stock_news_em"),)

    monkeypatch.setattr(snap_mod, "fetch_cn_stock_news", selective_news)
    target = LookthroughTarget("active_fund", "fund_x", "fund", "005827")
    snap = build_snapshot(target, top_n=10)
    assert len(snap.constituent_analyses) == 10
    empties = [c for c in snap.constituent_analyses if not c.evidence]
    assert len(empties) == 5
    for c in empties:
        assert any(r.startswith("filing_empty:") for r in c.failure_reasons)
        assert any(r.startswith("broker_empty:") for r in c.failure_reasons)
        assert any(r.startswith("news_empty:") for r in c.failure_reasons)


def test_g6_c_news_carries_constituent_scope_and_information_kind(monkeypatch) -> None:
    """Spec §31 G6 (c): structured news evidence shape."""
    monkeypatch.setattr(
        snap_mod, "fetch_cn_etf_holdings",
        lambda sym, top_n=10: _cn_holdings(["600519"]),
    )
    monkeypatch.setattr(snap_mod, "fetch_cn_filing_digest", lambda s: None)
    monkeypatch.setattr(snap_mod, "fetch_cn_broker_reports", lambda s: ())
    monkeypatch.setattr(
        snap_mod, "fetch_cn_stock_news",
        lambda s, top_k=3: (NewsItem(s, "新品", "https://x", "2024-04-15", "", "stock_news_em"),),
    )
    target = LookthroughTarget("active_fund", "fund_x", "fund", "005827")
    snap = build_snapshot(target, top_n=1)
    news_ev = [e for e in snap.constituent_analyses[0].evidence if e.type == "news"]
    assert len(news_ev) == 1
    assert news_ev[0].scope == "constituent"
    assert news_ev[0].citation_kind == "information"
    assert news_ev[0].constituent_key == "600519"
    assert snap.fund_level_failure_reasons == ()
