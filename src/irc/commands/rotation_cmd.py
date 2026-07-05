"""Thin command layer for `irc rotation` (daily) + `irc rotation seed` (§4, D11).

Daily: 1 snapshot call, then all pure cores over CACHED holdings + stock-board
map. The daily run is cache-only in v1: holdings/board-map cache misses are filled
by `irc rotation seed` (IRC_ROTATION_TOPUP_BUDGET bounds seed's stock-board fetch
chunk). The §8/D11 in-run bounded top-up for incremental misses between seeds is a
named follow-up (F6) — a cold cache renders L1 normally and shows the seed-pointer
line (§7), never a full inline fan-out. Advisory-only: exit 0 always, never pages
(§7). Degradation: total failure -> abstain stub; flow leg absent (today's snapshot
OR any board's flow5) -> GLOBAL flow_dark renorm (never a fabricated 0.0 inflow for
some boards while others score real flow — the recurring dark-factor bug class in
this codebase). Zero LLM/paid search -> no spend-gate preflight.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from irc.io_utils import atomic_write_text
from irc.monitor.trading_calendar import load_trading_days
from irc.rotation._cmd_helpers import load_membership, resolve_candidates
from irc.rotation.board_fetch import fetch_board_spot
from irc.rotation.composite import (
    board_signals,
    cross_sectional,
    flow_leg_dark,
    pe_percentiles,
)
from irc.rotation.ledger import append_rows, build_ledger_rows
from irc.rotation.report import (
    RADAR_VERSION,
    SCHEMA_VERSION,
    abstain_report,
    to_json,
    to_md,
)
from irc.rotation.seed import seed_boards, seed_holdings, seed_stock_board_map
from irc.rotation.series_store import append_snapshot
from irc.rotation.states import classify_board
from irc.rotation.types import BoardState, RotationReport

_log = logging.getLogger(__name__)
_KEEP_TD = 60
_SERIES_REL = ("data", "rotation", "board_series.json")
_LEDGER_REL = ("data", "rotation", "forward_ledger.jsonl")
_TOPUP_BUDGET_ENV = "IRC_ROTATION_TOPUP_BUDGET"
_TOPUP_BUDGET_DEFAULT = 50


def _today_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _write_report(out_dir: Path, report: RotationReport) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "rotation_radar.json", to_json(report))
    atomic_write_text(out_dir / "rotation_radar.md", to_md(report))


def _latest_board_pe(series) -> dict[str, float | None]:
    """Pure glue: each eligible board's PE from its LATEST stored day (the
    snapshot day, which carries live f9). Read from the STORE — never a
    re-fetch — so pe_pctl is byte-stable across same-day reruns (AC3)."""
    out: dict[str, float | None] = {}
    for code, rows in series.items():
        latest = sorted(rows, key=lambda r: r.date)[-1] if rows else None
        out[code] = latest.board_pe if latest else None
    return out


def _pctl_series_by_day(series, *, flow_dark: bool) -> dict[str, list[tuple[str, float]]]:
    """Pure glue: recompute the composite-percentile series per historical
    trailing day from the store windows (D5 — no incremental state file)."""
    all_dates = sorted({r.date for rows in series.values() for r in rows})
    pctl_series: dict[str, list[tuple[str, float]]] = {c: [] for c in series}
    for d in all_dates:
        sliced = {c: tuple(r for r in rows if r.date <= d) for c, rows in series.items()}
        comp = cross_sectional(board_signals(sliced), flow_dark=flow_dark)
        for c, p in comp.items():
            pctl_series[c].append((d, p))
    return pctl_series


def _one_state(code, series, sig, latest, pctl_series, pe_pctls, *, flow_dark) -> BoardState:
    state, dis = classify_board(tuple(pctl_series[code]))
    name = next((r.board_name for r in series[code][::-1] if r.board_name), code)
    pe_pctl = pe_pctls.get(code)
    chase = state in ("emerging", "hot") and pe_pctl is not None and pe_pctl > 0.90
    return BoardState(
        board_code=code, board_name=name, state=state, days_in_state=dis,
        composite_pctl=round(latest[code], 4), mom20=round(sig[code]["mom20"], 4),
        flow5=(None if flow_dark else sig[code]["flow5"]),
        turn_delta=round(sig[code]["turn_delta"], 4),
        pe_pctl=(round(pe_pctl, 4) if pe_pctl is not None else None),
        chase_risk=chase)


def _build_states(series, *, flow_dark: bool) -> tuple[tuple[BoardState, ...], dict]:
    """Pure glue: composite -> pctl series -> classify -> wire pe_pctl + chase_risk
    (§6). Returns (states, pe_coverage) — the 'missing PE noted in diagnostics'
    path (§6)."""
    latest = cross_sectional(board_signals(series), flow_dark=flow_dark)
    sig = board_signals(series)
    pe_latest = {c: v for c, v in _latest_board_pe(series).items() if c in latest}
    pe_pctls = pe_percentiles(pe_latest)
    pctl_series = _pctl_series_by_day(series, flow_dark=flow_dark)
    states = tuple(
        _one_state(c, series, sig, latest, pctl_series, pe_pctls, flow_dark=flow_dark)
        for c in sorted(latest))
    pe_coverage = {"with_pe": sum(1 for v in pe_latest.values() if v is not None),
                   "without_pe": sorted(c for c, v in pe_latest.items() if v is None)}
    return states, pe_coverage


def _resolve_trading_days(root: Path, _trading_days=None) -> tuple[str, ...]:
    """Injectable for tests (avoids the trading-calendar cache/network edge);
    default wraps the real cached loader."""
    if _trading_days is not None:
        return tuple(_trading_days)
    tds_set = load_trading_days(date.today(), root=root)
    if tds_set is None:
        _log.warning("rotation: trading calendar unavailable; series-store "
                     "pruning skipped this run (self-heals next run)")
        return ()
    return tuple(d.isoformat() for d in tds_set)


def run_rotation(*, repo_root: str, today: str | None = None, _fetch_spot=None,
                 _trading_days=None) -> int:
    """EDGE orchestrator for `irc rotation` (daily). Exit 0 always (advisory)."""
    root = Path(repo_root)
    _today = today or _today_iso()
    out_dir = root / "outputs" / _today / "rotation"
    fetch_spot = _fetch_spot or fetch_board_spot
    try:
        snapshot = fetch_spot(_today)
    except Exception as exc:  # noqa: BLE001 — abstain (§7, AC5)
        _log.warning("rotation: snapshot failed: %s", exc, exc_info=True)
        _write_report(out_dir, abstain_report(f"snapshot failed: {exc}"))
        return 0
    if not snapshot:
        _write_report(out_dir, abstain_report("snapshot returned no boards"))
        return 0
    tds = _resolve_trading_days(root, _trading_days)
    series = append_snapshot(root.joinpath(*_SERIES_REL), snapshot,
                             keep_td=_KEEP_TD, trading_days=tds)
    # HARD REQUIREMENT 1: decide flow_dark GLOBALLY and flow5-AWARE — a board never
    # scores with real flow while another silently gets a fabricated 0.0. A
    # today's-snapshot-only gate misses the post-seed window (backfill rows carry
    # main_inflow_ratio=None → flow5 None for every board until ~5 snapshot days
    # accumulate); flow_leg_dark closes that dark-factor gap (D6).
    flow_dark = all(b.main_inflow_ratio is None for b in snapshot) or \
        flow_leg_dark(board_signals(series))
    states, pe_coverage = _build_states(series, flow_dark=flow_dark)
    membership = load_membership(root, today=_today)
    candidates, new_ids, cand_diag = resolve_candidates(root, states, membership, today=_today)
    data_status = "degraded_flow_dark" if flow_dark else "ok"
    diagnostics = {
        "immature_boards": sorted(c for c, rows in series.items() if len(rows) < 20),
        "pe_coverage": pe_coverage,
        "new_candidates": len(new_ids),
        **cand_diag,
    }
    report = RotationReport(
        schema_version=SCHEMA_VERSION, radar_version=RADAR_VERSION,
        data_status=data_status, board_states=states, candidates=candidates,
        diagnostics=diagnostics)
    _write_report(out_dir, report)
    append_rows(root.joinpath(*_LEDGER_REL), build_ledger_rows(_today, states, RADAR_VERSION))
    print(f"rotation OK ({data_status}): {len(states)} boards, "
          f"{len(candidates)} candidates -> {out_dir}")
    return 0


def _topup_budget() -> int:
    raw = os.environ.get(_TOPUP_BUDGET_ENV, _TOPUP_BUDGET_DEFAULT)
    try:
        return int(raw)
    except ValueError:
        _log.warning("rotation: %s=%r is not an int; using default %d",
                     _TOPUP_BUDGET_ENV, raw, _TOPUP_BUDGET_DEFAULT)
        return _TOPUP_BUDGET_DEFAULT


def run_rotation_seed(*, repo_root: str) -> int:
    """EDGE orchestrator for `irc rotation seed` (one-time resumable backfill,
    D11/AC2). Always exits 0, even on partial completion (advisory)."""
    from irc.commands.narrative_cmd import _enumerate_cn_funds
    from irc.monitor.flow_batch_fetch import fetch_flow_today_batch
    from irc.monitor.industry_map_store import load_store as load_industry_map, record_seen
    from irc.narrative.holdings_fetch import fetch_top_holdings
    from irc.rotation.board_fetch import fetch_board_spot as _fetch_spot_edge

    root = Path(repo_root)
    today = _today_iso()
    series_path = root.joinpath(*_SERIES_REL)
    tds_set = load_trading_days(date.today(), root=root)
    tds = tuple(d.isoformat() for d in (tds_set or ()))

    boards = _seed_board_list(_fetch_spot_edge, today)
    board_summary = seed_boards(boards, series_path=series_path, keep_td=_KEEP_TD,
                                trading_days=tds)

    funds = _enumerate_cn_funds(root)
    holdings_dir = root / "data" / "narrative_holdings"
    holdings_summary = seed_holdings((f[0] for f in funds), cache_dir=holdings_dir,
                                     fetch=fetch_top_holdings)

    map_path = root / "data" / "monitor" / "stock_industry_map.json"
    symbols = _held_symbols(holdings_dir, funds)
    # §8: bound each top-up call to _topup_budget() symbols (env-overridable,
    # default 50, IRC_ROTATION_TOPUP_BUDGET) — every chunk is one network call.
    map_summary = seed_stock_board_map(
        symbols, map_path=map_path, today=today, batch_fetch=fetch_flow_today_batch,
        load_existing=load_industry_map, record=record_seen,
        chunk_size=_topup_budget())

    print(f"rotation seed: boards={board_summary} holdings={holdings_summary} "
          f"stock_map={map_summary}")
    return 0


def _seed_board_list(fetch_spot, today: str) -> tuple[tuple[str, str], ...]:
    """Best-effort board-code/name universe from today's snapshot (one call);
    an unavailable snapshot degrades to an empty list (nothing to seed today,
    never crashes the seed run)."""
    try:
        snapshot = fetch_spot(today)
    except Exception as exc:  # noqa: BLE001 — seed is partial-tolerant (AC2/T3)
        _log.warning("rotation seed: board-list snapshot failed: %s", exc)
        return ()
    return tuple(dict.fromkeys((b.board_code, b.board_name) for b in snapshot))


def _held_symbols(holdings_dir: Path, funds) -> tuple[str, ...]:
    """Union of top-10 holding symbols already cached for the CN-fund universe
    (best-effort; a missing cache dir yields no symbols for this pass)."""
    import json as _json

    syms: list[str] = []
    for fund_id, _name, _asset in funds:
        path = holdings_dir / f"{fund_id}.json"
        if not path.is_file():
            continue
        try:
            body = _json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        syms.extend(h.get("symbol") for h in body.get("holdings", []) if h.get("symbol"))
    return tuple(dict.fromkeys(syms))
