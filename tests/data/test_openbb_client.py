from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from irc.data.openbb_client import (
    OPENBB_PROVIDER_DEFAULT,
    fetch_etf_price_history,
    fetch_macro_series,
)


def test_fetch_etf_price_history_calls_correct_provider() -> None:
    fake_df = pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.20, 4.22],
        "high": [4.25, 4.30],
        "low": [4.18, 4.20],
        "close": [4.22, 4.28],
        "volume": [1.0e8, 1.1e8],
    })
    fake_obj = MagicMock()
    fake_obj.to_df.return_value = fake_df

    with patch("irc.data.openbb_client._call_obb") as mocked:
        mocked.return_value = fake_obj
        out = fetch_etf_price_history(ticker="VTI", start="2026-05-01", end="2026-05-07")

    mocked.assert_called_once()
    args, kwargs = mocked.call_args
    assert args[0] == "equity.price.historical"
    assert kwargs["symbol"] == "VTI"
    assert kwargs["provider"] == OPENBB_PROVIDER_DEFAULT
    assert len(out) == 2
    assert "close" in out.columns


def test_fetch_etf_price_history_routes_cn_ticker_to_akshare() -> None:
    fake_df = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    with patch("irc.data.openbb_client.fetch_etf_price_history_akshare", return_value=fake_df) as ak_mock, \
         patch("irc.data.openbb_client._call_obb") as obb_mock:
        out = fetch_etf_price_history(ticker="513500", start="2026-04-01", end="2026-05-07")
    ak_mock.assert_called_once_with("513500", "2026-04-01", "2026-05-07")
    obb_mock.assert_not_called()
    assert "close" in out.columns


def test_fetch_etf_price_history_forwards_cn_eastmoney_controls() -> None:
    fake_df = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    exhausted = MagicMock()
    with patch("irc.data.openbb_client.fetch_etf_price_history_akshare", return_value=fake_df) as ak_mock, \
         patch("irc.data.openbb_client._call_obb") as obb_mock:
        out = fetch_etf_price_history(
            ticker="513500",
            start="2026-04-01",
            end="2026-05-07",
            skip_cn_eastmoney=True,
            on_cn_eastmoney_exhausted=exhausted,
        )

    ak_mock.assert_called_once_with(
        "513500",
        "2026-04-01",
        "2026-05-07",
        skip_eastmoney=True,
        on_eastmoney_exhausted=exhausted,
    )
    obb_mock.assert_not_called()
    assert "close" in out.columns


def test_fetch_etf_price_history_cn_ticker_raises_when_akshare_fails() -> None:
    """yfinance heavily rate-limits CN ETFs (`513500.SS` etc.) — falling back
    to it on akshare failure burns the rate-limit budget across all CN tickers
    in the same run. For CN tickers, akshare is canonical: if it fails, raise
    fast and let the per-instrument handler in ingest_cmd skip this one."""
    import pytest
    with patch("irc.data.openbb_client.fetch_etf_price_history_akshare",
               side_effect=RuntimeError("akshare down")), \
         patch("irc.data.openbb_client._call_obb") as obb_mock:
        with pytest.raises(RuntimeError, match="akshare down"):
            fetch_etf_price_history(ticker="513500", start="2026-04-01", end="2026-05-07")
    obb_mock.assert_not_called()


def test_fetch_etf_price_history_non_cn_does_not_use_cn_akshare_fallback() -> None:
    """The akshare ETF fallback is for 6-digit CN exchange tickers. If
    OpenBB fails for SPY/VTI, retrying with CN-specific EastMoney/Sina symbol
    rules only hides the real provider failure."""
    import pytest

    with patch("irc.data.openbb_client._call_obb", side_effect=RuntimeError("openbb down")), \
         patch("irc.data.openbb_client.fetch_etf_price_history_akshare") as ak_mock:
        with pytest.raises(RuntimeError, match="openbb down"):
            fetch_etf_price_history(ticker="SPY", start="2026-04-01", end="2026-05-07")

    ak_mock.assert_not_called()


def test_fetch_macro_series_falls_back_to_akshare_on_openbb_failure() -> None:
    fake_df = pd.DataFrame({"date": [date(2026, 5, 6)], "value": [4.30]})
    with patch("irc.data.openbb_client._call_obb", side_effect=RuntimeError("missing creds")), \
         patch("irc.data.openbb_client.fetch_macro_series_akshare", return_value=fake_df) as ak_mock:
        out = fetch_macro_series(series_id="DGS10", start="2026-01-01", end="2026-05-01")
    ak_mock.assert_called_once_with("DGS10", "2026-01-01", "2026-05-01")
    assert list(out.columns) == ["date", "value"]


def test_fetch_macro_series_returns_dataframe() -> None:
    fake_df = pd.DataFrame({
        "date": [date(2026, 4, 30)],
        "value": [1.65],
    })
    fake_obj = MagicMock()
    fake_obj.to_df.return_value = fake_df

    with patch("irc.data.openbb_client._call_obb") as mocked:
        mocked.return_value = fake_obj
        out = fetch_macro_series(series_id="DGS10", start="2026-04-01", end="2026-04-30")

    assert "value" in out.columns
    assert mocked.call_args[0][0] == "economy.fred_series"
