# tests/monitor/eval/test_backtest.py
from __future__ import annotations
from datetime import date, timedelta
from irc.monitor.eval.backtest import replay_points, run_backtest
from irc.monitor.types import MonitorFund


def _fund():
    return MonitorFund(
        id="000001", name_cn="x", market="CN", analysis_profile="gold",
        themes=(), constituent_news=False,
        weights={"trend": 1.0}, bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.0,
    )


def _rising_series(n, start="2024-01-01"):
    d0 = date.fromisoformat(start)
    return tuple(((d0 + timedelta(days=i)).isoformat(), 1.0 + 0.001 * i) for i in range(n))


def _flat_series(n, start="2024-01-01"):
    d0 = date.fromisoformat(start)
    return tuple(((d0 + timedelta(days=i)).isoformat(), 1.0) for i in range(n))


def test_replay_points_excluded_below_minimum_observations():
    # window just below minimum_observations → compute_signal returns composite==0.0
    # / insufficient_evidence (trend N/A) → NOT a replay point.
    series = _rising_series(260)
    pts = replay_points(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    # earliest eligible as_of_idx is 250 (251 obs in series[:251]); below that excluded
    assert all(p.as_of_idx >= 250 for p in pts)


def test_replay_truncated_input_window_never_sees_future():
    # look-ahead guard: appending future NAVs after a replay point leaves every
    # replayed composite byte-identical (trend leg never reads past the cutoff).
    base = _rising_series(290)
    pts_short = run_backtest(_fund(), base[:280], minimum_observations=251, h=20,
                             today="2099-01-01")
    pts_long = run_backtest(_fund(), base, minimum_observations=251, h=20,
                            today="2099-01-01")
    assert pts_long.points   # guard: the look-ahead check is vacuous if grid is empty
    short_by_idx = {p.as_of_idx: p.composite for p in pts_short.points}
    for p in pts_long.points:
        if p.as_of_idx in short_by_idx:
            assert p.composite == short_by_idx[p.as_of_idx]   # byte-identical


def test_retro_never_emits_a_bias():
    series = _rising_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    assert all(not hasattr(p, "bias") or getattr(p, "bias", None) is None
               for p in out.points)


def test_entry_strictly_after_as_of_date():
    series = _rising_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    for p in out.points:
        assert p.entry_nav_date > p.as_of_date   # strict >


def test_retro_scores_composite_despite_insufficient_status():
    # spec §3: trend-only ALWAYS yields status=="insufficient_evidence" (1 family <
    # the 2-family gate) yet retro scores the continuous NON-ZERO composite REGARDLESS
    # of status. Above the floor the grid MUST be non-empty — excluding on status
    # would make retro permanently empty (a dead feature).
    series = _rising_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    assert out.points, "above-floor points must be scored, not excluded on status"
    assert all(p.status == "insufficient_evidence" for p in out.points)
    assert all(p.composite != 0.0 for p in out.points)
    assert "insufficient_evidence" not in out.excluded   # status is NOT an exclusion reason


def test_degenerate_zero_composite_excluded_from_grid():
    # §2.3: a constant-0 composite (a flat series → trend ~0) would feed the IC a
    # constant-0 signal (Spearman None) → excluded from the grid under a
    # composite-based reason, never emitted as a replay point.
    series = _flat_series(300)
    out = run_backtest(_fund(), series, minimum_observations=251, h=20, today="2099-01-01")
    assert all(p.composite != 0.0 for p in out.points)
    assert out.excluded.get("degenerate_zero_composite", 0) > 0
