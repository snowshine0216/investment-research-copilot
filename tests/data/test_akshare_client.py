from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.data.akshare_client import (
    fetch_etf_metadata,
    fetch_fund_metadata,
    fetch_fund_nav_history,
)


def test_fetch_fund_nav_history() -> None:
    fake = pd.DataFrame({
        "净值日期": ["2026-05-06", "2026-05-07"],
        "单位净值": [1.234, 1.245],
        "累计净值": [2.345, 2.356],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_fund_nav_history("006075")

    assert mocked.call_args[0][0] == "fund_open_fund_info_em"
    assert list(out.columns) == ["date", "nav", "nav_acc"]
    assert out.iloc[0]["nav"] == 1.234


def test_fetch_fund_metadata() -> None:
    fake = pd.DataFrame([
        {
            "基金代码": "006075",
            "基金简称": "易方达标普500",
            "基金类型": "QDII",
            "基金规模": "200亿",
            "成立日期": "2018-03-26",
            "费率": 0.0060,
        },
    ])
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_fund_metadata("006075")

    assert out["fund_code"] == "006075"
    assert out["expense_ratio"] == 0.0060
    assert out["inception_date"] == "2018-03-26"
