from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from irc.monitor.board_pe_staleness import BoardPeFreshness
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
    out1, f1 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                                 fetch=fake_fetch, sleep=lambda _s: None)
    out2, f2 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                                 fetch=fake_fetch, sleep=lambda _s: None)
    assert out1 == out2 == {"银行": 6.5}
    assert f1 == f2 == BoardPeFreshness("FRESH", "2026-06-21", 0)
    assert calls["n"] == 1  # second call served from cache
    payload = json.loads((cache_dir / "2026-06-21.json").read_text(encoding="utf-8"))
    assert payload == {"银行": 6.5}


def test_fetch_industry_pe_never_raises_returns_empty_dark(tmp_path: Path):
    def boom():
        raise RuntimeError("network down")

    out, f = fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-06-21",
                               fetch=boom, sleep=lambda _s: None)
    assert out == {}
    assert f == BoardPeFreshness("DARK", None, None)   # nothing cached anywhere


def _info_df(industry: str) -> pd.DataFrame:
    return pd.DataFrame({"item": ["行业"], "value": [industry]})


def test_fetch_stock_industry_map_per_symbol_cache_ok_and_miss(tmp_path: Path):
    seen: list[str] = []

    def fake_fetch(symbol):
        seen.append(symbol)
        if symbol == "600519":
            return _info_df("酿酒行业")
        # endpoint answers but has no 行业 row → confirmed DEAD → miss (not a raise)
        return pd.DataFrame({"item": ["总市值"], "value": ["1.2e12"]})

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


def test_unrecognised_cache_status_is_refetched_not_a_frozen_miss(tmp_path: Path):
    # Only ok/miss are ever written; an unrecognised status can arise only from
    # external corruption / a manual edit. Treat it as cache-ABSENT (refetch),
    # never as a confirmed miss that freezes the symbol dark for the day.
    # Line-23 residual fix.
    cache_dir = tmp_path / "si"
    cache_dir.mkdir(parents=True)
    (cache_dir / "2026-06-21.json").write_text(
        '{"600519": {"status": "weird", "industry": null}}', encoding="utf-8")
    seen: list[str] = []

    def fetch(symbol):
        seen.append(symbol)
        return _info_df("酿酒行业")

    out = fetch_stock_industry_map(("600519",), cache_dir=cache_dir, today="2026-06-21",
                                   fetch=fetch, sleep=lambda _s: None)
    assert seen == ["600519"]  # refetched, NOT served from the poisoned entry
    assert out == {"600519": "酿酒行业"}


def test_blank_frame_is_transient_not_dead(tmp_path: Path):
    # A soft-throttle empty-200 (akshare → empty df, OR a frame missing the
    # item/value columns) is NOT the same as a well-formed table that genuinely
    # lacks a 行业 row. The former is throttle-like → TRANSIENT (retried next run),
    # not cached as a confirmed miss that freezes the industry leg for the day.
    # Line-22 residual fix; the content-absence DEAD path is preserved by
    # test_fetch_stock_industry_map_per_symbol_cache_ok_and_miss.
    cache_dir = tmp_path / "si"
    out = fetch_stock_industry_map(("600519",), cache_dir=cache_dir, today="2026-06-21",
                                   fetch=lambda symbol: pd.DataFrame(), sleep=lambda _s: None)
    assert out == {"600519": None}
    assert not (cache_dir / "2026-06-21.json").is_file()  # not poisoned → retries
    # throttle lifts → real industry on the next same-day run
    out2 = fetch_stock_industry_map(("600519",), cache_dir=cache_dir, today="2026-06-21",
                                    fetch=lambda symbol: _info_df("酿酒行业"),
                                    sleep=lambda _s: None)
    assert out2 == {"600519": "酿酒行业"}


