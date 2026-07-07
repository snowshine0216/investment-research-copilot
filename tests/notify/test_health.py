from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from irc.notify.health import (
    HealthDigest,
    HealthItem,
    health_unknown,
    monitor_health,
    rotation_health,
    weekly_health,
)


def test_digest_empty_has_no_warnings():
    assert HealthDigest().has_warnings is False
    assert HealthDigest().items == ()


def test_digest_has_warnings_true_when_any_warn():
    dg = HealthDigest((HealthItem("a", "info", "x"), HealthItem("b", "warn", "y")))
    assert dg.has_warnings is True


def test_digest_info_only_has_no_warnings():
    dg = HealthDigest((HealthItem("a", "info", "x"),))
    assert dg.has_warnings is False


def test_health_unknown_is_a_single_warn():
    dg = health_unknown()
    assert dg.has_warnings is True
    assert dg.items[0].code == "health_unknown"
    assert "health unknown" in dg.items[0].text


def test_items_are_frozen():
    import dataclasses
    import pytest

    item = HealthItem("a", "info", "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.code = "b"  # type: ignore[misc]


_FIX = Path(__file__).parent / "fixtures" / "health"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


_TODAY = date(2026, 7, 7)


def test_monitor_board_pe_stale_is_info():
    dg = monitor_health(_load("eval_trace.json"), _load("fund_flow_series.json"),
                        today=_TODAY, holidays=frozenset())
    stale = [i for i in dg.items if i.code == "board_pe_stale"]
    assert stale and stale[0].level == "info"
    assert stale[0].text == "板块PE: STALE-1 (07-06)"


def test_monitor_board_pe_dark_is_warn():
    dg = monitor_health(_load("eval_trace_dark.json"), _load("fund_flow_series.json"),
                        today=_TODAY, holidays=frozenset())
    dark = [i for i in dg.items if i.code == "board_pe_dark"]
    assert dark and dark[0].level == "warn"
    assert dark[0].text == "板块PE: DARK ≥4td — 价值陷阱检测不可用"
    assert dg.has_warnings


def test_monitor_flow_symbol_stale_is_warn():
    dg = monitor_health(_load("eval_trace.json"), _load("fund_flow_series.json"),
                        today=_TODAY, holidays=frozenset())
    fs = [i for i in dg.items if i.code == "flow_symbol_stale"]
    assert fs and fs[0].level == "warn"
    assert "滞后>3td" in fs[0].text and "最旧 06-26" in fs[0].text
    assert dg.has_warnings


def test_monitor_flow_run_level_lag_and_coverage():
    # Force a run-level lag + coverage breach: only one symbol, newest 07-02.
    flow = {"000333": [["2026-07-02", 1.0]]}
    dg = monitor_health(_load("eval_trace.json"), flow, today=_TODAY, holidays=frozenset())
    fl = [i for i in dg.items if i.code == "flow_stale"]
    assert fl and fl[0].level == "warn"
    assert fl[0].text == "资金流: 最新 07-02 (滞后 3td), 覆盖 1/1"


def test_monitor_signal_not_ok_is_warn():
    dg = monitor_health(_load("eval_trace_signal.json"), _load("fund_flow_series.json"),
                        today=_TODAY, holidays=frozenset())
    sig = [i for i in dg.items if i.code == "signal_not_ok"]
    assert sig and sig[0].level == "warn"
    assert "009225" in sig[0].text and "非 ok" in sig[0].text


def test_monitor_all_ok_no_signal_warn():
    dg = monitor_health(_load("eval_trace.json"), _load("fund_flow_series.json"),
                        today=_TODAY, holidays=frozenset())
    assert not [i for i in dg.items if i.code == "signal_not_ok"]


def test_monitor_health_total_on_corrupt_flow():
    # A store where every symbol has malformed rows → internal raise → health_unknown.
    dg = monitor_health(_load("eval_trace.json"), {"X": "oops"},
                        today=_TODAY, holidays=frozenset())
    assert dg.items[0].code == "health_unknown"
    assert dg.has_warnings


def test_monitor_flow_coverage_floor_alone():
    # Isolate the coverage-floor half of the run-level OR: newest date across
    # the store equals today's previous trading day (no date lag), but only
    # 5/30 symbols carry that newest date (well under the 80% floor).
    raw = _load("fund_flow_series.json")
    syms = sorted(raw)
    fresh, rest = syms[:5], syms[5:]
    flow = {
        **{s: [r for r in raw[s] if r[0] <= "2026-07-06"] for s in fresh},
        **{s: [r for r in raw[s] if r[0] <= "2026-06-20"] for s in rest},
    }
    dg = monitor_health(_load("eval_trace.json"), flow, today=_TODAY, holidays=frozenset())
    fl = [i for i in dg.items if i.code == "flow_stale"]
    assert fl and fl[0].level == "warn"
    assert fl[0].text == "资金流: 最新 07-06 (滞后 1td), 覆盖 5/30"


def test_monitor_health_total_on_corrupt_trace():
    # A malformed trace (not a dict) must degrade to health_unknown, never raise,
    # even with a fully valid flow_store.
    dg = monitor_health("oops", _load("fund_flow_series.json"),
                        today=_TODAY, holidays=frozenset())
    assert dg.items == (health_unknown().items[0],)
    assert dg.has_warnings


def test_rotation_abstain_warn_with_streak():
    dg = rotation_health(_load("rotation_radar_abstain.json"), ("abstain", "abstain", "ok"))
    ab = [i for i in dg.items if i.code == "rotation_abstain"]
    assert ab and ab[0].level == "warn"
    assert ab[0].text == "轮动雷达: 弃权 (连续第 2 日)"


def test_rotation_abstain_streak_one_when_prior_ok():
    dg = rotation_health(_load("rotation_radar_abstain.json"), ("abstain",))
    ab = [i for i in dg.items if i.code == "rotation_abstain"]
    assert ab[0].text == "轮动雷达: 弃权 (连续第 1 日)"


def test_rotation_ok_no_warn():
    dg = rotation_health(_load("rotation_radar_ok.json"), ("ok", "abstain"))
    assert dg.items == ()
    assert dg.has_warnings is False


def test_rotation_degraded_status_warn():
    # degraded_* never occurs in a real artifact; minimal dict keeps the real key.
    dg = rotation_health({"data_status": "degraded_flow_dark", "board_states": []},
                         ("degraded_flow_dark",))
    dgd = [i for i in dg.items if i.code == "rotation_degraded"]
    assert dgd and dgd[0].text == "轮动雷达: degraded_flow_dark"


def test_flow_capture_coverage_warn_below_floor():
    dg = rotation_health(_load("rotation_radar_ok.json"), ("ok",), flow_capture_cov=(7, 30))
    cov = [i for i in dg.items if i.code == "flow_capture_coverage"]
    assert cov and cov[0].level == "warn" and cov[0].text == "flow-capture: 7/30"


def test_flow_capture_coverage_no_warn_at_floor():
    dg = rotation_health(_load("rotation_radar_ok.json"), ("ok",), flow_capture_cov=(29, 30))
    assert not [i for i in dg.items if i.code == "flow_capture_coverage"]


def test_rotation_total_on_corrupt_radar():
    # A malformed radar (not a dict) must degrade to health_unknown, never raise,
    # even with a well-formed recent_statuses tuple.
    dg = rotation_health("oops", ("ok",))
    assert dg.items == (health_unknown().items[0],)
    assert dg.has_warnings


def test_weekly_dxy_stale_is_warn():
    dg = weekly_health(_load("gold_regime.json"), today=date(2026, 7, 7))
    dxy = [i for i in dg.items if i.code == "macro_driver_stale"]
    assert dxy and dxy[0].level == "warn"
    assert dxy[0].text == "宏观驱动: DXY 滞后 21d (06-16)"


def test_weekly_only_dxy_breaches_7d_threshold():
    # real_yield/vix/inflation/DGS10 are all 07-01/07-02 (<= 6d) → not stale.
    dg = weekly_health(_load("gold_regime.json"), today=date(2026, 7, 7))
    stale = [i.text for i in dg.items if i.code == "macro_driver_stale"]
    assert stale == ["宏观驱动: DXY 滞后 21d (06-16)"]


def test_weekly_drivers_unavailable_is_info():
    dg = weekly_health(_load("gold_regime.json"), today=date(2026, 7, 7))
    un = [i for i in dg.items if i.code == "macro_driver_unavailable"]
    assert un and un[0].level == "info"
    assert un[0].text == "缺失驱动: etf_holdings_gld"


def test_weekly_total_on_garbage():
    dg = weekly_health({"macro_snapshots": [{"date": 123}]}, today=date(2026, 7, 7))
    assert dg.items[0].code == "health_unknown"
