"""Integration: production-shaped (行业-names-in-`industry`-slot) store through
record_seen/load_store -> fresh_slice -> resolve_candidates. Locks the name->code
translation at the radar join (item 004, review R-1). The pre-fix path (names fed
as codes) is asserted to yield 0 candidates — the regression guard for R-1."""
from __future__ import annotations

import json
from pathlib import Path

from irc.monitor.industry_map_store import fresh_slice, load_store, record_seen
from irc.rotation._cmd_helpers import resolve_candidates
from irc.rotation.candidates import rank_candidates
from irc.rotation.exposure import build_exposure
from irc.rotation.types import BoardState

TODAY = "2026-07-06"


def _state(code: str, name: str, state: str) -> BoardState:
    return BoardState(board_code=code, board_name=name, state=state, days_in_state=1,
                      composite_pctl=0.85, mom20=1.0, flow5=1.0, turn_delta=0.1,
                      pe_pctl=None, chase_risk=False)


def _write_holdings(root: Path) -> None:
    cache = root / "data" / "narrative_holdings"
    cache.mkdir(parents=True)
    # 600519 + 000858 sit in the 白酒 board (13.0% >= 10%); 00700 is HK, unmapped.
    body = {"holdings": [
        {"symbol": "600519", "name_cn": "贵州茅台", "weight_pct": 8.0, "sw_industry": ""},
        {"symbol": "000858", "name_cn": "五粮液", "weight_pct": 5.0, "sw_industry": ""},
        {"symbol": "00700", "name_cn": "腾讯控股", "weight_pct": 3.0, "sw_industry": ""},
    ]}
    (cache / "F001.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _seed_store(root: Path) -> Path:
    # Production shape: 行业 NAMES in the `industry` slot (NOT "BK1"-in-industry).
    map_path = root / "data" / "monitor" / "stock_industry_map.json"
    map_path.parent.mkdir(parents=True)
    record_seen(map_path, TODAY, {"600519": "白酒", "000858": "白酒"})
    return map_path


def test_resolve_candidates_translates_name_to_board_code(tmp_path):
    _write_holdings(tmp_path)
    _seed_store(tmp_path)
    states = (_state("BK0477", "白酒", "hot"), _state("BK0999", "其他", "quiet"))
    membership = (frozenset(), frozenset(), frozenset({"F001"}))  # held

    candidates, new_ids, diag = resolve_candidates(
        tmp_path, states, membership, today=TODAY)

    assert diag["holdings_cache"] == "ok"
    assert len(candidates) >= 1, "translated join must produce candidates"
    assert all(c.board_code.startswith("BK") for c in candidates)
    top = candidates[0]
    assert top.board_code == "BK0477" and top.fund_id == "F001"
    assert top.held is True
    assert "00700" in diag["unmapped_syms"]  # AC7: HK degrades to diagnostics


def test_prefix_names_as_codes_yield_zero_candidates(tmp_path):
    """Regression guard: feeding the 行业-NAME slice straight to build_exposure (the
    pre-fix behavior) makes every ExposureRow.board_code a name, so the code-keyed
    active filter matches nothing and candidates is empty."""
    _write_holdings(tmp_path)
    map_path = _seed_store(tmp_path)
    states = (_state("BK0477", "白酒", "hot"),)
    name_slice = fresh_slice(load_store(map_path), TODAY)  # values are 行业 NAMES
    assert name_slice == {"600519": "白酒", "000858": "白酒"}

    from irc.rotation._cmd_helpers import _load_holdings_cache
    funds = _load_holdings_cache(tmp_path / "data" / "narrative_holdings")
    rows_pre, _ = build_exposure(funds, name_slice)  # names-as-codes (pre-fix)
    cands_pre, _ = rank_candidates(rows_pre, states, discovered_watchlist=frozenset(),
                                   monitor_set=frozenset(), held=frozenset())
    assert len(cands_pre) == 0
