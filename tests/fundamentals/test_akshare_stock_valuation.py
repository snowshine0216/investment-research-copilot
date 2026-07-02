from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd

import irc.fundamentals.akshare_stock_valuation as asv
from irc.fundamentals.akshare_stock_valuation import (
    _series_maps,
    fetch_stock_valuation_history,
)
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_FRAME = pd.DataFrame({
    "数据日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "PE(TTM)": [18.0, 18.1, 18.2],
    "市净率": [2.0, 2.05, 2.1],
    "总市值": [1.0e12, 1.0e12, 1.0e12],
})


def test_series_maps_extracts_pe_and_pb_by_date() -> None:
    pe_map, pb_map = _series_maps(_FRAME)
    assert pe_map["2026-05-30"] == 18.2
    assert pb_map["2026-05-28"] == 2.0


def test_series_maps_empty_frame_returns_empty_maps() -> None:
    pe_map, pb_map = _series_maps(pd.DataFrame())
    assert pe_map == {} and pb_map == {}


def test_series_maps_coerces_non_numeric_to_none() -> None:
    frame = pd.DataFrame({"数据日期": ["2026-05-30"], "PE(TTM)": ["-"], "市净率": ["-"]})
    pe_map, pb_map = _series_maps(frame)
    assert pe_map["2026-05-30"] is None and pb_map["2026-05-30"] is None


def test_fetch_returns_history_with_dividend_yield_none() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call", return_value=_FRAME
    ):
        out = fetch_stock_valuation_history("600519")
    assert isinstance(out, StockValuationHistory)
    assert out.stock_code == "600519"
    assert len(out.rows) == 3
    assert out.rows[-1].pe_ttm == 18.2
    assert out.rows[-1].pb == 2.1
    assert all(r.dividend_yield is None for r in out.rows)


def test_fetch_degrades_to_none_on_empty_frame() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_stock_valuation_history("600519") is None


def test_fetch_degrades_to_none_on_raise() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        side_effect=RuntimeError("boom"),
    ):
        assert fetch_stock_valuation_history("600519") is None


def test_fetch_logs_warn_on_exception(caplog) -> None:
    """Finding 2: exception in _fetch_frame must emit a WARN with symbol + reason."""
    import logging
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        side_effect=ValueError("timeout"),
    ), caplog.at_level(logging.WARNING, logger="irc.fundamentals.akshare_stock_valuation"):
        result = fetch_stock_valuation_history("000001")
    assert result is None
    assert any(
        "000001" in r.message and "ValueError" in r.message and "timeout" in r.message
        for r in caplog.records
    ), f"expected WARN with symbol+type+msg; got: {[r.message for r in caplog.records]}"


def test_fetch_logs_warn_on_unexpected_type(caplog) -> None:
    """Finding 3: non-DataFrame return in _fetch_frame must emit a WARN."""
    import logging
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        return_value={"unexpected": "dict"},
    ), caplog.at_level(logging.WARNING, logger="irc.fundamentals.akshare_stock_valuation"):
        result = fetch_stock_valuation_history("000001")
    assert result is None  # empty frame → no dates → None
    assert any(
        "000001" in r.message and "dict" in r.message
        for r in caplog.records
    ), f"expected WARN with symbol+type; got: {[r.message for r in caplog.records]}"


def test_fetch_frame_wraps_proxy_env_when_cn_proxy_set(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "9.9.9.9:1")
    seen = {}

    def fake_ak_call(fn_name, **kwargs):
        seen["https_proxy"] = os.environ.get("HTTPS_PROXY")
        return pd.DataFrame({"数据日期": ["2026-07-01"], "PE(TTM)": [10.0], "市净率": [1.0]})

    monkeypatch.setattr(asv, "_ak_call", fake_ak_call)
    df = asv._fetch_frame("600690")
    assert seen["https_proxy"] == "http://9.9.9.9:1"   # proxy active during the call
    assert "HTTPS_PROXY" not in os.environ or os.environ.get("HTTPS_PROXY") != "http://9.9.9.9:1"
    assert not df.empty


def test_fetch_frame_direct_when_no_cn_proxy(monkeypatch):
    monkeypatch.delenv("IRC_CN_PROXY", raising=False)
    seen = {}

    def fake_ak_call(fn_name, **kwargs):
        seen["https_proxy"] = os.environ.get("HTTPS_PROXY")
        return pd.DataFrame({"数据日期": ["2026-07-01"], "PE(TTM)": [10.0], "市净率": [1.0]})

    monkeypatch.setattr(asv, "_ak_call", fake_ak_call)
    asv._fetch_frame("600690")
    assert seen["https_proxy"] is None   # no proxy injected


def test_fetch_frame_holds_shared_akshare_proxy_lock(monkeypatch):
    """P1a: _fetch_frame must hold the SAME shared lock as the DXY path
    (irc.http_proxy.AKSHARE_PROXY_LOCK) around its proxy_env block — smoke test,
    no deadlock, single-threaded call count only."""
    monkeypatch.setenv("IRC_CN_PROXY", "9.9.9.9:1")

    class _LockProbe:
        def __init__(self) -> None:
            self.entered = 0

        def __enter__(self):
            self.entered += 1
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    probe = _LockProbe()
    monkeypatch.setattr(asv, "AKSHARE_PROXY_LOCK", probe)
    monkeypatch.setattr(
        asv, "_ak_call",
        lambda fn_name, **kwargs: pd.DataFrame(
            {"数据日期": ["2026-07-01"], "PE(TTM)": [10.0], "市净率": [1.0]}),
    )
    asv._fetch_frame("600690")
    assert probe.entered == 1
