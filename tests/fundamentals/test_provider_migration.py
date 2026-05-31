"""Locks: routing the four call-sites through AkShareProvider yields output
byte-identical to the pre-migration direct calls on the same stubbed _ak_call.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals import akshare_index_valuation
from irc.fundamentals.provider import AkShareProvider
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.types import LookthroughTarget
from irc.opportunity.inputs_loader import _index_valuation_metrics

_PE_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": [12.1]})
_PB_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "市净率": [1.31]})


def test_index_metrics_via_provider_matches_pre_migration() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake):
        out = _index_valuation_metrics("csi300", provider=AkShareProvider())
    # Same as fetch_cn_index_valuation("csi300").pe_ttm / .pb / .dividend_yield.
    assert out == (12.1, 1.31, None)


def test_index_metrics_unknown_key_does_not_call_ak() -> None:
    with patch.object(akshare_index_valuation, "_ak_call") as mocked:
        out = _index_valuation_metrics("not_a_broad_index", provider=AkShareProvider())
    assert out == (None, None, None)
    mocked.assert_not_called()


class _RecordingProvider:
    def __init__(self):
        self.filing_calls: list[str] = []
        self.broker_calls: list[str] = []

    def fetch_filing_digest(self, symbol):
        self.filing_calls.append(symbol)
        return None

    def fetch_broker_reports(self, symbol, *, days=90, max_reports=20):
        self.broker_calls.append(symbol)
        return ()

    def fetch_index_valuation(self, index_key):
        return None


def test_build_snapshot_threads_provider_to_constituent_fetch() -> None:
    rec = _RecordingProvider()
    target = LookthroughTarget(
        kind="active_fund", key="005827", display_cn="易方达蓝筹",
        provider_symbol="005827",
    )
    with patch("irc.fundamentals.snapshot.fetch_cn_etf_holdings") as holdings, patch(
        "irc.fundamentals.snapshot._fetch_active_fund_level_evidence",
        return_value=((), ()),
    ), patch(
        "irc.fundamentals.snapshot.fetch_cn_stock_news", return_value=(),
    ):
        from irc.fundamentals.types import FundHolding, HoldingsResult
        holdings.return_value = HoldingsResult(
            constituents=(FundHolding(
                symbol="600519.SH", name_cn="贵州茅台", weight_pct=9.0,
                exchange="SH", provider_symbol="600519",
            ),),
            source_report_date="2025-03-31",
            source_report_quarter="2025Q1",
        )
        build_snapshot(target, top_n=1, provider=rec)
    assert "600519.SH" in rec.filing_calls
    assert "600519.SH" in rec.broker_calls
