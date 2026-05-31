"""Tushare provider (item 003). Phase A stub — replaced in Phase C."""
from __future__ import annotations

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport, FilingDigest


class TushareProvider:
    def __init__(self, token: str) -> None:
        self._token = token

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        return None

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        return ()

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        return None
