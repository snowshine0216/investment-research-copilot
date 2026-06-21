from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from irc.monitor.industry_valuation import (
    parse_industry_pe,
    parse_stock_industry,
    fetch_industry_pe,
    fetch_stock_industry_map,
)


def test_parse_industry_pe_extracts_name_to_pe():
    df = pd.DataFrame({"板块名称": ["银行", "白酒"], "市盈率": ["6.5", "30.2"]})
    out = parse_industry_pe(df)
    assert out == {"银行": 6.5, "白酒": 30.2}


def test_parse_industry_pe_drops_nonpositive_and_nan():
    df = pd.DataFrame({"板块名称": ["亏损业", "正常业", "空值业"],
                       "市盈率": ["-12.0", "10.0", "nan"]})
    out = parse_industry_pe(df)
    assert out == {"正常业": 10.0}  # non-positive + NaN dropped


def test_parse_industry_pe_unexpected_shape_is_empty():
    assert parse_industry_pe(None) == {}
    assert parse_industry_pe(pd.DataFrame()) == {}
    assert parse_industry_pe(pd.DataFrame({"x": [1]})) == {}


def test_parse_stock_industry_reads_industry_row():
    # stock_individual_info_em returns a long (item, value) table.
    df = pd.DataFrame({"item": ["总市值", "行业", "上市时间"],
                       "value": ["1.2e12", "酿酒行业", "20010827"]})
    assert parse_stock_industry(df) == "酿酒行业"


def test_parse_stock_industry_missing_industry_is_none():
    df = pd.DataFrame({"item": ["总市值"], "value": ["1.2e12"]})
    assert parse_stock_industry(df) is None
    assert parse_stock_industry(None) is None
    assert parse_stock_industry(pd.DataFrame()) is None


def test_fetch_industry_pe_caches_and_round_trips(tmp_path: Path):
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return pd.DataFrame({"板块名称": ["银行"], "市盈率": ["6.5"]})

    cache_dir = tmp_path / "industry_pe"
    out1 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                             fetch=fake_fetch, sleep=lambda _s: None)
    out2 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                             fetch=fake_fetch, sleep=lambda _s: None)
    assert out1 == out2 == {"银行": 6.5}
    assert calls["n"] == 1  # second call served from cache
    # on-disk form is sorted-key JSON of primitives (byte-stable)
    payload = json.loads((cache_dir / "2026-06-21.json").read_text(encoding="utf-8"))
    assert payload == {"银行": 6.5}


def test_fetch_industry_pe_never_raises_returns_empty(tmp_path: Path):
    def boom():
        raise RuntimeError("network down")

    out = fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-06-21",
                            fetch=boom, sleep=lambda _s: None)
    assert out == {}


def _info_df(industry: str) -> pd.DataFrame:
    return pd.DataFrame({"item": ["行业"], "value": [industry]})


def test_fetch_stock_industry_map_per_symbol_cache_ok_and_miss(tmp_path: Path):
    seen: list[str] = []

    def fake_fetch(symbol):
        seen.append(symbol)
        if symbol == "600519":
            return _info_df("酿酒行业")
        raise RuntimeError("dead symbol")  # 000001 → miss

    cache_dir = tmp_path / "stock_industry"
    out = fetch_stock_industry_map(("600519", "000001", "600519"),
                                   cache_dir=cache_dir, today="2026-06-21",
                                   fetch=fake_fetch, sleep=lambda _s: None)
    assert out == {"600519": "酿酒行业", "000001": None}
    assert seen == ["600519", "000001"]  # deduped, miss not re-fetched in-run
    # cache persists ok+miss; re-run hits NEITHER endpoint
    seen.clear()
    out2 = fetch_stock_industry_map(("600519", "000001"),
                                    cache_dir=cache_dir, today="2026-06-21",
                                    fetch=fake_fetch, sleep=lambda _s: None)
    assert out2 == {"600519": "酿酒行业", "000001": None}
    assert seen == []
    payload = json.loads((cache_dir / "2026-06-21.json").read_text(encoding="utf-8"))
    assert payload["000001"] == {"status": "miss", "industry": None}
    assert payload["600519"] == {"status": "ok", "industry": "酿酒行业"}


def test_fetch_stock_industry_map_per_call_never_raises(tmp_path: Path):
    def boom(symbol):
        raise RuntimeError("x")

    out = fetch_stock_industry_map(("600519",), cache_dir=tmp_path / "si",
                                   today="2026-06-21", fetch=boom, sleep=lambda _s: None)
    assert out == {"600519": None}
