from __future__ import annotations

import json
from pathlib import Path

from irc.commands.rotation_cmd import run_rotation
from irc.rotation.types import BoardDay

# --- deterministic seed helpers -------------------------------------------------

_HIST_TDS = tuple(f"2026-06-{i:02d}" for i in range(1, 26))  # 25 trading days
_TDS = _HIST_TDS + ("2026-07-06",)


def _seed_series(tmp_path: Path, *, hot="BK1", boards=("BK1", "BK2", "BK3")) -> Path:
    """Populate data/rotation/board_series.json with ≥20 td/board so composite and
    states compute; the `hot` board's history stays low/flat relative to its
    peers so today's snapshot spike (see `_snapshot`) pushes its 20-day
    cumulative cross-board-median-relative momentum decisively above the p80
    entry band (fresh cross → emerging, AC4). Historical seed rows carry
    board_pe=None (only the live snapshot carries f9)."""
    from irc.rotation.series_store import append_snapshot

    p = tmp_path / "data" / "rotation" / "board_series.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, d in enumerate(_HIST_TDS):
        for code in boards:
            # hot board flat-low over history then the snapshot spikes it (fresh cross)
            chg = 0.05 if code == hot else (0.3 if code == boards[-1] else 0.15)
            rows.append(BoardDay(d, code, {"BK1": "半导体", "BK2": "白酒",
                                           "BK3": "银行"}.get(code, code),
                                 chg, 1.0, 2.0, None, "backfill"))
    append_snapshot(p, rows, keep_td=60, trading_days=_HIST_TDS)
    return p


def _seed_holdings(tmp_path: Path, *, empty=True) -> Path:
    cache = tmp_path / "data" / "narrative_holdings"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _run(tmp_path, spot, **kw):
    return run_rotation(repo_root=str(tmp_path), today="2026-07-06",
                        _fetch_spot=spot, _trading_days=_TDS, **kw)


def _read_json(tmp_path):
    out = tmp_path / "outputs" / "2026-07-06" / "rotation" / "rotation_radar.json"
    return json.loads(out.read_text(encoding="utf-8")), out


def _snapshot(today):
    # 3 boards; BK1 clearly hot (high chg + flow + rich PE), BK3 mild, BK2 cold.
    return (BoardDay(today, "BK1", "半导体", 15.0, 5.0, 8.0, 95.0, "snapshot"),
            BoardDay(today, "BK2", "白酒", 0.1, 0.0, 1.0, 12.0, "snapshot"),
            BoardDay(today, "BK3", "银行", 2.0, 1.0, 2.0, 8.0, "snapshot"))


# --- AC5: abstain on total snapshot failure ------------------------------------

def test_abstain_on_total_snapshot_failure(tmp_path):
    def boom(today):
        raise RuntimeError("snapshot dead")

    rc = _run(tmp_path, boom)
    js, _ = _read_json(tmp_path)
    assert rc == 0
    assert js["data_status"] == "abstain"
    assert "snapshot dead" in js["diagnostics"]["failure"]
    # AC5: no series mutation on abstain
    assert not (tmp_path / "data" / "rotation" / "board_series.json").exists()
    # AC5: no ledger rows on abstain
    assert not (tmp_path / "data" / "rotation" / "forward_ledger.jsonl").exists()


def test_abstain_on_empty_snapshot(tmp_path):
    rc = _run(tmp_path, lambda today: ())
    js, _ = _read_json(tmp_path)
    assert rc == 0 and js["data_status"] == "abstain"


# --- AC3: same-day rerun byte-identical -----------------------------------------

def test_same_day_rerun_byte_identical(tmp_path):
    _seed_series(tmp_path)
    _seed_holdings(tmp_path)
    rc1 = _run(tmp_path, lambda today: _snapshot(today))
    _, out = _read_json(tmp_path)
    first = out.read_bytes()
    rc2 = _run(tmp_path, lambda today: _snapshot(today))
    assert rc1 == 0 and rc2 == 0
    assert out.read_bytes() == first  # AC3 determinism


# --- HARD REQ 1: global flow_dark -----------------------------------------------

