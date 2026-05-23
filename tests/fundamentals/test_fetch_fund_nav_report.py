"""Unit tests for fetch_fund_nav_report (mocked _ak_call)."""
from __future__ import annotations

import datetime as _dt
from unittest.mock import patch

import pandas as pd

from irc.fundamentals.akshare_fundamentals import fetch_fund_nav_report
from irc.fundamentals.types import FundNavReport


def _nav_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "净值日期": [
            _dt.date(2026, 3, 13),
            _dt.date(2026, 3, 14),
            _dt.date(2026, 3, 15),
        ],
        "单位净值": [4.5400, 4.5500, 4.5678],
        "日增长率": ["0.12", "0.22", "0.39"],
    })


def test_fetch_fund_nav_report_happy_path() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        out = fetch_fund_nav_report("518880")
    assert mocked.call_args[0][0] == "fund_open_fund_info_em"
    assert mocked.call_args[1] == {
        "symbol": "518880", "indicator": "单位净值走势",
    }
    assert isinstance(out, FundNavReport)
    assert out.fund_id == "518880"
    assert out.latest_nav == 4.5678
    assert out.latest_nav_date == "2026-03-15"
    assert out.source_report_quarter == "2026Q1"
    assert out.nav_history[-1] == ("2026-03-15", 4.5678)
    assert len(out.nav_history) == 3


def test_fetch_fund_nav_report_converts_datetime_date_to_iso() -> None:
    """`净值日期` arrives as datetime.date; adapter normalises via .isoformat()."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        out = fetch_fund_nav_report("518880")
    for d, _v in out.nav_history:
        assert isinstance(d, str)
        assert len(d) == 10  # YYYY-MM-DD


def test_fetch_fund_nav_report_empty_frame_returns_none() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame()
        out = fetch_fund_nav_report("999999")
    assert out is None


def test_fetch_fund_nav_report_missing_columns_returns_none() -> None:
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = pd.DataFrame({"foo": [1, 2]})
        out = fetch_fund_nav_report("518880")
    assert out is None


def test_fetch_fund_nav_report_adapter_exception_returns_none() -> None:
    """Adapter never raises (matches fetch_cn_filing_digest contract)."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.side_effect = ConnectionError("eastmoney 502")
        out = fetch_fund_nav_report("518880")
    assert out is None


def test_fetch_fund_nav_report_uses_only_nav_indicator() -> None:
    """F5 invariant: adapter must NEVER consult '基金概况'."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        fetch_fund_nav_report("518880")
    indicators = [
        kw.get("indicator") for _args, kw in mocked.call_args_list
    ]
    assert "基金概况" not in indicators
    assert indicators == ["单位净值走势"]


def test_fetch_fund_nav_report_string_date_passthrough() -> None:
    """If AkShare returns 净值日期 as str instead of date, adapter still works."""
    df = pd.DataFrame({
        "净值日期": ["2026-03-13", "2026-03-14", "2026-03-15"],
        "单位净值": [4.5400, 4.5500, 4.5678],
        "日增长率": ["0.12", "0.22", "0.39"],
    })
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = df
        out = fetch_fund_nav_report("518880")
    assert out is not None
    assert out.latest_nav_date == "2026-03-15"


def test_fetch_fund_nav_report_fund_name_fallback_when_absent() -> None:
    """The NAV走势 indicator does NOT carry fund_name; adapter sets it to fund_id."""
    with patch(
        "irc.fundamentals.akshare_fundamentals._ak_call"
    ) as mocked:
        mocked.return_value = _nav_frame()
        out = fetch_fund_nav_report("518880")
    assert out is not None
    # The adapter falls back to fund_id when no fund_name column is present.
    assert out.fund_name == "518880"
