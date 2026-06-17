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
