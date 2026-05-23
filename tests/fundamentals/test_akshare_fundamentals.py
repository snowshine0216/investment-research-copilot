"""TDD tests for akshare_fundamentals.

All akshare calls are mocked via the _ak_call indirection used elsewhere in the
codebase (see irc.data.akshare_client). Failures degrade to empty tuples / None,
never raise — pipeline-friendly per the spec.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.akshare_fundamentals import (
    fetch_cn_etf_holdings,
    fetch_cn_index_constituents,
)
from irc.fundamentals.akshare_filing import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
)
from irc.fundamentals.types import Constituent


# ---------- fetch_cn_index_constituents ----------

_CSINDEX_FRAME = pd.DataFrame({
    "日期": ["2026-04-30"] * 4,
    "指数代码": ["000300"] * 4,
    "指数名称": ["沪深300"] * 4,
    "成分券代码": ["600519", "000858", "300750", "601318"],
    "成分券名称": ["贵州茅台", "五粮液", "宁德时代", "中国平安"],
    "交易所": ["上海证券交易所", "深圳证券交易所", "深圳证券交易所", "上海证券交易所"],
    "权重": [5.12, 2.84, 2.10, 1.95],  # percent values from CSI feed
})


def test_fetch_cn_index_constituents_happy_path() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _CSINDEX_FRAME
        out = fetch_cn_index_constituents("000300", top_n=10)
    assert mocked.call_args[0][0] == "index_stock_cons_weight_csindex"
    assert mocked.call_args[1] == {"symbol": "000300"}
    assert len(out) == 4
    assert all(isinstance(c, Constituent) for c in out)


def test_fetch_cn_index_constituents_normalizes_weight_percent_to_fraction() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _CSINDEX_FRAME
        out = fetch_cn_index_constituents("000300", top_n=10)
    assert out[0].weight == 0.0512
    assert out[0].symbol == "600519.SH"
    assert out[1].symbol == "000858.SZ"
    assert out[0].market == "cn"


def test_fetch_cn_index_constituents_truncates_to_top_n_by_weight() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _CSINDEX_FRAME
        out = fetch_cn_index_constituents("000300", top_n=2)
    assert len(out) == 2
    assert out[0].name == "贵州茅台"
    assert out[1].name == "五粮液"


def test_fetch_cn_index_constituents_returns_empty_on_failure() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = RuntimeError("csindex 503")
        out = fetch_cn_index_constituents("000300")
    assert out == ()


# ---------- SZSE Sina fallback ----------

_SINA_SZ_FRAME = pd.DataFrame({
    "品种代码": ["300750", "300059", "300760", "300015"],
    "品种名称": ["宁德时代", "东方财富", "迈瑞医疗", "爱尔眼科"],
})

_SINA_SZ_FRAME_ALT = pd.DataFrame({
    "symbol": ["300750", "300059", "300760", "300015"],
    "name": ["宁德时代", "东方财富", "迈瑞医疗", "爱尔眼科"],
    "trade": [0.0, 0.0, 0.0, 0.0],
})


def test_fetch_cn_index_constituents_falls_back_to_sina_for_szse_code() -> None:
    """399006 (创业板指) is not published by CSI; Sina returns the constituent list
    without weights — we still return Constituent rows with weight=0.0 so the
    downstream thesis classifier (sign-counting) keeps working."""
    csi_empty = pd.DataFrame()
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [csi_empty, _SINA_SZ_FRAME]
        out = fetch_cn_index_constituents("399006", top_n=3)
    assert mocked.call_args_list[0].kwargs == {"symbol": "399006"}
    assert mocked.call_args_list[1].kwargs == {"symbol": "399006"}
    assert len(out) == 3
    assert out[0] == Constituent(symbol="300750.SZ", name="宁德时代", weight=0.0, market="cn")
    assert out[2].name == "迈瑞医疗"


def test_fetch_cn_index_constituents_falls_back_to_sina_for_sh_code_when_csi_empty() -> None:
    """If CSI returns empty for a 6xxxxx code, try Sina with plain index code."""
    sh_frame = pd.DataFrame({
        "品种代码": ["600519"],
        "品种名称": ["贵州茅台"],
    })
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), sh_frame]
        out = fetch_cn_index_constituents("600000", top_n=1)
    assert mocked.call_args_list[1].kwargs == {"symbol": "600000"}
    assert out == (Constituent(symbol="600519.SH", name="贵州茅台", weight=0.0, market="cn"),)


def test_fetch_cn_index_constituents_returns_empty_when_both_paths_fail() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), pd.DataFrame()]
        out = fetch_cn_index_constituents("399006", top_n=5)
    assert out == ()


def test_fetch_cn_index_constituents_sina_exception_is_swallowed() -> None:
    """Sina endpoint failure must degrade to empty, never raise."""
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), RuntimeError("akshare down")]
        out = fetch_cn_index_constituents("399006", top_n=5)
    assert out == ()


def test_fetch_cn_index_constituents_sina_alt_columns_symbol_name() -> None:
    """Current AkShare returns Sina columns as symbol/name/trade."""
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), _SINA_SZ_FRAME_ALT]
        out = fetch_cn_index_constituents("399006", top_n=2)
    assert len(out) == 2
    assert out[0] == Constituent(symbol="300750.SZ", name="宁德时代", weight=0.0, market="cn")


def test_fetch_cn_index_constituents_sina_alt_columns_strip_exchange_prefix() -> None:
    prefixed = pd.DataFrame({
        "symbol": ["sz300001", "sz300002"],
        "name": ["特锐德", "神州泰岳"],
    })
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), prefixed]
        out = fetch_cn_index_constituents("399006", top_n=2)
    assert out[0].symbol == "300001.SZ"
    assert out[1].symbol == "300002.SZ"


# ---------- fetch_cn_etf_holdings ----------

_HOLDINGS_FRAME = pd.DataFrame({
    "序号": [1, 2, 3, 1, 2],
    "股票代码": ["002025", "600862", "600519", "000333", "002415"],
    "股票名称": ["航天电器", "中航高科", "贵州茅台", "美的集团", "海康威视"],
    "占净值比例": [3.46, 3.24, 2.91, 9.10, 6.50],
    "持股数": [209.92, 380.43, 0.50, 1000.0, 500.0],
    "持仓市值": [7947.67, 7441.16, 873.6, 28000.0, 19500.0],
    "季度": [
        "2024年1季度股票投资明细",
        "2024年1季度股票投资明细",
        "2024年1季度股票投资明细",
        "2024年2季度股票投资明细",
        "2024年2季度股票投资明细",
    ],
})


def test_fetch_cn_etf_holdings_happy_path_filters_latest_quarter() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HOLDINGS_FRAME
        out = fetch_cn_etf_holdings("000001", as_of="2024", top_n=10)
    assert mocked.call_args[0][0] == "fund_portfolio_hold_em"
    assert mocked.call_args[1] == {"symbol": "000001", "date": "2024"}
    # Latest quarter is 2季度 — two rows.
    assert out.source_report_quarter == "2024Q2"
    assert out.source_report_date == "2024-06-30"
    assert len(out.constituents) == 2
    assert out.constituents[0].name_cn == "美的集团"
    assert out.constituents[0].weight_pct == 9.10
    assert out.constituents[0].symbol == "000333"
    assert out.constituents[0].exchange == "SZ"
    assert out.constituents[0].provider_symbol == "000333"


def test_fetch_cn_etf_holdings_default_as_of_uses_current_year() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HOLDINGS_FRAME
        fetch_cn_etf_holdings("000001")
    kwargs = mocked.call_args[1]
    assert kwargs["symbol"] == "000001"
    assert kwargs["date"].isdigit() and len(kwargs["date"]) == 4


def test_fetch_cn_etf_holdings_truncates_to_top_n() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HOLDINGS_FRAME
        out = fetch_cn_etf_holdings("000001", as_of="2024", top_n=1)
    assert len(out.constituents) == 1
    assert out.constituents[0].name_cn == "美的集团"


def test_fetch_cn_etf_holdings_returns_empty_on_failure() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = ValueError("eastmoney 502")
        out = fetch_cn_etf_holdings("000001", as_of="2024")
    assert out.constituents == ()
    assert out.source_report_quarter == ""
    assert out.source_report_date == ""


_HK_HOLDINGS_FRAME = pd.DataFrame({
    "股票代码": ["00700", "0700", "09988", "600519", "AAPL", "830839"],
    "股票名称": ["腾讯控股", "腾讯控股", "阿里巴巴", "贵州茅台", "苹果", "晶赛科技"],
    "占净值比例": [9.0, 8.0, 7.0, 6.0, 5.0, 4.0],
    "季度": ["2024年1季度股票投资明细"] * 6,
})


# ── Item 003: fetch_cn_stock_news ─────────────────────────────────────────────

from irc.fundamentals.akshare_fundamentals import fetch_cn_stock_news  # noqa: E402


_CN_NEWS_FRAME = pd.DataFrame({
    "关键词": ["茅台"] * 5,
    "新闻标题": ["新品发布", "增持公告", "Q1业绩", "调研纪要", "回购"],
    "新闻内容": ["a", "b", "c", "d", "e"],
    "发布时间": [
        "2024-04-15 09:00:00",
        "2024-04-14 09:00:00",
        "2024-04-13 09:00:00",
        "2024-04-12 09:00:00",
        "2024-04-11 09:00:00",
    ],
    "新闻链接": [f"https://example.com/{i}" for i in range(5)],
    "文章来源": ["东财"] * 5,
})


def test_fetch_cn_stock_news_top_3_by_date_desc() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _CN_NEWS_FRAME
        out = fetch_cn_stock_news("600519", top_k=3)
    assert mocked.call_args[0][0] == "stock_news_em"
    assert mocked.call_args[1] == {"symbol": "600519"}
    assert len(out) == 3
    assert out[0].published_iso == "2024-04-15"
    assert out[0].title == "新品发布"
    assert out[0].symbol == "600519"
    assert out[0].source == "stock_news_em"
    assert out[1].published_iso == "2024-04-14"
    assert out[2].published_iso == "2024-04-13"


def test_fetch_cn_stock_news_empty_on_failure() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = ConnectionError("dfcfw 502")
        out = fetch_cn_stock_news("600519")
    assert out == ()


def test_fetch_cn_stock_news_empty_on_empty_frame() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = pd.DataFrame()
        out = fetch_cn_stock_news("600519")
    assert out == ()


def test_fetch_cn_etf_holdings_hk_and_bj_routing_without_market_column() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = _HK_HOLDINGS_FRAME
        out = fetch_cn_etf_holdings("501025", as_of="2024", top_n=6)
    assert out.source_report_quarter == "2024Q1"
    exchanges = [c.exchange for c in out.constituents]
    assert exchanges == ["HK", "HK", "HK", "SH", "US", "BJ"]


# ---------- fetch_cn_broker_reports ----------

_REPORT_FRAME = pd.DataFrame({
    "序号": [1, 2, 3, 4],
    "股票代码": ["600519"] * 4,
    "股票简称": ["贵州茅台"] * 4,
    "报告名称": [
        "维持买入评级，节奏向好",
        "经营韧性强，长期价值凸显",
        "白酒龙头估值修复",
        "2024年报点评",  # well outside window — should be filtered out
    ],
    "东财评级": ["买入", "增持", "买入", "增持"],
    "机构": ["中信证券", "中金公司", "国信证券", "兴业证券"],
    "日期": ["2026-05-08", "2026-04-20", "2026-04-15", "2024-04-10"],
    "报告PDF链接": [
        "https://pdf.dfcfw.com/pdf/H3_a.pdf",
        "https://pdf.dfcfw.com/pdf/H3_b.pdf",
        "https://pdf.dfcfw.com/pdf/H3_c.pdf",
        "https://pdf.dfcfw.com/pdf/H3_d.pdf",
    ],
})


def test_fetch_cn_broker_reports_happy_path_returns_recent_first() -> None:
    with patch(
        "irc.fundamentals.akshare_filing._ak_call"
    ) as mocked, patch(
        "irc.fundamentals.akshare_filing._today_iso",
        return_value="2026-05-15",
    ):
        mocked.return_value = _REPORT_FRAME
        out = fetch_cn_broker_reports("600519", days=90, max_reports=20)
    assert mocked.call_args[0][0] == "stock_research_report_em"
    assert mocked.call_args[1] == {"symbol": "600519"}
    assert len(out) == 3  # 2024-04-10 dropped
    assert out[0].published_iso == "2026-05-08"  # newest first
    assert out[0].broker == "中信证券"
    assert out[0].title == "维持买入评级，节奏向好"
    assert out[0].source_url == "https://pdf.dfcfw.com/pdf/H3_a.pdf"
    assert out[0].symbol == "600519.SH"
    assert out[0].target_price is None  # no target_price column in EastMoney feed


def test_fetch_cn_broker_reports_strips_exchange_suffix_for_akshare() -> None:
    with patch(
        "irc.fundamentals.akshare_filing._ak_call"
    ) as mocked, patch(
        "irc.fundamentals.akshare_filing._today_iso",
        return_value="2026-05-15",
    ):
        mocked.return_value = _REPORT_FRAME
        out = fetch_cn_broker_reports("600519.SH", days=90, max_reports=1)

    assert mocked.call_args[1] == {"symbol": "600519"}
    assert out[0].symbol == "600519.SH"


def test_fetch_cn_broker_reports_respects_max_reports() -> None:
    with patch(
        "irc.fundamentals.akshare_filing._ak_call"
    ) as mocked, patch(
        "irc.fundamentals.akshare_filing._today_iso",
        return_value="2026-05-15",
    ):
        mocked.return_value = _REPORT_FRAME
        out = fetch_cn_broker_reports("600519", days=90, max_reports=2)
    assert len(out) == 2


def test_fetch_cn_broker_reports_returns_empty_on_failure() -> None:
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.side_effect = RuntimeError("eastmoney 5xx")
        out = fetch_cn_broker_reports("600519")
    assert out == ()


# ---------- fetch_cn_filing_digest ----------

_ABSTRACT_FRAME = pd.DataFrame({
    "选项": ["常用指标", "常用指标", "常用指标", "盈利能力"],
    "指标": ["归母净利润", "营业总收入", "营业成本", "净资产收益率"],
    # latest col → 2026Q1; same period prior year → 20250331
    "20260331": [27.24e9, 54.70e9, 17.19e9, 0.18],
    "20251231": [82.32e9, 172.05e9, 57.37e9, 0.30],
    "20250930": [64.62e9, 130.90e9, 41.42e9, 0.20],
    "20250630": [45.40e9, 91.09e9, 28.35e9, 0.19],
    "20250331": [26.84e9, 51.44e9, 14.43e9, 0.17],
    "20241231": [86.22e9, 174.14e9, 54.52e9, 0.31],
})


def test_fetch_cn_filing_digest_computes_yoy_and_margin_for_latest_quarter() -> None:
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = _ABSTRACT_FRAME
        digest = fetch_cn_filing_digest("600519")
    assert mocked.call_args[0][0] == "stock_financial_abstract"
    assert digest is not None
    assert digest.symbol == "600519.SH"
    assert digest.fiscal_period == "2026Q1"
    assert digest.filed_at_iso == "2026-03-31"
    # revenue YoY: (54.70 - 51.44) / 51.44 ≈ 0.0634
    assert digest.revenue_yoy == pytest.approx((54.70 - 51.44) / 51.44, rel=1e-3)
    assert digest.net_income_yoy == pytest.approx((27.24 - 26.84) / 26.84, rel=1e-3)
    # gross_margin: 1 - 17.19/54.70 ≈ 0.686
    assert digest.gross_margin == pytest.approx(1 - 17.19 / 54.70, rel=1e-3)
    assert "vFD_FinanceSummary" in digest.source_url
    assert "600519" in digest.source_url


def test_fetch_cn_filing_digest_strips_exchange_suffix_for_akshare() -> None:
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = _ABSTRACT_FRAME
        digest = fetch_cn_filing_digest("600519.SH")

    assert mocked.call_args[1] == {"symbol": "600519"}
    assert digest is not None
    assert digest.symbol == "600519.SH"
    assert "600519.SH" not in digest.source_url


def test_fetch_cn_filing_digest_maps_fy_period_for_year_end_column() -> None:
    fy_frame = pd.DataFrame({
        "选项": ["常用指标", "常用指标", "常用指标"],
        "指标": ["归母净利润", "营业总收入", "营业成本"],
        "20251231": [82.32e9, 172.05e9, 57.37e9],
        "20241231": [86.22e9, 174.14e9, 54.52e9],
    })
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = fy_frame
        digest = fetch_cn_filing_digest("600519")
    assert digest is not None
    assert digest.fiscal_period == "2025FY"
    assert digest.filed_at_iso == "2025-12-31"
    # negative YoY allowed
    assert digest.revenue_yoy == pytest.approx((172.05 - 174.14) / 174.14, rel=1e-3)


def test_fetch_cn_filing_digest_returns_none_on_failure() -> None:
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.side_effect = RuntimeError("sina 502")
        digest = fetch_cn_filing_digest("600519")
    assert digest is None


def test_fetch_cn_filing_digest_returns_none_when_metrics_missing() -> None:
    bad_frame = pd.DataFrame({
        "选项": ["盈利能力"], "指标": ["净资产收益率"], "20260331": [0.18],
    })
    with patch("irc.fundamentals.akshare_filing._ak_call") as mocked:
        mocked.return_value = bad_frame
        digest = fetch_cn_filing_digest("600519")
    assert digest is None


# ---------- fetch_hk_index_constituents ----------


def test_parse_hk_index_frame_sorts_by_weight_and_truncates() -> None:
    """Direct test of parsing logic — independent of the stub network call."""
    from irc.fundamentals.akshare_fundamentals import _parse_hk_index_frame

    df = pd.DataFrame([
        {"代码": "01299", "名称": "友邦保险", "权重": 6.0},
        {"代码": "00700", "名称": "腾讯控股", "权重": 10.0},
        {"代码": "09988", "名称": "阿里巴巴-W", "权重": 8.0},
    ])
    out = _parse_hk_index_frame(df, top_n=2)

    assert len(out) == 2
    assert out[0].symbol == "00700.HK"  # highest weight first
    assert out[1].symbol == "09988.HK"
    assert abs(out[0].weight - 0.10) < 1e-9


def test_parse_hk_index_frame_returns_empty_for_missing_columns() -> None:
    from irc.fundamentals.akshare_fundamentals import _parse_hk_index_frame

    df = pd.DataFrame([{"col_a": "foo"}])
    out = _parse_hk_index_frame(df, top_n=10)
    assert out == ()


def test_fetch_hk_index_constituents_happy_path() -> None:
    from irc.fundamentals.akshare_fundamentals import fetch_hk_index_constituents
    
    # Use placeholder column names - adjust when actual AkShare function is discovered
    fake_df = pd.DataFrame([
        {"代码": "00700", "名称": "腾讯控股", "权重": 10.0},
        {"代码": "09988", "名称": "阿里巴巴-W", "权重": 8.0},
        {"代码": "01299", "名称": "友邦保险", "权重": 6.0},
    ])
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.return_value = fake_df
        out = fetch_hk_index_constituents("HSI", top_n=2)

    assert len(out) == 2
    assert out[0] == Constituent(
        symbol="00700.HK", name="腾讯控股", weight=0.10, market="hk"
    )
    assert out[1] == Constituent(
        symbol="09988.HK", name="阿里巴巴-W", weight=0.08, market="hk"
    )


def test_fetch_hk_index_constituents_returns_empty_on_failure() -> None:
    from irc.fundamentals.akshare_fundamentals import fetch_hk_index_constituents

    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = RuntimeError("akshare network error")
        out = fetch_hk_index_constituents("HSI", top_n=10)

    assert out == ()


# ── Item 003: _parse_exchange + _parse_quarter_column ─────────────────────────

from irc.fundamentals.akshare_fundamentals import (  # noqa: E402
    _parse_exchange,
    _parse_quarter_column,
)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("600519", "SH"),
        ("000333", "SZ"),
        ("300750", "SZ"),
        ("00700", "HK"),
        ("0700", "HK"),
        ("09988", "HK"),
        ("AAPL", "US"),
        ("830839", "BJ"),
        ("430139", "BJ"),
    ],
)
def test_parse_exchange_ticker_prefix_fallback(code, expected) -> None:
    row = pd.Series({"股票代码": code})
    assert _parse_exchange(row) == expected


def test_parse_exchange_market_column_priority_hk() -> None:
    row = pd.Series({"股票代码": "600519", "股票市场": "港交所"})
    assert _parse_exchange(row) == "HK"


def test_parse_exchange_market_column_priority_sz() -> None:
    row = pd.Series({"股票代码": "00700", "股票市场": "深交所"})
    assert _parse_exchange(row) == "SZ"


def test_parse_exchange_market_column_star_board_sh() -> None:
    row = pd.Series({"股票代码": "688981", "股票市场": "科创板"})
    assert _parse_exchange(row) == "SH"


def test_parse_exchange_market_column_unknown_falls_through() -> None:
    # Unknown 股票市场 value falls through to ticker-prefix.
    row = pd.Series({"股票代码": "600519", "股票市场": "新疆板块"})
    assert _parse_exchange(row) == "SH"


def test_parse_exchange_unknown() -> None:
    row = pd.Series({"股票代码": "X1!"})
    assert _parse_exchange(row) == "UNKNOWN"


def test_parse_exchange_strips_sz_sh_prefix() -> None:
    row = pd.Series({"股票代码": "sz000333"})
    assert _parse_exchange(row) == "SZ"


def test_parse_quarter_column_happy() -> None:
    row = pd.Series({"季度": "2024年1季度股票投资明细"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == "2024Q1"
    assert iso == "2024-03-31"


def test_parse_quarter_column_q4() -> None:
    row = pd.Series({"季度": "2023年4季度股票投资明细"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == "2023Q4"
    assert iso == "2023-12-31"


def test_parse_quarter_column_baogao_qi_fallback() -> None:
    row = pd.Series({"报告期": "2024年2季度"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == "2024Q2"
    assert iso == "2024-06-30"


def test_parse_quarter_column_unparseable() -> None:
    row = pd.Series({"季度": "2024年半年度"})
    quarter, iso = _parse_quarter_column(row)
    assert quarter == ""
    assert iso == ""
