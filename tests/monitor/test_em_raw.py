from __future__ import annotations

import pandas as pd

from irc.monitor.em_raw import parse_clist_boards, parse_stock_info


def test_parse_clist_boards_maps_f14_and_f9():
    payload = {"data": {"diff": [
        {"f12": "BK0428", "f14": "电力", "f9": 19.68},
        {"f12": "BK0433", "f14": "农林牧渔", "f9": 76.9},
    ]}}
    df = parse_clist_boards(payload)
    assert list(df.columns) == ["板块名称", "市盈率"]
    assert set(df["板块名称"]) == {"电力", "农林牧渔"}
    assert df.set_index("板块名称").loc["电力", "市盈率"] == 19.68


def test_parse_clist_boards_tolerates_dict_diff_shape():
    payload = {"data": {"diff": {"0": {"f14": "电力", "f9": 19.68}}}}
    df = parse_clist_boards(payload)
    assert df.set_index("板块名称").loc["电力", "市盈率"] == 19.68


def test_parse_clist_boards_data_null_is_empty_frame():
    # F4/F5 drift signature: {"data": null}
    df = parse_clist_boards({"data": None})
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_parse_stock_info_reads_f127_industry_with_drift_keys():
    # EastMoney added dlmkts/dsc top-level keys (F5). The raw parser must ignore them.
    payload = {"dlmkts": "x", "dsc": "y",
               "data": {"f57": "600690", "f58": "海尔智家", "f127": "白色家电"}}
    df = parse_stock_info(payload)
    assert set(df.columns) == {"item", "value"}
    row = df[df["item"] == "行业"]
    assert row["value"].iloc[0] == "白色家电"


def test_parse_stock_info_missing_f127_is_wellformed_without_industry_row():
    # well-formed data, no 行业 → DEAD path preserved (item/value cols present, no 行业)
    payload = {"data": {"f57": "600690", "f58": "海尔智家", "f127": None}}
    df = parse_stock_info(payload)
    assert set(df.columns) == {"item", "value"}
    assert (df["item"] == "行业").sum() == 0


def test_parse_stock_info_data_null_is_blank_frame():
    # F5 drift / throttle: {"data": null} → blank frame → TRANSIENT upstream
    df = parse_stock_info({"dlmkts": "x", "data": None})
    assert isinstance(df, pd.DataFrame)
    assert df.empty
