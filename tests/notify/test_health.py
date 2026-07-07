from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from irc.notify.health import (
    HealthDigest,
    detect_rotation_recovery,
    monitor_health,
    rotation_health,
    weekly_health,
)

_FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


# 2026-07-07 trading-day tuple (Wed..Tue, weekend gap 07-04/05).
_TDAYS = (date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3),
          date(2026, 7, 6), date(2026, 7, 7))


def test_monitor_health_stale_board_pe_is_info():
    trace = _load("eval_trace_monitor.json")
    digest = monitor_health(trace, {}, _TDAYS)
    board = [i for i in digest.items if i.code == "board_pe_stale"]
    assert board and board[0].level == "info"
    assert "STALE-1" in board[0].text and "2026-07-06" in board[0].text


def test_monitor_health_dark_board_pe_is_warn():
    trace = _load("eval_trace_monitor.json")
    trace = {**trace, "board_pe_freshness": {"state": "DARK", "as_of": "2026-07-01", "age_td": 4}}
    digest = monitor_health(trace, {}, _TDAYS)
    dark = [i for i in digest.items if i.code == "board_pe_dark"]
    assert dark and dark[0].level == "warn"
    assert digest.has_warnings is True


def test_monitor_health_per_symbol_stale_is_warn():
    trace = _load("eval_trace_monitor.json")
    flow = _load("fund_flow_series.json")  # real: 688072 @ 2026-06-26 (>3 td)
    digest = monitor_health(trace, flow, _TDAYS)
    stale = [i for i in digest.items if i.code == "flow_symbol_stale"]
    assert stale and stale[0].level == "warn"
    assert "滞后>3td" in stale[0].text and "2026-06-26" in stale[0].text
    assert digest.has_warnings is True


def test_monitor_health_run_level_lag_is_warn():
    trace = _load("eval_trace_monitor.json")
    # All symbols one week stale but uniform → run-level lag, no per-symbol split.
    flow = {"600000": [["2026-06-20", 1.0]], "600036": [["2026-06-20", 2.0]]}
    digest = monitor_health(trace, flow, _TDAYS)
    lag = [i for i in digest.items if i.code == "flow_stale"]
    assert lag and lag[0].level == "warn"


def test_monitor_health_signal_not_ok_is_warn():
    trace = _load("eval_trace_monitor.json")
    funds = {**trace["funds"]}
    fid = next(iter(funds))
    funds[fid] = {"signal": {"status": "gated"}, "published_state": "NO_CALL"}
    trace = {**trace, "funds": funds}
    digest = monitor_health(trace, {}, _TDAYS)
    sig = [i for i in digest.items if i.code == "signal_not_ok"]
    assert sig and sig[0].level == "warn" and fid in sig[0].text


def test_monitor_health_empty_trace_is_health_unknown():
    digest = monitor_health({}, {}, _TDAYS)
    assert digest.items and digest.items[0].code == "health_unknown"
    assert digest.has_warnings is True


def test_monitor_health_clean_when_fresh_and_covered():
    trace = _load("eval_trace_monitor.json")
    trace = {**trace, "board_pe_freshness": {"state": "FRESH", "as_of": "2026-07-07", "age_td": 0}}
    flow = {"600000": [["2026-07-07", 1.0]], "600036": [["2026-07-07", 2.0]]}
    digest = monitor_health(trace, flow, _TDAYS)
    assert digest == HealthDigest(())


def test_rotation_health_abstain_counts_consecutive():
    radar = _load("rotation_radar_abstain.json")  # data_status == "abstain"
    digest = rotation_health(radar, ("ok", "abstain", "abstain"))
    item = digest.items[0]
    assert item.code == "rotation_abstain" and item.level == "warn"
    assert "连续第 2 日" in item.text
    assert digest.has_warnings is True


def test_rotation_health_degraded_prefix_is_warn():
    digest = rotation_health({"data_status": "degraded_flow_dark"}, ("degraded_flow_dark",))
    assert digest.items[0].code == "rotation_degraded"
    assert "degraded_flow_dark" in digest.items[0].text


def test_rotation_health_ok_is_empty():
    radar = _load("rotation_radar_ok.json")  # data_status == "ok"
    assert rotation_health(radar, ("abstain", "ok")) == HealthDigest(())


def test_rotation_health_missing_status_is_unknown():
    digest = rotation_health({}, ())
    assert digest.items[0].code == "health_unknown"


def test_detect_recovery_on_abstain_to_ok():
    radar = _load("rotation_radar_ok.json")
    board_count = len(radar["board_states"])
    text = detect_rotation_recovery(("abstain", "ok"), board_count)
    assert text is not None
    assert f"{board_count} boards" in text and "此前弃权 1 日" in text


def test_detect_recovery_none_when_no_prior_degradation():
    assert detect_rotation_recovery(("ok", "ok"), 200) is None


def test_detect_recovery_none_when_today_not_ok():
    assert detect_rotation_recovery(("abstain", "abstain"), 200) is None


def test_weekly_health_flags_stale_macro_driver():
    gold = _load("gold_regime.json")  # DXY @ 2026-06-16
    digest = weekly_health(gold, date(2026, 7, 7))
    dxy = [i for i in digest.items if i.code == "macro_driver_stale" and "DXY" in i.text]
    assert dxy and dxy[0].level == "warn"
    assert "滞后 21d" in dxy[0].text


def test_weekly_health_relays_unavailable_as_info():
    gold = _load("gold_regime.json")  # drivers_unavailable == ["etf_holdings_gld"]
    digest = weekly_health(gold, date(2026, 7, 7))
    unavail = [i for i in digest.items if i.code == "driver_unavailable"]
    assert unavail and unavail[0].level == "info"
    assert "etf_holdings_gld" in unavail[0].text


def test_weekly_health_empty_is_unknown():
    assert weekly_health({}, date(2026, 7, 7)).items[0].code == "health_unknown"
