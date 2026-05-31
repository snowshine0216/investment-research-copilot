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
from irc.settings import Settings


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


def _try(call):
    """Run `call`, return its value; on any exception return the sentinel `None`.

    Sentinel-agnostic: callers compare the result against their miss value.
    """
    try:
        return call()
    except Exception:
        return None


class FallbackProvider:
    """Per-method: try `primary`; on a miss/exception fall back to `secondary`.

    A "miss" is `None` (digest/index) or `()` (brokers). Both-miss returns the
    primary miss value. Never raises (ADR 0009 degrade-to-None family).
    """

    def __init__(
        self,
        primary: CnFundamentalsProvider,
        secondary: CnFundamentalsProvider,
    ) -> None:
        self._primary = primary
        self._secondary = secondary

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        primary = _try(lambda: self._primary.fetch_filing_digest(symbol))
        if primary is not None:
            return primary
        return _try(lambda: self._secondary.fetch_filing_digest(symbol))

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        primary = _try(
            lambda: self._primary.fetch_broker_reports(
                symbol, days=days, max_reports=max_reports
            )
        )
        if primary:
            return primary
        secondary = _try(
            lambda: self._secondary.fetch_broker_reports(
                symbol, days=days, max_reports=max_reports
            )
        )
        return secondary or ()

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        primary = _try(lambda: self._primary.fetch_index_valuation(index_key))
        if primary is not None:
            return primary
        return _try(lambda: self._secondary.fetch_index_valuation(index_key))


def default_cn_provider() -> CnFundamentalsProvider:
    """Construction edge: read the token from `.env` and pick the provider.

    No token → `AkShareProvider()` alone (byte-identical to pre-003). With a
    token → `FallbackProvider(AkShareProvider(), TushareProvider(token))`.
    `TushareProvider` is imported lazily so this module never imports tushare.
    """
    token = Settings().tushare_token.get_secret_value().strip()
    if not token:
        return AkShareProvider()
    from irc.fundamentals.tushare_provider import TushareProvider

    return FallbackProvider(AkShareProvider(), TushareProvider(token))
