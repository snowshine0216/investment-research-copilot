from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import irc.monitor.trading_calendar as tc


def _write_cache(root: Path, fetched_on: str, dates: list[str]) -> Path:
    p = root / "data" / "monitor" / "trade_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"fetched_on": fetched_on, "dates": dates}), encoding="utf-8")
    return p


def test_cache_hit_today_does_not_fetch(monkeypatch, tmp_path: Path):
    _write_cache(tmp_path, "2026-06-17", ["2026-02-13", "2026-02-17"])
    calls = []
    monkeypatch.setattr(tc, "fetch_trade_calendar", lambda: calls.append(1) or ())
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert calls == []                       # no network on same-day cache
    assert out == frozenset({_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)})


def test_stale_cache_refetches_and_persists(monkeypatch, tmp_path: Path):
    _write_cache(tmp_path, "2026-06-10", ["2026-02-13"])   # fetched_on < today
    monkeypatch.setattr(
        tc, "fetch_trade_calendar",
        lambda: (_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)),
    )
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out == frozenset({_dt.date(2026, 2, 13), _dt.date(2026, 2, 17)})
    on_disk = json.loads(
        (tmp_path / "data" / "monitor" / "trade_calendar.json").read_text(encoding="utf-8"))
    assert on_disk["fetched_on"] == "2026-06-17"
    assert on_disk["dates"] == ["2026-02-13", "2026-02-17"]   # sorted ISO


def test_missing_cache_fetches_and_persists(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tc, "fetch_trade_calendar", lambda: (_dt.date(2026, 2, 13),))
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out == frozenset({_dt.date(2026, 2, 13)})
    assert (tmp_path / "data" / "monitor" / "trade_calendar.json").exists()


def test_fetch_failure_returns_none(monkeypatch, tmp_path: Path):
    def _boom():
        raise RuntimeError("akshare down")
    monkeypatch.setattr(tc, "fetch_trade_calendar", _boom)
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out is None


def test_corrupt_cache_refetches(monkeypatch, tmp_path: Path):
    p = tmp_path / "data" / "monitor" / "trade_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(tc, "fetch_trade_calendar", lambda: (_dt.date(2026, 2, 13),))
    out = tc.load_trading_days(_dt.date(2026, 6, 17), root=tmp_path)
    assert out == frozenset({_dt.date(2026, 2, 13)})
