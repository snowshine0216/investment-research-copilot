from __future__ import annotations

import json

from irc.monitor.flow_series_store import (
    append_today, load_store, seed_from_per_symbol, series_slice,
)

_TD = ("2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02")


def test_append_completed_day_then_slice(tmp_path):
    p = tmp_path / "flow_series.json"
    store = append_today(p, "2026-07-01", {"600519": 4.0, "000651": 7.0},
                         keep_td=25, trading_days=_TD)
    assert store["600519"] == (("2026-07-01", 4.0),)
    assert series_slice(store, ("600519", "999999")) == {
        "600519": (("2026-07-01", 4.0),), "999999": None}


def test_append_is_idempotent_same_day(tmp_path):
    p = tmp_path / "flow_series.json"
    append_today(p, "2026-07-01", {"600519": 4.0}, keep_td=25, trading_days=_TD)
    store = append_today(p, "2026-07-01", {"600519": 9.0}, keep_td=25, trading_days=_TD)
    assert store["600519"] == (("2026-07-01", 9.0),)  # overwrite, not duplicate


def test_append_accumulates_across_days_and_prunes(tmp_path):
    p = tmp_path / "flow_series.json"
    append_today(p, "2026-06-29", {"600519": 1.0}, keep_td=2, trading_days=_TD)
    append_today(p, "2026-06-30", {"600519": 2.0}, keep_td=2, trading_days=_TD)
    store = append_today(p, "2026-07-01", {"600519": 3.0}, keep_td=2, trading_days=_TD)
    # keep_td=2 → only the last 2 trading days survive
    assert store["600519"] == (("2026-06-30", 2.0), ("2026-07-01", 3.0))


def test_append_skips_none_values(tmp_path):
    p = tmp_path / "flow_series.json"
    store = append_today(p, "2026-07-01", {"600519": None, "000651": 7.0},
                         keep_td=25, trading_days=_TD)
    assert "600519" not in store        # None → not appended (no fabricated row)
    assert store["000651"] == (("2026-07-01", 7.0),)


def test_load_store_degrades_on_corrupt(tmp_path):
    p = tmp_path / "flow_series.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load_store(p) == {}           # degrade, never crash


def test_write_is_byte_stable_sorted(tmp_path):
    p = tmp_path / "flow_series.json"
    append_today(p, "2026-07-01", {"z": 1.23456, "a": 2.0}, keep_td=25, trading_days=_TD)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert list(payload.keys()) == ["a", "z"]           # sorted keys
    assert payload["z"][0][1] == 1.2346                 # 4dp round


def test_seed_from_per_symbol_merges_ok_series(tmp_path):
    fund_flow = tmp_path / "fund_flow"
    fund_flow.mkdir()
    (fund_flow / "2026-07-01.json").write_text(json.dumps({
        "600519": {"status": "ok", "rows": [{"date": "2026-06-30", "main_net_pct": 2.5},
                                            {"date": "2026-07-01", "main_net_pct": 3.5}]},
        "000001": {"status": "miss", "rows": []},
    }), encoding="utf-8")
    p = tmp_path / "flow_series.json"
    store = seed_from_per_symbol(p, fund_flow, keep_td=25, trading_days=_TD)
    assert store["600519"] == (("2026-06-30", 2.5), ("2026-07-01", 3.5))
    assert "000001" not in store          # miss series not seeded
