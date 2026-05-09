from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from irc.data.akshare_client import (
    _expense_ratio_from_fee_table,
    _item_value_dict,
    _ratios_from_text,
    fetch_etf_metadata,
    fetch_etf_metadata_em,
    fetch_etf_price_history_akshare,
    fetch_fund_metadata,
    fetch_fund_nav_history,
    fetch_macro_series_akshare,
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


def test_fetch_fund_metadata_propagates_xq_failure() -> None:
    """XueQiu is the only akshare path with individual fund metadata. When it
    fails (auth/rate limit), callers must see the exception so they can skip
    the instrument with a warning. There is no working EM equivalent in
    akshare 1.18.60 — `fund_individual_basic_info_em` does not exist."""
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.side_effect = KeyError("data")
        with pytest.raises(KeyError):
            fetch_fund_metadata("006075")
    assert [c.args[0] for c in mocked.call_args_list] == ["fund_individual_basic_info_xq"]


def test_item_value_dict_handles_em_style_columns() -> None:
    df = pd.DataFrame({"项目": ["基金代码", "基金名称"], "数据": ["006075", "易方达"]})
    result = _item_value_dict(df)
    assert result == {"基金代码": "006075", "基金名称": "易方达"}


_EM_PROFILE_HTML_513500 = """
<table class="info w790">
<tr><th>基金全称</th><td>博时标普500交易型开放式指数证券投资基金</td>
    <th>基金简称</th><td>标普500ETF博时</td></tr>
<tr><th>基金代码</th><td>513500（主代码）<th>基金类型</th><td>指数型-海外股票</td></tr>
<tr><th>发行日期</th><td>2013年11月04日</td>
    <th>成立日期/规模</th><td>2013年12月05日 / 5.650亿份</td></tr>
<tr><th>净资产规模</th><td>209.41亿元（截止至：2026年03月31日）</td>
    <th>份额规模</th><td>98.1064亿份</td></tr>
<tr><th>管理费率</th><td>0.60%（每年）</td>
    <th>托管费率</th><td>0.20%（每年）</td></tr>
<tr><th>销售服务费率</th><td>---（每年）</td>
    <th>最高认购费率</th><td>0.80%</td></tr>
</table>
"""


def test_fetch_etf_metadata_em_parses_eastmoney_profile() -> None:
    with patch("irc.data.akshare_client._http_get", return_value=_EM_PROFILE_HTML_513500):
        out = fetch_etf_metadata_em("513500")
    assert out["fund_code"] == "513500"
    assert out["name_cn"] == "标普500ETF博时"
    assert out["inception_date"] == "2013-12-05"
    assert out["aum_text"] == "209.41亿元"
    assert out["expense_ratio"] == pytest.approx(0.0060 + 0.0020)
    assert out["manager_tenure_years"] is None


def test_fetch_etf_metadata_em_raises_when_page_has_no_metadata() -> None:
    with patch("irc.data.akshare_client._http_get", return_value="<html>not found</html>"):
        with pytest.raises(ValueError, match="not found"):
            fetch_etf_metadata_em("999999")


def test_http_get_retries_on_timeout_then_succeeds() -> None:
    import requests
    from irc.data import akshare_client as ak_mod

    call_count = {"n": 0}

    def fake_get(url, headers, timeout):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise requests.exceptions.Timeout("read timeout")
        resp = MagicMock()
        resp.text = "<html>ok</html>"
        resp.raise_for_status = MagicMock()
        return resp

    with patch.object(ak_mod, "_http_get", wraps=ak_mod._http_get) as _wrapped, \
         patch("requests.get", side_effect=fake_get), \
         patch("time.sleep"):  # don't actually sleep in tests
        out = ak_mod._http_get("https://example/", {}, timeout=1)

    assert out == "<html>ok</html>"
    assert call_count["n"] == 2  # 1 timeout + 1 success


def test_http_get_raises_after_exhausting_retries() -> None:
    import requests
    from irc.data import akshare_client as ak_mod

    with patch("requests.get", side_effect=requests.exceptions.Timeout("nope")), \
         patch("time.sleep"):
        with pytest.raises(requests.exceptions.Timeout):
            ak_mod._http_get("https://example/", {}, timeout=1, attempts=3, backoff_s=0.0)


def test_fetch_etf_metadata_em_handles_thousand_separator_in_aum() -> None:
    html = (
        "<table><tr><th>基金简称</th><td>沪深300ETF华泰柏瑞</td>"
        "<th>成立日期/规模</th><td>2012年05月04日 / 329亿份</td></tr>"
        "<tr><th>净资产规模</th><td>1,999.14亿元</td>"
        "<th>管理费率</th><td>0.15%（每年）</td>"
        "<th>托管费率</th><td>0.05%（每年）</td></tr></table>"
    )
    with patch("irc.data.akshare_client._http_get", return_value=html):
        out = fetch_etf_metadata_em("510300")
    assert out["aum_text"] == "1999.14亿元"


def test_fetch_etf_price_history_akshare_normalizes_columns() -> None:
    fake = pd.DataFrame({
        "日期": ["2026-04-30", "2026-05-06"],
        "开盘": [2.42, 2.455], "收盘": [2.419, 2.454],
        "最高": [2.431, 2.463], "最低": [2.40, 2.45],
        "成交量": [1.0e8, 1.1e8], "成交额": [1.0, 1.1],
        "振幅": [0.83, 0.62], "涨跌幅": [0.33, 1.45],
        "涨跌额": [0.008, 0.035], "换手率": [1.05, 1.66],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_etf_price_history_akshare("513500", start="2026-04-01", end="2026-05-07")
    assert mocked.call_args.args[0] == "fund_etf_hist_em"
    assert mocked.call_args.kwargs == {
        "symbol": "513500", "period": "daily",
        "start_date": "20260401", "end_date": "20260507", "adjust": "qfq",
    }
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_fetch_etf_price_history_akshare_retries_transient_connection_errors() -> None:
    """EastMoney occasionally drops connections mid-handshake. A single
    RemoteDisconnected used to crash the whole ingest because yfinance
    fallback is rate-limited; we now retry within akshare itself."""
    fake = pd.DataFrame({
        "日期": ["2026-05-06"],
        "开盘": [2.455], "收盘": [2.454],
        "最高": [2.463], "最低": [2.45],
        "成交量": [1.1e8],
    })
    transient = ConnectionError("Connection aborted: Remote end closed connection without response")
    with patch("irc.data.akshare_client._ak_call") as mocked, \
         patch("irc.data.akshare_client._sleep") as slept:
        mocked.side_effect = [transient, transient, fake]
        out = fetch_etf_price_history_akshare("513500", start="2026-04-01", end="2026-05-07")
    assert mocked.call_count == 3
    assert slept.call_count == 2
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_fetch_etf_price_history_akshare_does_not_retry_value_errors() -> None:
    """Non-network errors should fail fast — retrying a malformed ticker
    is just three identical 4xx-equivalent responses."""
    with patch("irc.data.akshare_client._ak_call") as mocked, \
         patch("irc.data.akshare_client._sleep") as slept:
        mocked.side_effect = ValueError("symbol unknown")
        with pytest.raises(ValueError):
            fetch_etf_price_history_akshare("999999", start="2026-04-01", end="2026-05-07")
    assert mocked.call_count == 1
    assert slept.call_count == 0


def test_fetch_etf_price_history_falls_back_to_sina_when_eastmoney_exhausts_retries() -> None:
    """EastMoney's push2his.* host gets blocked at random for non-CN-mainland
    IPs. After EM retries are exhausted, fall back to Sina finance which uses
    a different host (finance.sina.com.cn) — proven independent uptime."""
    sina_full = pd.DataFrame({
        "date": ["2026-03-15", "2026-04-30", "2026-05-06", "2026-06-01"],
        "open": [2.40, 2.42, 2.45, 2.50], "high": [2.42, 2.43, 2.46, 2.51],
        "low":  [2.39, 2.41, 2.44, 2.49], "close": [2.41, 2.42, 2.45, 2.50],
        "volume": [1.0e8, 1.0e8, 1.1e8, 1.2e8], "amount": [1, 1, 1, 1],
    })
    transient = ConnectionError("Connection aborted: push2his blocked")

    def _ak_call_side_effect(fn_name, **kwargs):
        if fn_name == "fund_etf_hist_em":
            raise transient
        if fn_name == "fund_etf_hist_sina":
            return sina_full
        raise AssertionError(f"unexpected ak_call: {fn_name}")

    with patch("irc.data.akshare_client._ak_call", side_effect=_ak_call_side_effect) as mocked, \
         patch("irc.data.akshare_client._sleep"):
        out = fetch_etf_price_history_akshare("513500", start="2026-04-01", end="2026-05-07")
    # 3 EM attempts + 1 sina = 4 total
    assert mocked.call_count == 4
    em_calls = [c for c in mocked.call_args_list if c.args[0] == "fund_etf_hist_em"]
    sina_calls = [c for c in mocked.call_args_list if c.args[0] == "fund_etf_hist_sina"]
    assert len(em_calls) == 3
    assert len(sina_calls) == 1
    # Sina symbol is sh/sz prefixed — 513500 starts with 5 → sh
    assert sina_calls[0].kwargs["symbol"] == "sh513500"
    # Date range filter applied client-side — only 2026-04-30 and 2026-05-06 fall inside
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert str(out.iloc[0]["date"]) == "2026-04-30"
    assert str(out.iloc[-1]["date"]) == "2026-05-06"


def test_fetch_etf_price_history_sina_symbol_prefix_for_shenzhen_ticker() -> None:
    """Shenzhen tickers start with 0/1/2/3 — must map to `sz` prefix."""
    sina_full = pd.DataFrame({
        "date": ["2026-05-06"], "open": [1.0], "high": [1.0], "low": [1.0],
        "close": [1.0], "volume": [1e8], "amount": [1],
    })
    def _ak_call_side_effect(fn_name, **kwargs):
        if fn_name == "fund_etf_hist_em":
            raise ConnectionError("blocked")
        return sina_full

    with patch("irc.data.akshare_client._ak_call", side_effect=_ak_call_side_effect) as mocked, \
         patch("irc.data.akshare_client._sleep"):
        fetch_etf_price_history_akshare("159919", start="2026-04-01", end="2026-05-07")
    sina_call = next(c for c in mocked.call_args_list if c.args[0] == "fund_etf_hist_sina")
    assert sina_call.kwargs["symbol"] == "sz159919"


def test_fetch_etf_price_history_sina_fallback_propagates_failure_when_both_fail() -> None:
    """If both EastMoney and Sina fail, raise the Sina exception so the
    per-instrument handler in ingest_cmd skips this ticker rather than crash."""
    def _both_fail(fn_name, **kwargs):
        if fn_name == "fund_etf_hist_em":
            raise ConnectionError("EM blocked")
        if fn_name == "fund_etf_hist_sina":
            raise ConnectionError("sina also down")
        raise AssertionError("unexpected")

    with patch("irc.data.akshare_client._ak_call", side_effect=_both_fail), \
         patch("irc.data.akshare_client._sleep"):
        with pytest.raises(ConnectionError, match="sina also down"):
            fetch_etf_price_history_akshare("513500", start="2026-04-01", end="2026-05-07")


def test_fetch_macro_series_akshare_dispatches_dgs10() -> None:
    fake = pd.DataFrame({
        "日期": ["2026-04-30", "2026-05-06"],
        "美国国债收益率10年": [4.25, 4.30],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_macro_series_akshare("DGS10", start="2026-01-01", end="2026-12-31")
    assert mocked.call_args.args[0] == "bond_zh_us_rate"
    assert list(out.columns) == ["date", "value"]
    assert out.iloc[-1]["value"] == 4.30


def test_fetch_macro_series_akshare_dispatches_dxy() -> None:
    """DXY is the akshare-only US Dollar Index slot used by gold scoring;
    thresholds in gold_score/_dxy_score (95/105/115) and gold_scenarios
    (dxy<100, dxy>110) are calibrated for this ~95–115 range."""
    fake = pd.DataFrame({
        "日期": ["2026-04-30", "2026-05-06"],
        "最新价": [98.42, 99.10],
    })
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_macro_series_akshare("DXY", start="2026-01-01", end="2026-12-31")
    assert mocked.call_args.args[0] == "index_global_hist_em"
    assert mocked.call_args.kwargs == {"symbol": "美元指数"}
    assert list(out.columns) == ["date", "value"]
    assert out.iloc[-1]["value"] == 99.10


def test_fetch_macro_series_akshare_raises_for_unsupported_series() -> None:
    with pytest.raises(ValueError, match="no akshare fallback"):
        fetch_macro_series_akshare("UNKNOWN_SERIES", start="2026-01-01", end="2026-05-01")


def test_fetch_macro_series_akshare_no_longer_recognizes_old_dtwexbgs_id() -> None:
    """Guards against accidental revert: DTWEXBGS used to be the placeholder
    for the DXY slot but was confusingly named (FRED's DTWEXBGS sits ~120 vs
    DXY ~98). The slot is now keyed as 'DXY' end-to-end."""
    with pytest.raises(ValueError, match="no akshare fallback"):
        fetch_macro_series_akshare("DTWEXBGS", start="2026-01-01", end="2026-05-01")


def test_fetch_etf_metadata() -> None:
    fake = pd.DataFrame([{"代码": "sh510300", "名称": "沪深300ETF"}])
    with patch("irc.data.akshare_client._ak_call") as mocked:
        mocked.return_value = fake
        out = fetch_etf_metadata("510300")

    assert out == {"ticker": "510300", "name_cn": "沪深300ETF"}


def test_item_value_dict_empty_df_returns_empty_dict() -> None:
    result = _item_value_dict(pd.DataFrame())
    assert result == {}


def test_item_value_dict_single_row_uses_column_keys() -> None:
    df = pd.DataFrame([{"fund_code": "006075", "name": "易方达"}])
    result = _item_value_dict(df)
    assert result["fund_code"] == "006075"
    assert result["name"] == "易方达"


def test_ratios_from_text_none_returns_empty_tuple() -> None:
    assert _ratios_from_text(None) == ()


def test_ratios_from_text_plain_float_returns_tuple() -> None:
    result = _ratios_from_text("0.005")
    assert result == (0.005,)


def test_expense_ratio_from_fee_table_empty_df_returns_none() -> None:
    assert _expense_ratio_from_fee_table(pd.DataFrame()) is None