def test_flow_dark_tags_data_status_and_never_fabricates_zero_flow(tmp_path):
    _seed_series(tmp_path)
    _seed_holdings(tmp_path)

    def spot(today):
        # every board's main_inflow_ratio is None → flow leg globally absent
        return (BoardDay(today, "BK1", "半导体", 9.0, None, 8.0, 95.0, "snapshot"),
                BoardDay(today, "BK2", "白酒", 0.1, None, 1.0, 12.0, "snapshot"),
                BoardDay(today, "BK3", "银行", 2.0, None, 2.0, 8.0, "snapshot"))

    seen = {}
    import irc.commands.rotation_cmd as mod
    real_cs = mod.cross_sectional

    def spy_cs(signals, *, flow_dark, turn_dark=False):
        seen.setdefault("flow_dark_values", []).append(flow_dark)
        return real_cs(signals, flow_dark=flow_dark, turn_dark=turn_dark)

    orig = mod.cross_sectional
    mod.cross_sectional = spy_cs
    try:
        _run(tmp_path, spot)
    finally:
        mod.cross_sectional = orig

    js, _ = _read_json(tmp_path)
    assert js["data_status"] == "degraded_flow_dark"
    # Proof 1: cross_sectional was ALWAYS called flow_dark=True — never once False,
    # so no board could be scored with a fabricated 0.0 flow (the `s["flow5"] or 0.0`
    # branch is unreachable this run).
    assert seen["flow_dark_values"], "cross_sectional never called"
    assert all(v is True for v in seen["flow_dark_values"])
    # Proof 2: every scored board reports flow5 == None (flow leg dropped globally),
    # i.e. nobody kept a real flow while nobody else was handed a fake 0.
    assert all(b["flow5"] is None for b in js["board_states"])


def test_flow_present_keeps_ok_status(tmp_path):
    _seed_series(tmp_path)
    _seed_holdings(tmp_path)
    _run(tmp_path, lambda today: _snapshot(today))
    js, _ = _read_json(tmp_path)
    assert js["data_status"] == "ok"
    assert any(b["flow5"] is not None for b in js["board_states"])


def test_partial_flow_gap_triggers_global_flow_dark(tmp_path):
    """Dark-factor guard the today's-snapshot-only gate MISSED: a per-board flow gap
    — one board's trailing-5 flow window all None (backfill-only, e.g. a freshly
    seeded board) while ANOTHER board carries real flow today — must darken the flow
    leg for ALL boards (D6), never fabricate a 0.0 for the gap board. `all(today
    None)` is False here (BK1 has flow), so only the flow5-aware gate catches it."""
    from irc.rotation.series_store import append_snapshot

    p = tmp_path / "data" / "rotation" / "board_series.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in _HIST_TDS:
        rows.append(BoardDay(d, "BK1", "半导体", 0.15, 1.0, 2.0, None, "backfill"))
        rows.append(BoardDay(d, "BK2", "白酒", 0.15, None, 2.0, None, "backfill"))  # flow=None
    append_snapshot(p, rows, keep_td=60, trading_days=_HIST_TDS)
    _seed_holdings(tmp_path)

    def spot(today):  # BK1 has flow today, BK2 still None → all(today None) is False
        return (BoardDay(today, "BK1", "半导体", 9.0, 5.0, 8.0, 40.0, "snapshot"),
                BoardDay(today, "BK2", "白酒", 2.0, None, 2.0, 12.0, "snapshot"))

    _run(tmp_path, spot)
    js, _ = _read_json(tmp_path)
    assert js["data_status"] == "degraded_flow_dark"  # flow5-aware gate fired
    assert all(b["flow5"] is None for b in js["board_states"])  # no fabricated-0 for BK2


# --- turn_leg_dark: board present in series but MISSING from today's snapshot --

def test_turn_dark_when_board_missing_from_snapshot(tmp_path):
    """A board present in the seeded series (BK3) but absent from today's snapshot
    has an all-None recent turnover window (its last real turnover row ages out /
    was never refreshed live) → turn_leg_dark fires, data_status carries
    `turn_dark`, that board's turn_delta is None in the json, and NO board is
    scored with a fabricated turn (proven via the data_status + all-None check,
    mirroring the flow-dark proof pattern)."""
    from irc.rotation.series_store import append_snapshot

    p = tmp_path / "data" / "rotation" / "board_series.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in _HIST_TDS:
        rows.append(BoardDay(d, "BK1", "半导体", 0.15, 1.0, 2.0, None, "backfill"))
        rows.append(BoardDay(d, "BK3", "银行", 0.15, 1.0, None, None, "backfill"))  # turnover=None
    append_snapshot(p, rows, keep_td=60, trading_days=_HIST_TDS)
    _seed_holdings(tmp_path)

    def spot(today):  # BK3 absent from today's snapshot -> stays all-None turnover
        return (BoardDay(today, "BK1", "半导体", 9.0, 5.0, 8.0, 40.0, "snapshot"),)

    rc = _run(tmp_path, spot)
    js, _ = _read_json(tmp_path)
    assert rc == 0
    assert js["data_status"] == "degraded_turn_dark"
    assert "turn" in js["diagnostics"]["dark_legs"]
    assert "flow" not in js["diagnostics"]["dark_legs"]
    # both boards: turn leg dropped globally, nobody scored with a fabricated turn
    assert all(b["turn_delta"] is None for b in js["board_states"]), \
        "turn_delta must be None for every board while the turn leg is dark, " \
        "never fabricated 0.0 for BK1 while BK3 lacks turnover"


