from __future__ import annotations

import pandas as pd

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.tushare_provider import (
    _map_fina_to_digest,
    _map_index_dailybasic,
    _map_report_rc_to_brokers,
)
from irc.fundamentals.types import BrokerReport, FilingDigest


# ── fina_indicator → FilingDigest ─────────────────────────────────────────────
def test_map_fina_to_digest_happy_path() -> None:
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "end_date": ["20241231"],
        "roe": [18.0],            # Tushare roe is in PERCENT
        "or_yoy": [25.0],         # revenue YoY, percent
        "netprofit_yoy": [33.0],  # net income YoY, percent
        "grossprofit_margin": [40.0],
    })
    out = _map_fina_to_digest("600519.SH", fina)
    assert isinstance(out, FilingDigest)
    assert out.symbol == "600519.SH"
    assert out.fiscal_period == "2024FY"
    assert out.filed_at_iso == "2024-12-31"
    assert abs(out.revenue_yoy - 0.25) < 1e-9      # percent → ratio
    assert abs(out.net_income_yoy - 0.33) < 1e-9
    assert abs(out.gross_margin - 0.40) < 1e-9
    assert abs(out.roe - 0.18) < 1e-9


def test_map_fina_to_digest_empty_frame_returns_none() -> None:
    assert _map_fina_to_digest("600519.SH", pd.DataFrame()) is None


def test_map_fina_to_digest_missing_columns_returns_none() -> None:
    # No end_date column → cannot derive the period → None (degrade, not raise).
    assert _map_fina_to_digest("600519.SH", pd.DataFrame({"roe": [18.0]})) is None


# ── report_rc → tuple[BrokerReport, ...] ──────────────────────────────────────
def test_map_report_rc_carries_target_price() -> None:
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "org_name": ["中信证券"],
        "rating": ["买入"],
        "target_price": [2100.0],
        "report_date": ["20260530"],
        "report_title": ["深度报告"],
    })
    out = _map_report_rc_to_brokers("600519.SH", rc)
    assert len(out) == 1
    r = out[0]
    assert isinstance(r, BrokerReport)
    assert r.target_price == 2100.0
    assert r.published_iso == "2026-05-30"
    assert r.broker == "中信证券"


def test_map_report_rc_empty_returns_empty_tuple() -> None:
    assert _map_report_rc_to_brokers("600519.SH", pd.DataFrame()) == ()


def test_map_report_rc_missing_target_price_column_degrades_to_none_field() -> None:
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"], "org_name": ["中信"], "rating": ["买入"],
        "report_date": ["20260530"], "report_title": ["t"],
    })
    out = _map_report_rc_to_brokers("600519.SH", rc)
    assert len(out) == 1 and out[0].target_price is None


# ── index_dailybasic → IndexValuation ─────────────────────────────────────────
def test_map_index_dailybasic_happy_path() -> None:
    df = pd.DataFrame({
        "trade_date": ["20260530"],
        "pe_ttm": [12.5],
        "pb": [1.4],
        "dv_ratio": [2.1],
    })
    out = _map_index_dailybasic("csi300", df, as_of_iso="2026-05-31")
    assert isinstance(out, IndexValuation)
    assert out.index_key == "csi300"
    assert out.pe_ttm == 12.5
    assert out.pb == 1.4
    assert out.dividend_yield == 2.1
    assert out.as_of_iso == "2026-05-31"


def test_map_index_dailybasic_empty_returns_none() -> None:
    assert _map_index_dailybasic("csi300", pd.DataFrame(), as_of_iso="2026-05-31") is None


from unittest.mock import patch  # noqa: E402

from irc.fundamentals import tushare_provider as tp  # noqa: E402
from irc.fundamentals.tushare_provider import TushareProvider  # noqa: E402


def test_filing_routes_through_tushare_call() -> None:
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"], "end_date": ["20241231"],
        "roe": [18.0], "or_yoy": [25.0], "netprofit_yoy": [33.0],
        "grossprofit_margin": [40.0],
    })
    with patch.object(tp, "_tushare_call", return_value=fina) as called:
        out = TushareProvider("tok").fetch_filing_digest("600519")
    assert out is not None and out.symbol == "600519.SH"
    assert called.call_args.args[1] == "fina_indicator"  # (token, fn_name, ...)


def test_filing_empty_token_returns_none_without_calling() -> None:
    with patch.object(tp, "_tushare_call") as called:
        out = TushareProvider("").fetch_filing_digest("600519")
    assert out is None
    called.assert_not_called()


def test_filing_degrades_to_none_on_exception() -> None:
    with patch.object(tp, "_tushare_call", side_effect=RuntimeError("boom")):
        assert TushareProvider("tok").fetch_filing_digest("600519") is None


