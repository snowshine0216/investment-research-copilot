from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

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


def test_fetch_fund_nav_history_tolerates_unit_nav_without_accumulated_nav() -> None:
    fake = pd.DataFrame({
        "净值日期": ["2026-05-07"],
        "单位净值": [1.23],
        "日增长率": ["0.10%"],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_fund_nav_history("510300")

    assert mocked.call_args[1] == {"symbol": "510300", "indicator": "单位净值走势"}
    assert list(out.columns) == ["date", "nav", "nav_acc"]
    assert out.loc[0, "date"] == "2026-05-07"
    assert out.loc[0, "nav"] == 1.23
    assert pd.isna(out.loc[0, "nav_acc"])


def test_fetch_fund_metadata() -> None:
    basic = pd.DataFrame({
        "item": ["基金代码", "基金名称", "基金类型", "最新规模", "成立时间"],
        "value": ["006075", "易方达标普500", "QDII", "200亿", "2018-03-26"],
    })
    fees = pd.DataFrame({
        "费用类型": ["管理费率", "托管费率", "销售服务费率"],
        "费率": ["0.50%", "0.10%", "0.00%"],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.side_effect = [basic, fees]
        out = fetch_fund_metadata("006075")

    assert out["fund_code"] == "006075"
    assert out["expense_ratio"] == 0.0060
    assert out["inception_date"] == "2018-03-26"
    assert out["aum_text"] == "200亿"
    assert [c.args[0] for c in mocked.call_args_list] == [
        "fund_individual_basic_info_xq",
        "fund_fee_em",
    ]


def test_fetch_fund_metadata_sums_operating_fees_in_one_row() -> None:
    basic = pd.DataFrame({
        "item": ["基金代码", "基金名称", "基金类型", "最新规模", "成立时间"],
        "value": ["006075", "易方达标普500", "QDII", "200亿", "2018-03-26"],
    })
    fees = pd.DataFrame([{
        "运作费用": "管理费率 0.50%; 托管费率 0.10%; 销售服务费率 0.00%",
    }])
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.side_effect = [basic, fees]
        out = fetch_fund_metadata("006075")

    assert out["expense_ratio"] == 0.0060


def test_fetch_fund_metadata_raises_for_unknown_code() -> None:
    fake = pd.DataFrame({
        "item": ["基金代码", "基金名称"],
        "value": ["006075", "易方达标普500"],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        with pytest.raises(ValueError, match="not found"):
            fetch_fund_metadata("999999")


def test_fetch_etf_metadata() -> None:
    fake = pd.DataFrame([{"代码": "sh510300", "名称": "沪深300ETF"}])
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_etf_metadata("510300")

    assert out == {"ticker": "510300", "name_cn": "沪深300ETF"}
