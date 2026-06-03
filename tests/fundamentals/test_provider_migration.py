"""Locks: routing the call-sites through AkShareProvider yields output
byte-identical to the pre-migration direct calls on the same stubbed _ak_call.

Note (item 001 / R3, design spec §4.3): the `_index_valuation_metrics` call-site
no longer routes through the provider — it reads the cached `index_valuation_history`
DuckDB table (live provider fetch removed). The two former
`_index_valuation_metrics`-via-provider locks were therefore retired here; the new
cached-read contract is covered by `tests/opportunity/test_inputs_loader.py`, and
`AkShareProvider.fetch_index_valuation` itself retains its own coverage in
`tests/fundamentals/test_provider.py` (R4 — the provider method stays a valid,
tested seam). The remaining lock below covers the snapshot constituent-fetch seam,
which is unchanged by item 001.
"""
from __future__ import annotations

from unittest.mock import patch

from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.types import LookthroughTarget


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