def test_flow_only_dark_still_reports_degraded_flow_dark(tmp_path):
    """Regression: the pre-existing flow-only-dark path must keep reporting the
    plain `degraded_flow_dark` status (not the new combined variant) when turn is
    fine."""
    _seed_series(tmp_path)
    _seed_holdings(tmp_path)

    def spot(today):
        return (BoardDay(today, "BK1", "半导体", 9.0, None, 8.0, 95.0, "snapshot"),
                BoardDay(today, "BK2", "白酒", 0.1, None, 1.0, 12.0, "snapshot"),
                BoardDay(today, "BK3", "银行", 2.0, None, 2.0, 8.0, "snapshot"))

    _run(tmp_path, spot)
    js, _ = _read_json(tmp_path)
    assert js["data_status"] == "degraded_flow_dark"
    assert js["diagnostics"]["dark_legs"] == ["flow"]


# --- HARD REQ 2: diagnostics populated end-to-end -------------------------------

def test_normal_run_populates_diagnostics(tmp_path):
    _seed_series(tmp_path)
    _seed_holdings(tmp_path)
    _run(tmp_path, lambda today: _snapshot(today))
    js, out = _read_json(tmp_path)
    diag = js["diagnostics"]
    assert diag  # non-empty
    for key in ("holdings_coverage_pct", "immature_boards", "unmapped_syms",
                "pe_coverage", "new_candidates"):
        assert key in diag, f"missing diagnostics key: {key}"
    assert set(diag["pe_coverage"]) == {"with_pe", "without_pe"}
    # the md renders the diagnostics section (to_md now shows every key)
    md = (out.parent / "rotation_radar.md").read_text(encoding="utf-8")
    assert "诊断" in md


# --- §6: chase_risk fires for rich emerging board, not for PE-less board ---------

def test_chase_risk_and_pe_coverage(tmp_path):
    _seed_series(tmp_path)
    _seed_holdings(tmp_path)

    def spot(today):
        return (BoardDay(today, "BK1", "半导体", 15.0, 5.0, 8.0, 95.0, "snapshot"),
                BoardDay(today, "BK2", "白酒", 0.1, 0.0, 1.0, None, "snapshot"),
                BoardDay(today, "BK3", "银行", 2.0, 1.0, 2.0, 8.0, "snapshot"))

    _run(tmp_path, spot)
    js, _ = _read_json(tmp_path)
    by_code = {b["board_code"]: b for b in js["board_states"]}
    assert by_code["BK1"]["chase_risk"] is True
    assert by_code["BK1"]["pe_pctl"] is not None and by_code["BK1"]["pe_pctl"] > 0.90
    assert by_code["BK2"]["pe_pctl"] is None and by_code["BK2"]["chase_risk"] is False
    assert js["diagnostics"]["pe_coverage"]["with_pe"] >= 2
    assert "BK2" in js["diagnostics"]["pe_coverage"]["without_pe"]


# --- §7: cold holdings cache renders the actionable line, no inline fan-out ------

def test_cold_holdings_renders_note(tmp_path):
    _seed_series(tmp_path)  # NO narrative_holdings dir → cold
    _run(tmp_path, lambda today: _snapshot(today))
    js, out = _read_json(tmp_path)
    assert js["diagnostics"]["holdings_cache"] == "cold"
    assert js["candidates"] == []
    md = (out.parent / "rotation_radar.md").read_text(encoding="utf-8")
    assert "irc rotation seed" in md  # the single actionable line


# --- Task 15: CLI registration --------------------------------------------------

def test_cli_rotation_registered():
    from irc.cli import main

    assert "rotation" in main.commands
    rotation_group = main.commands["rotation"]
    assert "seed" in rotation_group.commands
