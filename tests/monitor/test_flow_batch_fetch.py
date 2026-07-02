from __future__ import annotations

from irc.monitor.flow_batch_fetch import (
    build_secids, fetch_flow_today_batch, parse_ulist,
)


def test_parse_ulist_percent_point_boundaries():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0}, {"f12": "000651", "f184": 3.0},
        {"f12": "300750", "f184": 0.01}, {"f12": "600690", "f184": 0.03},
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": 1.0, "000651": 3.0, "300750": 0.01, "600690": 0.03}


def test_parse_ulist_blank_and_dash_are_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": "-"}, {"f12": "000651", "f184": ""},
        {"f12": "300750", "f184": None},
    ]}}
    assert parse_ulist(payload) == {"600519": None, "000651": None, "300750": None}


def test_parse_ulist_data_null_is_empty():
    assert parse_ulist({"data": None}) == {}
    assert parse_ulist({}) == {}


def test_build_secids_prefixes():
    assert build_secids(("600519", "000651", "300750")) == "1.600519,0.000651,0.300750"


def test_fetch_flow_today_batch_one_call_via_proxy(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "1.2.3.4:9")
    calls = {"n": 0}

    def http_get(url, *, params, headers, timeout, proxies=None):
        calls["n"] += 1
        assert proxies == {"http": "http://1.2.3.4:9", "https": "http://1.2.3.4:9"}
        assert params["secids"] == "1.600519,0.000651"
        return {"data": {"diff": [{"f12": "600519", "f184": 4.86},
                                  {"f12": "000651", "f184": 7.42}]}}

    out = fetch_flow_today_batch(("600519", "000651"), http_get=http_get)
    assert calls["n"] == 1                       # ONE batch call, not 53/not per-fund
    assert out == {"600519": 4.86, "000651": 7.42}


def test_fetch_flow_today_batch_blank_body_all_none():
    out = fetch_flow_today_batch(
        ("600519",), http_get=lambda *a, **k: {"data": None})
    assert out == {"600519": None}              # never fabricated
