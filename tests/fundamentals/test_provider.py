from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals import akshare_filing, akshare_index_valuation
from irc.fundamentals.akshare_filing import fetch_cn_broker_reports, fetch_cn_filing_digest
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.provider import (
    AkShareProvider,
    CnFundamentalsProvider,
)


# ── Fixture frames (mirror the live AkShare column labels) ────────────────────
_FIN_FRAME = pd.DataFrame({
    "选项": ["常用指标", "常用指标", "常用指标", "盈利能力"],
    "指标": ["营业总收入", "归母净利润", "营业成本", "净资产收益率"],
    "20241231": [1000.0, 200.0, 600.0, 0.18],
    "20231231": [800.0, 150.0, 500.0, 0.15],
})
_PE_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": [12.1]})
_PB_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "市净率": [1.31]})
_BROKER_FRAME = pd.DataFrame({
    "机构": ["中信"],
    "东财评级": ["买入"],
    "报告名称": ["深度报告"],
    "日期": [pd.Timestamp.today().strftime("%Y-%m-%d")],
    "报告PDF链接": ["http://x/y.pdf"],
})


def test_akshare_provider_satisfies_protocol() -> None:
    assert isinstance(AkShareProvider(), CnFundamentalsProvider)


def test_akshare_provider_filing_equals_direct_call() -> None:
    with patch.object(akshare_filing, "_ak_call", return_value=_FIN_FRAME):
        direct = fetch_cn_filing_digest("600519")
    with patch.object(akshare_filing, "_ak_call", return_value=_FIN_FRAME):
        via = AkShareProvider().fetch_filing_digest("600519")
    assert via == direct


def test_akshare_provider_brokers_equals_direct_call() -> None:
    with patch.object(akshare_filing, "_ak_call", return_value=_BROKER_FRAME):
        direct = fetch_cn_broker_reports("600519")
    with patch.object(akshare_filing, "_ak_call", return_value=_BROKER_FRAME):
        via = AkShareProvider().fetch_broker_reports("600519")
    assert via == direct


def test_akshare_provider_index_equals_direct_call() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake), patch.object(
        akshare_index_valuation, "_today_iso", return_value="2026-05-31"
    ):
        direct = fetch_cn_index_valuation("csi300")
    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake), patch.object(
        akshare_index_valuation, "_today_iso", return_value="2026-05-31"
    ):
        via = AkShareProvider().fetch_index_valuation("csi300")
    assert via == direct


def test_akshare_provider_passes_kwargs_to_broker_fetch() -> None:
    # Provider must forward the days/max_reports keyword args verbatim.
    captured: list[dict] = []

    def _fake(fn_name, **kwargs):
        captured.append({"fn": fn_name, **kwargs})
        return _BROKER_FRAME

    with patch.object(akshare_filing, "_ak_call", side_effect=_fake):
        AkShareProvider().fetch_broker_reports("600519", days=30, max_reports=5)
    assert captured and captured[0]["fn"] == "stock_research_report_em"
