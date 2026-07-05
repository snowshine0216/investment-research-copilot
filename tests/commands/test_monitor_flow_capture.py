from __future__ import annotations

import json

import irc.commands.monitor_cmd as mc
from irc.monitor.board_pe_staleness import BoardPeFreshness


def _wire_capture(tmp_path, monkeypatch, *, board_pe=None):
    """Offline capture harness: 2 top-5 symbols, 3 full-basket symbols (AC-3)."""
    monkeypatch.setattr(mc, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(mc, "resolve_funds", lambda cfg: [object()])
    monkeypatch.setattr(mc, "_capture_union_symbols",
                        lambda funds, root: ("600519", "000651"))
    monkeypatch.setattr(mc, "_full_basket_union_symbols",
                        lambda funds, root: ("600519", "000651", "600233"))
    monkeypatch.setattr(
        mc, "fetch_flow_today_batch",
        lambda symbols: ({"600519": 4.0, "000651": 7.0, "600233": 9.0},
                         {"600519": "酿酒行业", "000651": None, "600233": "航天航空"}))
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: frozenset({__import__("datetime").date(2026, 7, 1)}))
    monkeypatch.setattr(
        mc, "fetch_industry_pe",
        board_pe or (lambda **kw: ({}, BoardPeFreshness("DARK", None, None))))


def test_run_flow_capture_appends_completed_day_top5_only(tmp_path, monkeypatch):
    """AC-3: full-basket secids in the ONE batch call, but the flow store is
    sliced back to the top-5 union BEFORE append_today — D5 scope preserved,
    NO non-top-5 symbol ever enters fund_flow_series.json."""
    _wire_capture(tmp_path, monkeypatch)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "fund_flow_series.json").read_text())
    assert store["600519"] == [["2026-07-01", 4.0]]
    assert store["000651"] == [["2026-07-01", 7.0]]
    assert "600233" not in store            # full-basket tail NEVER enters the flow store


def test_capture_merges_batch_industry_into_cross_day_store(tmp_path, monkeypatch):
    """AC-5 (15:45 site): the 行业 map — including the non-top-5 tail — lands in
    stock_industry_map.json; None never merges."""
    _wire_capture(tmp_path, monkeypatch)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    imap = json.loads((tmp_path / "data" / "monitor" / "stock_industry_map.json")
                      .read_text(encoding="utf-8"))
    assert imap["600233"]["industry"] == "航天航空"   # basket tail accumulates
    assert imap["600519"]["industry"] == "酿酒行业"
    assert "000651" not in imap                       # None never merges (RD-4)


def test_capture_board_pe_failure_never_fails_capture(tmp_path, monkeypatch):
    """AC-14: a raising board-PE refresh → rc 0, flow store still written."""
    def _boom(**kw):
        raise RuntimeError("board fetch down")

    _wire_capture(tmp_path, monkeypatch, board_pe=_boom)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "fund_flow_series.json").read_text())
    assert store["600519"] == [["2026-07-01", 4.0]]


def test_capture_board_pe_runs_after_flow_append(tmp_path, monkeypatch):
    """RD-6 load-bearing ordering: board PE fires strictly AFTER the flow row is
    durably written (a watchdog kill loses only the refresh, never the row)."""
    seen = {}

    def _probe(**kw):
        seen["flow_store_exists"] = (
            tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
        seen["cache_dir"], seen["today"] = kw["cache_dir"], kw["today"]
        return {}, BoardPeFreshness("DARK", None, None)

    _wire_capture(tmp_path, monkeypatch, board_pe=_probe)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    assert seen["flow_store_exists"] is True
    assert seen["cache_dir"] == tmp_path / "data" / "monitor" / "industry_pe"
    assert seen["today"] == "2026-07-01"     # capture's own today (P8c)


def test_capture_empty_symbols_early_return(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(mc, "resolve_funds", lambda cfg: [])
    monkeypatch.setattr(mc, "_full_basket_union_symbols", lambda funds, root: ())
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()


def test_capture_batch_failure_degrades_rc0(tmp_path, monkeypatch):
    _wire_capture(tmp_path, monkeypatch)

    def _boom(symbols):
        raise RuntimeError("ulist down")

    monkeypatch.setattr(mc, "fetch_flow_today_batch", _boom)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()


def test_batch_note_never_writes_store(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: ({"600519": 11.78}, {"600519": "酿酒行业"}))
    note, industry = mc._batch_flow_industry(tmp_path, ("600519",))
    assert note == {"600519": 11.78}
    assert industry == {"600519": "酿酒行业"}
    # CRITICAL (D6/trap §8): the 12:15 path must NOT create/modify the FLOW store
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
