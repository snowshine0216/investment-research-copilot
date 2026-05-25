"""TDD tests for hkex_client. Mocks the akshare endpoint via the _ak_call indirection."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.hkex_client import fetch_hk_filing_digest
from irc.fundamentals.types import FilingDigest


def _row(date: str, start: str, item: str, amount: float) -> dict:
    return {
        "SECURITY_CODE": "00700",
        "SECURITY_NAME_ABBR": "腾讯控股",
        "REPORT_DATE": f"{date} 00:00:00",
        "START_DATE": f"{start} 00:00:00",
        "STD_ITEM_NAME": item,
        "AMOUNT": amount,
    }


_HK_FRAME = pd.DataFrame([
    # 2026 Q1 (latest)
    _row("2026-03-31", "2026-01-01", "营业额", 194_166_000_000),
    _row("2026-03-31", "2026-01-01", "股东应占溢利", 47_800_000_000),
    _row("2026-03-31", "2026-01-01", "毛利", 111_265_000_000),
    # 2025 Q1 (prior year same period)
    _row("2025-03-31", "2025-01-01", "营业额", 159_500_000_000),
    _row("2025-03-31", "2025-01-01", "股东应占溢利", 41_900_000_000),
    _row("2025-03-31", "2025-01-01", "毛利", 88_900_000_000),
    # 2025 FY data — older filed, should NOT win
    _row("2025-12-31", "2025-01-01", "营业额", 700_000_000_000),
    _row("2025-12-31", "2025-01-01", "股东应占溢利", 200_000_000_000),
    _row("2025-12-31", "2025-01-01", "毛利", 380_000_000_000),
])


def test_fetch_hk_filing_digest_happy_path_computes_yoy_and_margin() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = _HK_FRAME
        digest = fetch_hk_filing_digest("0700.HK")
    assert mocked.call_args[0][0] == "stock_financial_hk_report_em"
    # Symbol gets normalized to 5-digit string for EastMoney HK endpoint
    assert mocked.call_args[1]["stock"] == "00700"
    assert isinstance(digest, FilingDigest)
    assert digest.symbol == "0700.HK"
    assert digest.filed_at_iso == "2026-03-31"
    assert digest.fiscal_period == "2026Q1"
    assert digest.revenue_yoy == pytest.approx(
        (194_166 - 159_500) / 159_500, rel=1e-3
    )
    assert digest.net_income_yoy == pytest.approx(
        (47_800 - 41_900) / 41_900, rel=1e-3
    )
    assert digest.gross_margin == pytest.approx(111_265 / 194_166, rel=1e-3)
    assert "00700" in digest.source_url
    assert "hkex" in digest.source_url.lower() or "eastmoney" in digest.source_url.lower()


def test_fetch_hk_filing_digest_detects_fy_period() -> None:
    fy_frame = pd.DataFrame([
        _row("2025-12-31", "2025-01-01", "营业额", 700e9),
        _row("2025-12-31", "2025-01-01", "股东应占溢利", 200e9),
        _row("2025-12-31", "2025-01-01", "毛利", 380e9),
        _row("2024-12-31", "2024-01-01", "营业额", 620e9),
        _row("2024-12-31", "2024-01-01", "股东应占溢利", 180e9),
        _row("2024-12-31", "2024-01-01", "毛利", 340e9),
    ])
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = fy_frame
        digest = fetch_hk_filing_digest("0700.HK")
    assert digest is not None
    assert digest.fiscal_period == "2025FY"
    assert digest.revenue_yoy == pytest.approx((700 - 620) / 620, rel=1e-3)


def test_fetch_hk_filing_digest_accepts_numeric_symbol() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = _HK_FRAME
        digest = fetch_hk_filing_digest("700")
    assert mocked.call_args[1]["stock"] == "00700"
    assert digest is not None
    assert digest.symbol == "0700.HK"


def test_fetch_hk_filing_digest_returns_none_on_failure() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.side_effect = RuntimeError("eastmoney 502")
        assert fetch_hk_filing_digest("00700") is None


def test_fetch_hk_filing_digest_returns_none_when_revenue_missing() -> None:
    bad_frame = pd.DataFrame([
        _row("2026-03-31", "2026-01-01", "毛利", 1.0),
    ])
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = bad_frame
        assert fetch_hk_filing_digest("0700.HK") is None


def test_fetch_hk_filing_digest_returns_none_when_empty() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = pd.DataFrame()
        assert fetch_hk_filing_digest("0700.HK") is None


# ── Item 003: fetch_hk_stock_news ─────────────────────────────────────────────

from irc.fundamentals.hkex_client import fetch_hk_stock_news  # noqa: E402


_HK_NEWS_FRAME = pd.DataFrame({
    "发布时间": [
        "2024-04-15 09:00:00",
        "2024-04-14 09:00:00",
        "2024-04-13 09:00:00",
        "2024-04-12 09:00:00",
        "2024-04-11 09:00:00",
    ],
    "标题": ["t1", "t2", "t3", "t4", "t5"],
    "内容摘要": ["a", "b", "c", "d", "e"],
    "新闻链接": [f"https://hk-news.example/{i}" for i in range(5)],
})


def test_fetch_hk_stock_news_top_3_by_date_desc() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = _HK_NEWS_FRAME
        out = fetch_hk_stock_news("00700", top_k=3)
    assert mocked.call_args[0][0] == "stock_hk_news_em"
    assert mocked.call_args[1] == {"symbol": "00700"}
    assert len(out) == 3
    assert out[0].published_iso == "2024-04-15"
    assert out[0].source == "stock_hk_news_em"
    assert out[0].symbol == "00700"


def test_fetch_hk_stock_news_unsupported_adapter_falls_back_to_direct() -> None:
    """AkShare lacks `stock_hk_news_em`; fall back to EastMoney-direct so the
    holding still gets an info-leg evidence row (regression for the 11 funds
    rejected with `insufficient_info_coverage_top_half` on 2026-05-24)."""
    fallback = (
        {"date": "2026-04-15 09:00:00", "title": "T1",
         "content": "c1", "url": "https://example.com/1", "mediaName": "EM"},
    )
    with patch(
        "irc.fundamentals.hkex_client._ak_call",
        side_effect=AttributeError("module 'akshare' has no attribute 'stock_hk_news_em'"),
    ), patch(
        "irc.fundamentals.hkex_client._fetch_eastmoney_news_direct",
        return_value=fallback,
    ) as direct:
        out = fetch_hk_stock_news("00700", top_k=1)
    assert direct.called
    assert len(out) == 1
    assert out[0].source == "eastmoney_direct"
    assert out[0].published_iso == "2026-04-15"


def test_fetch_hk_stock_news_empty_frame_returns_empty() -> None:
    with patch("irc.fundamentals.hkex_client._ak_call") as mocked:
        mocked.return_value = pd.DataFrame()
        out = fetch_hk_stock_news("00700")
    assert out == ()


def test_fetch_hk_stock_news_raises_when_both_paths_fail() -> None:
    """P1-c: when both AkShare and EastMoney-direct raise, propagate so callers
    tag the holding as `hk_news_fetch_failed`."""
    import pytest
    with patch(
        "irc.fundamentals.hkex_client._ak_call",
        side_effect=ConnectionError("hk dfcfw 502"),
    ), patch(
        "irc.fundamentals.hkex_client._fetch_eastmoney_news_direct",
        side_effect=ConnectionError("hk dfcfw 502"),
    ), pytest.raises(ConnectionError):
        fetch_hk_stock_news("00700")


def test_hk_news_adapter_available_always_true() -> None:
    """Direct EastMoney-direct fallback makes the adapter always available,
    regardless of whether AkShare exposes `stock_hk_news_em`."""
    from irc.fundamentals.hkex_client import hk_news_adapter_available
    assert hk_news_adapter_available() is True
