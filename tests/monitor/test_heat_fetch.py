from __future__ import annotations

import pandas as pd
import pytest

from irc.monitor.heat_fetch import (
    fetch_purchase_table,
    heat_inputs_for,
    parse_purchase_status,
    _RESTRICTION_CAP_THRESHOLD,
)


def _table(rows: list[dict]) -> pd.DataFrame:
    """Build a fund_purchase_em-shaped frame from minimal rows."""
    return pd.DataFrame(rows)


# ── parse_purchase_status: not-restricted (open + uncapped) ───────────────────

def test_open_status_high_cap_not_restricted():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is False


# ── parse_purchase_status: restricted by status ───────────────────────────────

@pytest.mark.parametrize("status", ["暂停申购", "限大额", "场内交易", "封闭期", "认购期", ""])
def test_non_open_status_is_restricted(status):
    # cap is high, but status alone (∉ {开放申购}) restricts.
    t = _table([{"基金代码": "519069", "申购状态": status, "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "519069") is True


# ── parse_purchase_status: restricted by cap ──────────────────────────────────

def test_open_status_low_cap_is_restricted():
    # 开放申购 but daily cap below 1e8 → restricted (限大额-style).
    t = _table([{"基金代码": "006533", "申购状态": "开放申购", "日累计限定金额": 1e5}])
    assert parse_purchase_status(t, "006533") is True


def test_cap_exactly_at_threshold_not_restricted():
    # cap == 1e8 is NOT < 1e8 → open status + at-threshold cap = not restricted.
    t = _table([{"基金代码": "000083", "申购状态": "开放申购",
                 "日累计限定金额": _RESTRICTION_CAP_THRESHOLD}])
    assert parse_purchase_status(t, "000083") is False


# ── parse_purchase_status: None paths (absent / unparseable / bad shape) ───────

def test_fund_absent_returns_none():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "999999") is None


def test_missing_status_column_returns_none():
    t = _table([{"基金代码": "000083", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is None


def test_missing_cap_column_falls_back_to_status_only():
    # No cap column: rule degrades to the status leg alone (open → not restricted),
    # NOT to None — status is parseable, so we emit an honest bool.
    t = _table([{"基金代码": "000083", "申购状态": "开放申购"}])
    assert parse_purchase_status(t, "000083") is False


def test_missing_code_column_returns_none():
    t = _table([{"申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is None


def test_none_table_returns_none():
    assert parse_purchase_status(None, "000083") is None


def test_empty_table_returns_none():
    assert parse_purchase_status(_table([]), "000083") is None


def test_unparseable_cap_with_open_status_not_restricted():
    # 开放申购 + non-numeric cap → cap leg can't fire; status leg says open → not restricted.
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": "—"}])
    assert parse_purchase_status(t, "000083") is False


def test_code_zero_pad_match():
    # Defensive: an int-typed code column still matches the 6-digit id.
    t = _table([{"基金代码": 83, "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert parse_purchase_status(t, "000083") is False


# ── fetch_purchase_table: never raises, returns None on failure ───────────────

def test_fetch_returns_table_from_injected_fetch():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    out = fetch_purchase_table(fetch=lambda: t)
    assert out is t


def test_fetch_returns_none_when_fetch_raises():
    def _boom():
        raise RuntimeError("network down")
    assert fetch_purchase_table(fetch=_boom) is None


def test_fetch_returns_none_on_empty_frame():
    assert fetch_purchase_table(fetch=lambda: _table([])) is None


def test_fetch_returns_none_on_non_dataframe():
    assert fetch_purchase_table(fetch=lambda: "not a frame") is None


# ── heat_inputs_for: always aum_delta_pct=None; restricted threads parse result ─

def test_heat_inputs_for_open_fund():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    restricted, aum = heat_inputs_for("000083", purchase_table=t)
    assert restricted is False and aum is None


def test_heat_inputs_for_restricted_fund():
    t = _table([{"基金代码": "006533", "申购状态": "限大额", "日累计限定金额": 1e5}])
    restricted, aum = heat_inputs_for("006533", purchase_table=t)
    assert restricted is True and aum is None


def test_heat_inputs_for_none_table_yields_none_restricted():
    restricted, aum = heat_inputs_for("000083", purchase_table=None)
    assert restricted is None and aum is None


def test_heat_inputs_for_absent_fund_yields_none_restricted():
    t = _table([{"基金代码": "000083", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    restricted, aum = heat_inputs_for("999999", purchase_table=t)
    assert restricted is None and aum is None
