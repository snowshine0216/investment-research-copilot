"""Pluggable CN-fundamentals provider seam (ADR 0010, item 003).

A structural `Protocol` over the three CN-fundamentals fetch surfaces, reusing
their existing frozen return types. `AkShareProvider` delegates VERBATIM to the
unchanged module functions (no parsing re-implemented), so the token-absent path
is byte-identical to pre-003. `FallbackProvider` composes two providers per
method (try primary, fill misses with secondary) and NEVER raises.

Tushare lives in `tushare_provider.py` (imported lazily by `default_cn_provider`)
so this module carries no `tushare` import. See docs/adr/0010-...md.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from irc.fundamentals.akshare_filing import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
)
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport, FilingDigest


@runtime_checkable
class CnFundamentalsProvider(Protocol):
    """Three CN-fundamentals fetch surfaces. Reuses existing return types."""

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None: ...

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]: ...

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None: ...


class AkShareProvider:
    """Delegates each method verbatim to the existing module function.

    Stateless. Reproduces today's behavior byte-for-byte (no parsing here).
    """

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        return fetch_cn_filing_digest(symbol)

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        return fetch_cn_broker_reports(symbol, days=days, max_reports=max_reports)

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        return fetch_cn_index_valuation(index_key)
