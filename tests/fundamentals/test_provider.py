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


from irc.fundamentals.provider import FallbackProvider  # noqa: E402
from irc.fundamentals.types import BrokerReport as _BR  # noqa: E402
from irc.fundamentals.index_valuation_types import IndexValuation  # noqa: E402


class _Fake:
    """In-memory provider for routing tests (no network)."""

    def __init__(self, *, digest=None, brokers=(), index=None, raises=False):
        self._digest = digest
        self._brokers = brokers
        self._index = index
        self._raises = raises

    def fetch_filing_digest(self, symbol):
        if self._raises:
            raise RuntimeError("boom")
        return self._digest

    def fetch_broker_reports(self, symbol, *, days=90, max_reports=20):
        if self._raises:
            raise RuntimeError("boom")
        return self._brokers

    def fetch_index_valuation(self, index_key):
        if self._raises:
            raise RuntimeError("boom")
        return self._index


def _digest(symbol="600519.SH"):
    from irc.fundamentals.types import FilingDigest
    return FilingDigest(
        symbol=symbol, fiscal_period="2024FY", filed_at_iso="2024-12-31",
        revenue_yoy=0.25, net_income_yoy=0.33, gross_margin=0.4,
    )


def test_fallback_satisfies_protocol() -> None:
    fp = FallbackProvider(AkShareProvider(), AkShareProvider())
    assert isinstance(fp, CnFundamentalsProvider)


def test_fallback_primary_hit_skips_secondary() -> None:
    primary = _Fake(digest=_digest("P"))
    secondary = _Fake(digest=_digest("S"))
    out = FallbackProvider(primary, secondary).fetch_filing_digest("x")
    assert out is not None and out.symbol == "P"


def test_fallback_primary_miss_uses_secondary() -> None:
    primary = _Fake(digest=None)
    secondary = _Fake(digest=_digest("S"))
    out = FallbackProvider(primary, secondary).fetch_filing_digest("x")
    assert out is not None and out.symbol == "S"


def test_fallback_primary_raises_uses_secondary() -> None:
    primary = _Fake(raises=True)
    secondary = _Fake(digest=_digest("S"))
    out = FallbackProvider(primary, secondary).fetch_filing_digest("x")
    assert out is not None and out.symbol == "S"


def test_fallback_both_miss_returns_none_no_raise() -> None:
    out = FallbackProvider(_Fake(digest=None), _Fake(digest=None)).fetch_filing_digest("x")
    assert out is None


def test_fallback_brokers_empty_primary_uses_secondary() -> None:
    sec = (_BR(symbol="600519.SH", broker="中信", rating="买入",
              target_price=2000.0, published_iso="2026-05-30", title="t"),)
    out = FallbackProvider(_Fake(brokers=()), _Fake(brokers=sec)).fetch_broker_reports("x")
    assert len(out) == 1 and out[0].target_price == 2000.0


def test_fallback_brokers_both_empty_returns_empty_tuple() -> None:
    out = FallbackProvider(_Fake(brokers=()), _Fake(brokers=())).fetch_broker_reports("x")
    assert out == ()


def test_fallback_primary_raises_secondary_raises_returns_miss() -> None:
    out = FallbackProvider(_Fake(raises=True), _Fake(raises=True)).fetch_broker_reports("x")
    assert out == ()


def test_fallback_index_primary_miss_uses_secondary() -> None:
    iv = IndexValuation(index_key="csi300", pe_ttm=10.0, pb=1.0,
                        dividend_yield=None, as_of_iso="2026-05-31")
    out = FallbackProvider(_Fake(index=None), _Fake(index=iv)).fetch_index_valuation("csi300")
    assert out is not None and out.pe_ttm == 10.0


def test_fallback_target_price_flows_when_primary_brokers_empty() -> None:
    # The headline gap: AkShare drops target_price; Tushare-shaped secondary fills it.
    sec = (_BR(symbol="600519.SH", broker="中信", rating="买入",
              target_price=2100.0, published_iso="2026-05-30", title="t"),)
    out = FallbackProvider(_Fake(brokers=()), _Fake(brokers=sec)).fetch_broker_reports("600519")
    assert out[0].target_price == 2100.0


from unittest.mock import MagicMock  # noqa: E402

from irc.fundamentals.provider import default_cn_provider  # noqa: E402


def test_default_provider_is_akshare_only_without_token() -> None:
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = ""
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings):
        provider = default_cn_provider()
    assert isinstance(provider, AkShareProvider)


def test_default_provider_is_fallback_with_token() -> None:
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = "tok-123"
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings):
        provider = default_cn_provider()
    assert isinstance(provider, FallbackProvider)


from irc.fundamentals.tushare_provider import TushareProvider  # noqa: E402
from irc.fundamentals import tushare_provider as _tp_mod  # noqa: E402


def test_default_provider_secondary_is_tushare() -> None:
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = "tok-123"
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings):
        provider = default_cn_provider()
    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider._secondary, TushareProvider)
    assert isinstance(provider._primary, AkShareProvider)


def test_target_price_flows_through_default_provider_when_akshare_empty() -> None:
    # AkShare broker fetch returns () (today's reality); Tushare report_rc fills it.
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"], "org_name": ["中信"], "rating": ["买入"],
        "target_price": [2100.0], "report_date": [pd.Timestamp.today().strftime("%Y%m%d")],
        "report_title": ["t"],
    })
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = "tok-123"
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings), patch.object(
        akshare_filing, "_ak_call", return_value=pd.DataFrame()  # AkShare → ()
    ), patch.object(_tp_mod, "_tushare_call", return_value=rc):
        provider = default_cn_provider()
        out = provider.fetch_broker_reports("600519")
    assert len(out) == 1 and out[0].target_price == 2100.0


# ── FIX 1: swallowed primary exception emits a WARNING and still returns sentinel ─

def test_fallback_primary_swallow_emits_warning_and_returns_sentinel(caplog) -> None:
    """When primary raises, FallbackProvider must log a WARNING and still return sentinel."""
    import logging
    primary = _Fake(raises=True)
    secondary = _Fake(digest=None)
    with caplog.at_level(logging.WARNING, logger="irc.fundamentals.provider"):
        out = FallbackProvider(primary, secondary).fetch_filing_digest("600519")
    assert out is None  # sentinel unchanged
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "Expected at least one WARNING log when primary swallows an exception"


# ── FIX 003: decouple default_cn_provider from the DEEPSEEK key ──────────────

from pydantic import ValidationError as _PydanticValidationError  # noqa: E402


def test_default_cn_provider_degrades_to_akshare_when_settings_validation_fails() -> None:
    """default_cn_provider() must return AkShareProvider (not raise) when Settings()
    raises ValidationError (e.g. DEEPSEEK_API_KEY absent in a fetch-only context).
    This test FAILS before the fix and PASSES after. (003 pr-review round 2)
    """
    def _raise_validation_error():
        raise _PydanticValidationError.from_exception_data(
            title="Settings",
            line_errors=[{
                "type": "missing",
                "loc": ("deepseek_api_key",),
                "msg": "Field required",
                "input": {},
                "ctx": {},
                "url": "",
            }],
        )

    with patch("irc.fundamentals.provider.Settings", side_effect=_raise_validation_error):
        provider = default_cn_provider()
    assert isinstance(provider, AkShareProvider)
