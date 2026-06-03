from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals.akshare_index_valuation import (
    _extract_latest_value,
    fetch_cn_index_valuation,
)
from irc.fundamentals.index_valuation_types import IndexValuation


# ---------- pure extraction helper ----------

_PE_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "平均市盈率": [11.8, 11.9, 12.1],
})

_PB_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "市净率": [1.28, 1.29, 1.31],
})


def test_extract_latest_value_picks_latest_date_row() -> None:
    val = _extract_latest_value(_PE_FRAME, ("平均市盈率", "市盈率", "pe"))
    assert val == 12.1


def test_extract_latest_value_returns_none_when_no_candidate_column() -> None:
    val = _extract_latest_value(_PE_FRAME, ("市净率", "pb"))
    assert val is None


def test_extract_latest_value_returns_none_on_empty_frame() -> None:
    assert _extract_latest_value(pd.DataFrame(), ("平均市盈率",)) is None


def test_extract_latest_value_coerces_non_float_to_none() -> None:
    frame = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": ["-"]})
    assert _extract_latest_value(frame, ("平均市盈率",)) is None


# ---------- fetcher ----------

def test_fetch_unknown_index_key_returns_none_without_calling_ak() -> None:
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        out = fetch_cn_index_valuation("not_a_broad_index")
    assert out is None
    mocked.assert_not_called()


def test_fetch_recognised_index_returns_pe_and_pb() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake
    ), patch(
        "irc.fundamentals.akshare_index_valuation._today_iso",
        return_value="2026-05-31",
    ):
        out = fetch_cn_index_valuation("csi300")
    assert isinstance(out, IndexValuation)
    assert out.index_key == "csi300"
    assert out.pe_ttm == 12.1
    assert out.pb == 1.31
    assert out.dividend_yield is None  # legulegu PE/PB endpoints carry no div col
    assert out.as_of_iso == "2026-05-31"


def test_fetch_passes_chinese_name_to_ak_call() -> None:
    calls: list[dict] = []

    def _fake(fn_name, **kwargs):
        calls.append({"fn": fn_name, **kwargs})
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch("irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake):
        fetch_cn_index_valuation("csi300")
    # csi300 -> 沪深300 (from _BROAD_INDEX_DISPLAY)
    assert any(c.get("symbol") == "沪深300" for c in calls)


def test_fetch_degrades_to_none_on_adapter_exception() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        side_effect=RuntimeError("network down"),
    ):
        out = fetch_cn_index_valuation("csi300")
    assert out is None


def test_fetch_returns_valuation_with_none_metrics_on_empty_frames() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=pd.DataFrame(),
    ), patch(
        "irc.fundamentals.akshare_index_valuation._today_iso",
        return_value="2026-05-31",
    ):
        out = fetch_cn_index_valuation("csi300")
    assert isinstance(out, IndexValuation)
    assert out.pe_ttm is None
    assert out.pb is None
    assert out.dividend_yield is None


from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory


def test_fetch_history_unknown_index_returns_none_without_calling_ak() -> None:
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        out = fetch_cn_index_valuation_history("not_a_broad_index")
    assert out is None
    mocked.assert_not_called()


def test_fetch_history_extracts_full_series() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake
    ):
        out = fetch_cn_index_valuation_history("csi300")
    assert isinstance(out, IndexValuationHistory)
    assert out.index_key == "csi300"
    # _PE_FRAME / _PB_FRAME each have 3 dated rows aligned on 日期.
    assert len(out.rows) == 3
    assert [r.date_iso for r in out.rows] == ["2026-05-28", "2026-05-29", "2026-05-30"]
    assert out.rows[-1].pe_ttm == 12.1
    assert out.rows[-1].pb == 1.31
    assert out.rows[-1].dividend_yield is None


def test_fetch_history_degrades_to_none_on_adapter_exception() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        side_effect=RuntimeError("network down"),
    ):
        assert fetch_cn_index_valuation_history("csi300") is None


def test_fetch_history_returns_none_on_empty_frames() -> None:
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_cn_index_valuation_history("csi300") is None
