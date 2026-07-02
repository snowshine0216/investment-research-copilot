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


from irc.monitor.em_raw import (  # noqa: E402
    _secid, fetch_board_pe_frame, fetch_stock_info_frame,
)


def test_secid_prefixes():
    assert _secid("600519") == "1.600519"
    assert _secid("000651") == "0.000651"
    assert _secid("300750") == "0.300750"


def test_fetch_board_pe_frame_paginates_and_stops_on_short_page():
    pages: list[dict] = []

    def http_get(url, *, params, headers, timeout, proxies=None):
        pn = int(params["pn"])
        pages.append(url)
        if pn == 1:
            return {"data": {"diff": [{"f14": f"B{i}", "f9": 10.0 + i}
                                      for i in range(100)]}}
        return {"data": {"diff": [{"f14": "LAST", "f9": 5.0}]}}  # short page → stop

    df = fetch_board_pe_frame(http_get=http_get, sleep=lambda _s: None)
    assert len(pages) == 2  # page 1 full (100) → page 2 short → stop
    assert "LAST" in set(df["板块名称"])
    assert len(df) == 101


def test_fetch_board_pe_frame_caps_at_max_pages():
    def http_get(url, *, params, headers, timeout, proxies=None):
        return {"data": {"diff": [{"f14": f"B{params['pn']}_{i}", "f9": 1.0}
                                   for i in range(100)]}}  # always full → never stops

    df = fetch_board_pe_frame(http_get=http_get, sleep=lambda _s: None)
    assert len(df) == 100 * 10  # capped at _MAX_PAGES


def test_fetch_stock_info_frame_one_call_records_proxy(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "1.2.3.4:9")
    captured = {}

    def http_get(url, *, params, headers, timeout, proxies=None):
        captured["secid"] = params["secid"]
        captured["proxies"] = proxies
        return {"data": {"f57": "600690", "f58": "海尔智家", "f127": "白色家电"}}

    df = fetch_stock_info_frame("600690", http_get=http_get)
    assert captured["secid"] == "1.600690"
    assert captured["proxies"] == {"http": "http://1.2.3.4:9", "https": "http://1.2.3.4:9"}
    assert df[df["item"] == "行业"]["value"].iloc[0] == "白色家电"
