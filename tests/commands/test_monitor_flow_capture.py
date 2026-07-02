from __future__ import annotations

import json

import irc.commands.monitor_cmd as mc


def test_run_flow_capture_appends_completed_day(tmp_path, monkeypatch):
    # Two active funds whose top-5 union symbols get one batch call.
    class _F:
        def __init__(self, fid, syms):
            self.id, self._syms = fid, syms

    monkeypatch.setattr(mc, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(mc, "resolve_funds", lambda cfg: [_F("110011", ("600519",))])
    monkeypatch.setattr(mc, "_capture_union_symbols",
                        lambda funds, root: ("600519", "000651"))
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: {"600519": 4.0, "000651": 7.0})
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: frozenset({__import__("datetime").date(2026, 7, 1)}))

    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "fund_flow_series.json").read_text())
    assert store["600519"] == [["2026-07-01", 4.0]]
    assert store["000651"] == [["2026-07-01", 7.0]]


def test_provisional_note_never_writes_store(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: {"600519": 11.78})  # intraday-provisional
    note = mc._provisional_flow_note(tmp_path, ("600519",))
    assert note == {"600519": 11.78}
    # CRITICAL (D6/trap §8): the provisional path must NOT create/modify the store
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
