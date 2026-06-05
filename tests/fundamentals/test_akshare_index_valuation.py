from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from irc.fundamentals.akshare_index_valuation import (
    _CSINDEX_PE_TTM_COL,
    _extract_latest_value,
    fetch_cn_index_valuation,
    fetch_cn_index_valuation_history,
    fetch_cn_sector_index_valuation_history,
)
from irc.fundamentals.index_valuation_types import IndexValuation, IndexValuationHistory


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


# csindex-shaped frame: 市盈率1 (PE-TTM) + 市盈率2 (LYR) + 股息率 cols, NO pb col.
_CSINDEX_FRAME = pd.DataFrame({
    "日期": ["2026-05-26", "2026-05-27", "2026-05-28"],
    "市盈率1": [26.50, 26.80, 26.97],
    "市盈率2": [29.10, 29.20, 29.28],
    "股息率1": [1.10, 1.10, 1.12],
    "股息率2": [1.20, 1.20, 1.22],
})


def test_csindex_pe_ttm_col_is_市盈率1():
    assert _CSINDEX_PE_TTM_COL == "市盈率1"


def test_sector_fetch_unknown_slug_returns_none_without_calling_ak():
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        out = fetch_cn_sector_index_valuation_history("not_a_sector")
    assert out is None
    mocked.assert_not_called()


def test_sector_fetch_reads_市盈率1_and_sets_pb_none():
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=_CSINDEX_FRAME,
    ):
        out = fetch_cn_sector_index_valuation_history("csi_nonferrous")
    assert isinstance(out, IndexValuationHistory)
    assert out.index_key == "csi_nonferrous"
    assert len(out.rows) == 3
    assert [r.date_iso for r in out.rows] == ["2026-05-26", "2026-05-27", "2026-05-28"]
    # PE comes from 市盈率1 (TTM), NOT 市盈率2.
    assert out.rows[-1].pe_ttm == pytest.approx(26.97)
    # csindex has NO PB column.
    assert all(r.pb is None for r in out.rows)


def test_sector_fetch_fails_if_only_legulegu_pe_names_present():
    # A frame carrying ONLY legulegu PE names (平均市盈率) must NOT yield PE —
    # proves the fetcher does not fall back to _PE_COLS.
    legulegu_frame = pd.DataFrame({
        "日期": ["2026-05-28"],
        "平均市盈率": [12.1],
    })
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=legulegu_frame,
    ):
        out = fetch_cn_sector_index_valuation_history("csi_nonferrous")
    # No 市盈率1 column → no usable PE rows → degrade to None.
    assert out is None


def test_sector_fetch_passes_csi_code_to_ak_call():
    calls: list[dict] = []

    def _fake(fn_name, **kwargs):
        calls.append({"fn": fn_name, **kwargs})
        return _CSINDEX_FRAME

    with patch("irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake):
        fetch_cn_sector_index_valuation_history("csi_nonferrous")
    assert calls and calls[0]["fn"] == "stock_zh_index_value_csindex"
    # csi_nonferrous -> 930708
    assert calls[0].get("symbol") == "930708"


def test_sector_fetch_degrades_to_none_on_adapter_exception():
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        side_effect=RuntimeError("network down"),
    ):
        assert fetch_cn_sector_index_valuation_history("csi_nonferrous") is None


def test_sector_code_map_is_sot_backed():
    from irc.fundamentals.akshare_index_valuation import _SECTOR_INDEX_CODE
    from irc.opportunity.sector_indices import SECTOR_INDEX_CODE

    assert _SECTOR_INDEX_CODE is SECTOR_INDEX_CODE
    assert _SECTOR_INDEX_CODE["csi_robotics"] == "H30590"  # new slug resolvable


def test_sector_fetch_resolves_new_slug_code(monkeypatch):
    import pandas as pd

    from irc.fundamentals import akshare_index_valuation as m

    captured = {}

    def fake_ak(fn_name, **kwargs):
        captured["symbol"] = kwargs.get("symbol")
        return pd.DataFrame({"日期": ["2026-06-04"], "市盈率1": [28.5]})

    monkeypatch.setattr(m, "_ak_call", fake_ak)
    out = m.fetch_cn_sector_index_valuation_history("csi_robotics")
    assert out is not None
    assert captured["symbol"] == "H30590"


def test_sector_fetch_returns_none_on_empty_frame():
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_cn_sector_index_valuation_history("csi_nonferrous") is None
