# tests/monitor/test_flow_fetch.py
from __future__ import annotations

import json as _json

import pandas as pd
import pytest

from irc.monitor.flow_fetch import (
    _cache_payload,
    _load_cache_payload,
    _market_of,
    fetch_flow_series,
    parse_main_net_pct,
)


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Task 1.1: parse_main_net_pct
# ---------------------------------------------------------------------------

def test_parse_extracts_date_and_net_pct_percent_points():
    # akshare parses 主力净流入-净占比 already as percent-points (12.34 means 12.34%).
    df = _df([
        {"日期": "2026-06-16", "主力净流入-净占比": 12.34},
        {"日期": "2026-06-17", "主力净流入-净占比": -3.5},
    ])
    assert parse_main_net_pct(df) == (("2026-06-16", 12.34), ("2026-06-17", -3.5))


def test_parse_sorts_ascending_by_date():
    df = _df([
        {"日期": "2026-06-17", "主力净流入-净占比": 1.0},
        {"日期": "2026-06-16", "主力净流入-净占比": 2.0},
    ])
    assert parse_main_net_pct(df) == (("2026-06-16", 2.0), ("2026-06-17", 1.0))


def test_parse_drops_nonnumeric_or_nan_net_pct():
    df = _df([
        {"日期": "2026-06-16", "主力净流入-净占比": "—"},
        {"日期": "2026-06-17", "主力净流入-净占比": float("nan")},
        {"日期": "2026-06-18", "主力净流入-净占比": 4.0},
    ])
    assert parse_main_net_pct(df) == (("2026-06-18", 4.0),)


def test_parse_unexpected_shape_is_empty_not_fabricated():
    df = _df([{"wrong": 1}])
    assert parse_main_net_pct(df) == ()


# ---------------------------------------------------------------------------
# Task 1.2: _market_of
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol,market", [
    ("600519", "sh"), ("601318", "sh"),
    ("000001", "sz"), ("300750", "sz"),
    ("830799", "bj"), ("430047", "bj"),
])
def test_market_of_routes_a_share_prefixes(symbol, market):
    assert _market_of(symbol) == market


@pytest.mark.parametrize("symbol", ["00700", "AAPL", "09988"])
def test_market_of_non_a_share_is_none(symbol):
    # HK/US lines (QDII look-through) are not A-shares → None → never fetched.
    assert _market_of(symbol) is None


# ---------------------------------------------------------------------------
# Task 1.3: cache schema — serialize / load round-trip
# ---------------------------------------------------------------------------

def test_cache_payload_is_byte_stable_sorted_and_rounded():
    by_symbol = {
        "600519": (("2026-06-16", 1.23456), ("2026-06-15", 2.0)),
        "000001": None,  # confirmed miss
    }
    payload = _cache_payload(by_symbol)
    # symbols sorted; rows sorted ascending by date; main_net_pct rounded 4dp.
    assert list(payload.keys()) == ["000001", "600519"]
    assert payload["000001"] == {"status": "miss", "rows": []}
    assert payload["600519"] == {
        "status": "ok",
        "rows": [{"date": "2026-06-15", "main_net_pct": 2.0},
                 {"date": "2026-06-16", "main_net_pct": 1.2346}],
    }


def test_cache_roundtrip_maps_ok_to_series_and_miss_to_none():
    payload = {
        "600519": {"status": "ok", "rows": [{"date": "2026-06-16", "main_net_pct": 1.5}]},
        "000001": {"status": "miss", "rows": []},
    }
    loaded = _load_cache_payload(payload)
    assert loaded["600519"] == (("2026-06-16", 1.5),)
    assert loaded["000001"] is None


# ---------------------------------------------------------------------------
# Task 1.4: fetch_flow_series — edge orchestration
# ---------------------------------------------------------------------------

def _fake_df(pct: float) -> pd.DataFrame:
    return pd.DataFrame([{"日期": "2026-06-16", "主力净流入-净占比": pct}])


def test_fetch_dedups_symbols_and_writes_cache(tmp_path):
    calls: list[str] = []

    def fake_fetch(*, stock, market):
        calls.append(stock)
        return _fake_df(5.0)

    out = fetch_flow_series(
        ("600519", "600519", "000001"),  # duplicate 600519
        cache_dir=tmp_path, today="2026-06-16", fetch=fake_fetch, sleep=lambda _: None,
    )
    assert calls == ["600519", "000001"]  # deduped, ordered
    assert out["600519"] == (("2026-06-16", 5.0),)
    cache = _json.loads((tmp_path / "2026-06-16.json").read_text())
    assert set(cache) == {"000001", "600519"}


def test_fetch_is_idempotent_within_a_day_no_refetch(tmp_path):
    calls: list[str] = []

    def fake_fetch(*, stock, market):
        calls.append(stock)
        return _fake_df(5.0)

    fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16",
                      fetch=fake_fetch, sleep=lambda _: None)
    fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16",
                      fetch=fake_fetch, sleep=lambda _: None)
    assert calls == ["600519"]  # second call served from cache


def test_fetch_failure_is_transient_not_persisted_and_retried(tmp_path):
    # A raised fetch (rate limit / timeout) is TRANSIENT: caller sees no data,
    # but it is NOT cached as a confirmed miss → a re-run retries it (ADR 0019).
    def boom(*, stock, market):
        raise RuntimeError("rate limited")

    out = fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16",
                            fetch=boom, sleep=lambda _: None)
    assert out["600519"] is None  # flow_no_data, never a crash
    assert not (tmp_path / "2026-06-16.json").is_file()  # nothing poisoned

    out2 = fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16",
                             fetch=lambda *, stock, market: _fake_df(5.0),
                             sleep=lambda _: None)
    assert out2["600519"] == (("2026-06-16", 5.0),)  # retried, recovered


def test_corrupt_cache_does_not_crash_brief_refetches(tmp_path):
    # A partial on-disk ok entry (row missing main_net_pct) must degrade to a
    # refetch, never crash the brief (fetch_stock_industry_map/_pe are unguarded
    # at the monitor_cmd call site). Regression for the cached_fetch._read guard.
    (tmp_path / "2026-06-16.json").write_text(
        '{"600519": {"status": "ok", "rows": [{"date": "2026-06-16"}]}}',
        encoding="utf-8",
    )
    out = fetch_flow_series(("600519",), cache_dir=tmp_path, today="2026-06-16",
                            fetch=lambda *, stock, market: _fake_df(7.0), sleep=lambda _: None)
    assert out["600519"] == (("2026-06-16", 7.0),)  # corrupt entry ignored, refetched


def test_fetch_skips_non_a_share_symbols(tmp_path):
    calls: list[str] = []

    def fake_fetch(*, stock, market):
        calls.append(stock)
        return _fake_df(5.0)

    out = fetch_flow_series(("00700",), cache_dir=tmp_path, today="2026-06-16", fetch=fake_fetch)
    assert calls == []          # HK line never fetched
    assert out["00700"] is None  # uncovered
