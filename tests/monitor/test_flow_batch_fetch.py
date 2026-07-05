from __future__ import annotations

from irc.monitor.flow_batch_fetch import (
    build_secids, fetch_flow_today_batch, parse_ulist,
)


def test_parse_ulist_industry_from_f100_not_numeric_f127():
    """REGRESSION (probe 2026-07-04): EastMoney field codes are interface-specific.
    In `ulist.np/get`, f127 is a NUMERIC field (涨速/change-rate), NOT 行业 —
    industry rides on f100 (matches stock/get's f127 semantics). The batch must
    read industry from f100 and ignore f127's number. Real payload shape from the
    live probe: 600519→白酒Ⅱ (f127=0.76), 300750→电池 (f127=-3.31)."""
    payload = {"data": {"diff": [
        {"f12": "600519", "f14": "贵州茅台", "f184": -5.3, "f100": "白酒Ⅱ", "f127": 0.76},
        {"f12": "300750", "f14": "宁德时代", "f184": -1.98, "f100": "电池", "f127": -3.31},
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (-5.3, "白酒Ⅱ"), "300750": (-1.98, "电池")}


def test_parse_ulist_percent_point_boundaries_with_f100():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0, "f100": "酿酒行业"},
        {"f12": "000651", "f184": 3.0, "f100": "家电行业"},
        {"f12": "300750", "f184": 0.01, "f100": "电池"},
        {"f12": "600690", "f184": 0.03, "f100": "家电行业"},
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (1.0, "酿酒行业"), "000651": (3.0, "家电行业"),
                   "300750": (0.01, "电池"), "600690": (0.03, "家电行业")}


def test_parse_ulist_f100_absent_blank_dash_whitespace_are_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0},                      # f100 missing
        {"f12": "000651", "f184": 2.0, "f100": ""},          # blank
        {"f12": "300750", "f184": 3.0, "f100": "-"},         # dash sentinel
        {"f12": "600690", "f184": 4.0, "f100": "   "},       # whitespace-only
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (1.0, None), "000651": (2.0, None),
                   "300750": (3.0, None), "600690": (4.0, None)}


def test_parse_ulist_f100_stripped_and_nonstring_is_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0, "f100": " 酿酒行业 "},
        {"f12": "000651", "f184": 2.0, "f100": 42},          # never fabricated
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (1.0, "酿酒行业"), "000651": (2.0, None)}


def test_parse_ulist_blank_and_dash_f184_are_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": "-"}, {"f12": "000651", "f184": ""},
        {"f12": "300750", "f184": None},
    ]}}
    assert parse_ulist(payload) == {"600519": (None, None), "000651": (None, None),
                                    "300750": (None, None)}


def test_parse_ulist_data_null_is_empty():
    assert parse_ulist({"data": None}) == {}
    assert parse_ulist({}) == {}


def test_parse_ulist_dict_diff_shape_tolerated():
    payload = {"data": {"diff": {"0": {"f12": "600519", "f184": 4.86, "f100": "酿酒行业"}}}}
    assert parse_ulist(payload) == {"600519": (4.86, "酿酒行业")}


def test_parse_ulist_flow_half_identity_with_pre_change_parser():
    """AC-1 flow-identity guard: for any fixture payload, the flow halves equal
    the PRE-CHANGE parse_ulist output exactly (guards the flow_reconciliation
    byte-identity contract at the parse level — the f184 coercion path is
    untouched by the 行业 widening)."""
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 4.86, "f100": "酿酒行业"},
        {"f12": "000651", "f184": "-", "f100": "家电行业"},
        {"f12": "300750", "f184": 0.01},
        {"f12": "600690", "f184": None, "f100": ""},
    ]}}
    pre_change = {"600519": 4.86, "000651": None, "300750": 0.01, "600690": None}
    assert {sym: pair[0] for sym, pair in parse_ulist(payload).items()} == pre_change


def test_build_secids_prefixes():
    assert build_secids(("600519", "000651", "300750")) == "1.600519,0.000651,0.300750"


def test_fetch_flow_today_batch_one_call_two_maps_via_proxy(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "1.2.3.4:9")
    calls = {"n": 0}

    def http_get(url, *, params, headers, timeout, proxies=None):
        calls["n"] += 1
        assert proxies == {"http": "http://1.2.3.4:9", "https": "http://1.2.3.4:9"}
        assert params["secids"] == "1.600519,0.000651"
        assert params["fields"] == "f12,f14,f184,f100"     # AC-2: ONE call, 行业=f100
        return {"data": {"diff": [{"f12": "600519", "f184": 4.86, "f100": "酿酒行业"},
                                  {"f12": "000651", "f184": 7.42}]}}

    flow, industry = fetch_flow_today_batch(("600519", "000651"), http_get=http_get)
    assert calls["n"] == 1                       # ONE batch call, not per-symbol
    assert flow == {"600519": 4.86, "000651": 7.42}
    assert industry == {"600519": "酿酒行业", "000651": None}


def test_fetch_flow_today_batch_blank_body_all_none():
    flow, industry = fetch_flow_today_batch(
        ("600519",), http_get=lambda *a, **k: {"data": None})
    assert flow == {"600519": None}              # never fabricated
    assert industry == {"600519": None}
