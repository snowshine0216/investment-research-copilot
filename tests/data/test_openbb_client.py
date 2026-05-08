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
