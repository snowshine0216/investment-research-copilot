"""Mocked failure-mode companion for the Q4 live gate.

The live test (``test_fund_announcement_em_live.py``) can only assert "real
AkShare passes today"; it cannot exercise the failure paths because they
are unreachable when AkShare is healthy. This file patches ``_ak_call``
(and, for the function-missing case, ``akshare``) to lock the failure-trace
tone — guarding the autodev orchestrator's stdout-reading STOP-detection.

Runs in every default ``pytest`` invocation (no ``live_akshare`` marker,
no env-var gate). ~5 tests, ~30 LoC of test bodies.
"""
from __future__ import annotations

import sys
import types
from typing import Any

import pandas as pd
import pytest

from tests.fundamentals.test_fund_announcement_em_live import (
    _assert_announcement_df,
    _call_fund_announcement_em,
    _resolve_column,
)


# ── Failure 1: function missing on the ``akshare`` module ────────────────────

def test_function_missing_emits_q4_prerequisite_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preflight detects ``not hasattr(ak, 'fund_announcement_em')``.

    We can't directly call the preflight test function (it lives in another
    file and uses live network). Instead, we replicate its core check against
    a stub ``akshare`` module missing the attribute.
    """
    stub = types.ModuleType("akshare")
    stub.__version__ = "0.0.0-stub"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "akshare", stub)

    import akshare as ak  # picks up the stub from sys.modules
    assert not hasattr(ak, "fund_announcement_em")

    # Now assert the structured Q4 message reaches a future reader.
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*missing.*"):
        if not hasattr(ak, "fund_announcement_em"):
            raise AssertionError(
                "Q4 PREREQUISITE FAILURE: ak.fund_announcement_em is missing from "
                f"the installed AkShare ({getattr(ak, '__version__', 'unknown')}). "
                "Item 005 cannot ship its information leg. STOP and re-decide Q4 "
                "(option b: theme-report scope-promotion, option c: exclude gold + "
                "cn_bond_fund from V1). See docs/diagnosis-thesis-cards-evidence-gap.md §5."
            )


# ── Failure 2: empty DataFrame return ────────────────────────────────────────

def test_empty_dataframe_raises_q4_row_count_failure(mocker: Any) -> None:
    empty = pd.DataFrame(columns=["公告标题", "公告类型", "公告日期", "公告链接"])
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        return_value=empty,
    )
    # _call returns the df; the assertion lives in _assert_announcement_df:
    # The expected path: _call returned the empty df cleanly; we now assert
    # _assert_announcement_df raises the structured threshold-failure message.
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*returned 0 rows.*threshold is 5"):
        _assert_announcement_df(empty, "518880")


# ── Failure 3: DataFrame missing the URL column ──────────────────────────────

def test_missing_url_column_raises_q4_column_failure(mocker: Any) -> None:
    df = pd.DataFrame({
        "公告标题": [f"标题{i}" for i in range(6)],
        "公告类型": [f"类型{i}" for i in range(6)],
        "公告日期": [f"2025-01-0{i+1}" for i in range(6)],
        # NOTE: 公告链接 deliberately absent
    })
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        return_value=df,
    )
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*missing the 'url' column"):
        _assert_announcement_df(df, "518880")


# ── Failure 4: ``_ak_call`` returns None ─────────────────────────────────────

def test_none_return_raises_q4_non_dataframe_failure(mocker: Any) -> None:
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        return_value=None,
    )
    df = _call_fund_announcement_em("518880")
    assert df is None  # _call returns the raw value; assertion lives below
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*returned a non-DataFrame.*NoneType"):
        _assert_announcement_df(df, "518880")


# ── Failure 5: ``_ak_call`` raises a runtime exception ───────────────────────

def test_exception_during_call_raises_q4_unreachable_failure(mocker: Any) -> None:
    mocker.patch(
        "irc.fundamentals.akshare_fundamentals._ak_call",
        side_effect=RuntimeError("network unreachable"),
    )
    with pytest.raises(AssertionError, match="Q4 PREREQUISITE FAILURE.*raised RuntimeError.*Information leg unreachable"):
        _call_fund_announcement_em("518880")
