from __future__ import annotations
from irc.monitor.render_drilldown import all_na_columns


def test_all_na_columns_detects_fully_dark_column():
    rows = [{"pe": None, "pb": 10.0}, {"pe": None, "pb": 12.0}]
    result = all_na_columns(rows, columns=("pe", "pb"))
    assert result == frozenset({"pe"})


def test_all_na_columns_partial_data_not_collapsed():
    rows = [{"pe": 15.0, "pb": 10.0}, {"pe": None, "pb": 12.0}]
    result = all_na_columns(rows, columns=("pe", "pb"))
    assert result == frozenset()


def test_all_na_columns_missing_key_treated_as_none():
    rows = [{"pb": 10.0}, {"pb": 12.0}]   # 'pe' key entirely absent
    result = all_na_columns(rows, columns=("pe", "pb"))
    assert result == frozenset({"pe"})


def test_all_na_columns_empty_rows_yields_empty_frozenset():
    assert all_na_columns([], columns=("pe", "pb")) == frozenset()