def test_fetch_stock_industry_map_transient_not_persisted_and_retried(tmp_path: Path):
    # A raised fetch is TRANSIENT: None to the caller, NOT cached → re-run retries.
    cache_dir = tmp_path / "si"

    def boom(symbol):
        raise RuntimeError("x")

    out = fetch_stock_industry_map(("600519",), cache_dir=cache_dir,
                                   today="2026-06-21", fetch=boom, sleep=lambda _s: None)
    assert out == {"600519": None}
    assert not (cache_dir / "2026-06-21.json").is_file()  # nothing poisoned

    out2 = fetch_stock_industry_map(("600519",), cache_dir=cache_dir, today="2026-06-21",
                                    fetch=lambda symbol: _info_df("酿酒行业"),
                                    sleep=lambda _s: None)
    assert out2 == {"600519": "酿酒行业"}  # retried, recovered


def test_default_fetch_uses_em_raw_board_frame(tmp_path, monkeypatch):
    """Contract-preservation: with NO fetch injected, fetch_industry_pe pulls the
    board frame from em_raw (raw JSON) and the EXISTING parse_industry_pe yields
    the same {name: pe} mapping — no akshare wrapper involved."""
    import irc.monitor.industry_valuation as iv

    monkeypatch.setattr(
        iv, "fetch_board_pe_frame",
        lambda **_kw: pd.DataFrame({"板块名称": ["电力"], "市盈率": [19.68]}))
    out, f = iv.fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-02",
                                  sleep=lambda _s: None)
    assert out == {"电力": 19.68}
    assert f.state == "FRESH"


def test_empty_parse_is_returned_but_not_cached(tmp_path, monkeypatch):
    """D3: {} from an empty parse is returned but NOT written (kills the
    '{} frozen for the day' wart, F4)."""
    import irc.monitor.industry_valuation as iv

    monkeypatch.setattr(iv, "fetch_board_pe_frame", lambda **_kw: pd.DataFrame())
    out, f = iv.fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-02",
                                  sleep=lambda _s: None)
    assert out == {}
    assert f.state == "DARK"
    assert not (tmp_path / "ip" / "2026-07-02.json").is_file()  # NOT cached


_TDS = frozenset({date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)})


def _bank_frame():
    return pd.DataFrame({"板块名称": ["银行"], "市盈率": ["6.5"]})


def test_failed_fetch_serves_stale_cached_table_within_3td(tmp_path: Path):
    """OD-1: the ≤3-td stale table is RETURNED AS THE TABLE — the exact value a
    FRESH day feeds factor math with; only the freshness label differs."""
    cache_dir = tmp_path / "ip"
    fetch_industry_pe(cache_dir=cache_dir, today="2026-07-02",
                      fetch=_bank_frame, sleep=lambda _s: None)   # seed yesterday

    def boom():
        raise RuntimeError("down")

    out, f = fetch_industry_pe(cache_dir=cache_dir, today="2026-07-03",
                               fetch=boom, sleep=lambda _s: None, trading_days=_TDS)
    assert out == {"银行": 6.5}
    assert f == BoardPeFreshness("STALE", "2026-07-02", 1)


def test_fresh_is_calendar_independent(tmp_path: Path):
    """RD-3: a calendar outage (trading_days=None) never darkens a today-fresh
    table — FRESH is an as_of == today string equality."""
    out, f = fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-03",
                               fetch=_bank_frame, sleep=lambda _s: None,
                               trading_days=None)
    assert out == {"银行": 6.5}
    assert f == BoardPeFreshness("FRESH", "2026-07-03", 0)


def test_no_calendar_disables_only_the_stale_branch(tmp_path: Path):
    """Q5: failed fetch + stale cache + NO trading_days → DARK (honest N
    uncomputable), as_of still naming the newest non-empty cached day."""
    cache_dir = tmp_path / "ip"
    fetch_industry_pe(cache_dir=cache_dir, today="2026-07-02",
                      fetch=_bank_frame, sleep=lambda _s: None)

    def boom():
        raise RuntimeError("down")

    out, f = fetch_industry_pe(cache_dir=cache_dir, today="2026-07-03",
                               fetch=boom, sleep=lambda _s: None)
    assert out == {}
    assert f == BoardPeFreshness("DARK", "2026-07-02", None)