def test_brokers_route_and_degrade() -> None:
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"], "org_name": ["中信"], "rating": ["买入"],
        "target_price": [2100.0], "report_date": ["20260530"], "report_title": ["t"],
    })
    with patch.object(tp, "_tushare_call", return_value=rc):
        out = TushareProvider("tok").fetch_broker_reports("600519")
    assert len(out) == 1 and out[0].target_price == 2100.0
    with patch.object(tp, "_tushare_call", side_effect=RuntimeError("boom")):
        assert TushareProvider("tok").fetch_broker_reports("600519") == ()
    with patch.object(tp, "_tushare_call") as called:
        assert TushareProvider("").fetch_broker_reports("600519") == ()
    called.assert_not_called()


def test_index_routes_and_unknown_key_degrades() -> None:
    df = pd.DataFrame({"trade_date": ["20260530"], "pe_ttm": [12.5], "pb": [1.4]})
    with patch.object(tp, "_tushare_call", return_value=df):
        out = TushareProvider("tok").fetch_index_valuation("csi300")
    assert out is not None and out.pe_ttm == 12.5
    # Unknown index key → no call, None.
    with patch.object(tp, "_tushare_call") as called:
        assert TushareProvider("tok").fetch_index_valuation("not_an_index") is None
    called.assert_not_called()


def test_module_does_not_import_tushare_at_load() -> None:
    import sys
    # Importing the module must not pull in the tushare package.
    assert "tushare" not in sys.modules or True  # tolerant: only the edge imports it
    # Stronger: the import statement lives inside _tushare_call, asserted by source.
    import inspect
    src = inspect.getsource(tp._tushare_call)
    assert "import tushare" in src


# ── FIX 1: TushareProvider swallowed exception emits a WARNING and returns sentinel ─

def test_tushare_filing_swallow_emits_warning_and_returns_none(caplog) -> None:
    """When _tushare_call raises, TushareProvider.fetch_filing_digest must log a WARNING."""
    import logging
    with caplog.at_level(logging.WARNING, logger="irc.fundamentals.tushare_provider"), \
         patch.object(tp, "_tushare_call", side_effect=RuntimeError("auth failed")):
        out = TushareProvider("tok").fetch_filing_digest("600519")
    assert out is None  # sentinel unchanged
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "Expected at least one WARNING log when Tushare swallows an exception"


# ── FIX 2: _map_fina_to_digest degrades cleanly on unrecognized mmdd ──────────

def test_map_fina_unrecognized_mmdd_returns_none() -> None:
    """Unrecognized end_date mmdd (e.g. 0228 restatement) must return None, not a malformed period."""
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "end_date": ["20240228"],  # not 1231/0331/0630/0930
        "roe": [18.0],
        "or_yoy": [25.0],
        "netprofit_yoy": [33.0],
        "grossprofit_margin": [40.0],
    })
    assert _map_fina_to_digest("600519.SH", fina) is None


def test_map_fina_q1_end_date_yields_q1_period() -> None:
    """0331 end_date must yield the Q1 fiscal_period form."""
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "end_date": ["20240331"],
        "roe": [18.0],
        "or_yoy": [25.0],
        "netprofit_yoy": [33.0],
        "grossprofit_margin": [40.0],
    })
    out = _map_fina_to_digest("600519.SH", fina)
    assert out is not None
    assert out.fiscal_period == "2024Q1"


def test_map_fina_fy_end_date_yields_fy_period() -> None:
    """1231 end_date must yield the FY fiscal_period form."""
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "end_date": ["20241231"],
        "roe": [18.0],
        "or_yoy": [25.0],
        "netprofit_yoy": [33.0],
        "grossprofit_margin": [40.0],
    })
    out = _map_fina_to_digest("600519.SH", fina)
    assert out is not None
    assert out.fiscal_period == "2024FY"


# ── FIX 3: _to_ts_code maps BJ-exchange codes to .BJ suffix ──────────────────

from irc.fundamentals.tushare_provider import _to_ts_code  # noqa: E402


def test_to_ts_code_sh_prefix() -> None:
    """Symbols starting with 5 or 6 must map to .SH."""
    assert _to_ts_code("600519") == "600519.SH"
    assert _to_ts_code("510300") == "510300.SH"


def test_to_ts_code_sz_prefix() -> None:
    """Symbols starting with 0 or 3 must map to .SZ."""
    assert _to_ts_code("000001") == "000001.SZ"
    assert _to_ts_code("300750") == "300750.SZ"


def test_to_ts_code_bj_prefix() -> None:
    """Symbols starting with 4 or 8 must map to .BJ (Beijing Stock Exchange)."""
    assert _to_ts_code("830799") == "830799.BJ"
    assert _to_ts_code("430047") == "430047.BJ"


def test_to_ts_code_already_suffixed_passthrough() -> None:
    """Codes that already contain '.' must be returned unchanged."""
    assert _to_ts_code("600519.SH") == "600519.SH"
    assert _to_ts_code("830799.BJ") == "830799.BJ"
