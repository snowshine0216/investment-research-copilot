from __future__ import annotations

import pytest

from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES, qdii_premium_for_row


def test_qdii_asset_classes_is_frozenset_with_three_members() -> None:
    """_QDII_ASSET_CLASSES is the canonical immutable set; consumers import it."""
    assert isinstance(_QDII_ASSET_CLASSES, frozenset)
    assert _QDII_ASSET_CLASSES == frozenset({"us_etf", "hk_etf", "qdii_global"})


class _StubFetcher:
    """Records calls so tests can assert the fetcher is/isn't invoked."""

    def __init__(self, return_value: float | None = 0.0292) -> None:
        self.return_value = return_value
        self.calls: list[str] = []

    def __call__(self, symbol: str) -> float | None:
        self.calls.append(symbol)
        return self.return_value


def test_returns_none_for_non_qdii_asset_class() -> None:
    """Non-QDII rows must not stamp the field — fetcher must not be called."""
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="cn_equity_fund",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="000001",
    )
    assert out is None
    assert fetcher.calls == []


def test_returns_zero_for_qdii_off_exchange_without_calling_fetcher() -> None:
    """Off-exchange QDII feeders transact at NAV; synthetic 0.0 is correct."""
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="017641",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_returns_zero_for_qdii_global_off_exchange() -> None:
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="qdii_global",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="019547",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_returns_zero_for_hk_etf_off_exchange() -> None:
    fetcher = _StubFetcher()
    out = qdii_premium_for_row(
        asset_class="hk_etf",
        market="cn_off_exchange",
        fetcher=fetcher,
        symbol="161716",
    )
    assert out == 0.0
    assert fetcher.calls == []


def test_invokes_fetcher_for_qdii_on_exchange_us_etf() -> None:
    fetcher = _StubFetcher(return_value=0.0292)
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="513650",
    )
    assert out == 0.0292
    assert fetcher.calls == ["513650"]


def test_invokes_fetcher_for_qdii_on_exchange_hk_etf() -> None:
    fetcher = _StubFetcher(return_value=0.0079)
    out = qdii_premium_for_row(
        asset_class="hk_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="159691",
    )
    assert out == 0.0079
    assert fetcher.calls == ["159691"]


def test_propagates_none_from_fetcher() -> None:
    """When AkShare returns no row, the resolver propagates None."""
    fetcher = _StubFetcher(return_value=None)
    out = qdii_premium_for_row(
        asset_class="us_etf",
        market="cn_on_exchange",
        fetcher=fetcher,
        symbol="999999",
    )
    assert out is None
    assert fetcher.calls == ["999999"]
