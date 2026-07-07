"""EDGE helpers for `commands/rotation_cmd.py` — extracted to respect the size
budget. Membership loading + L2 exposure/candidate resolution. Every loader
degrades to an empty/cold result on any failure; the radar must never crash on
a missing/malformed config (§7 advisory posture).
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from irc.rotation.candidates import rank_candidates
from irc.rotation.exposure import build_exposure
from irc.rotation.report import cold_holdings_note
from irc.rotation.types import BoardState

_log = logging.getLogger(__name__)

Membership = tuple[frozenset[str], frozenset[str], frozenset[str]]  # (watchlist, monitor, held)


def _discovered_watchlist(root: Path, today: str) -> frozenset[str]:
    path = root / "outputs" / today / "discovered_watchlist.csv"
    if not path.is_file():
        return frozenset()
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return frozenset(row["instrument_id"] for row in csv.DictReader(fh)
                             if row.get("instrument_id"))
    except (OSError, csv.Error, KeyError):
        _log.warning("rotation: discovered_watchlist.csv unreadable", exc_info=True)
        return frozenset()


def _monitor_set(root: Path) -> frozenset[str]:
    try:
        from irc.config_loader import load_monitor_config
        from irc.monitor.resolve import resolve_funds
        return frozenset(f.id for f in resolve_funds(load_monitor_config(root)))
    except Exception:  # noqa: BLE001 — monitor config absence is not fatal here
        _log.warning("rotation: monitor set unavailable", exc_info=True)
        return frozenset()


def _held_funds(root: Path) -> frozenset[str]:
    try:
        from irc.config_loader import load_yaml
        from irc.schemas.inputs import AccountFile
        account: AccountFile = load_yaml(root / "inputs/account.yaml", root)
        return frozenset(
            h.instrument_id for acct in account.accounts for h in acct.holdings
            if h.instrument_id)
    except Exception:  # noqa: BLE001 — account.yaml absence is not fatal here
        _log.warning("rotation: account holdings unavailable", exc_info=True)
        return frozenset()


def load_membership(root: Path, *, today: str) -> Membership:
    """EDGE: existing-surface membership sets for candidate annotation. Never
    raises — any single source degrades to an empty frozenset."""
    return _discovered_watchlist(root, today), _monitor_set(root), _held_funds(root)


def _load_holdings_cache(cache_dir: Path) -> list[tuple[str, str, tuple, str | None]]:
    """EDGE-read: every cached fund's top-10 holdings as the exposure.Fund shape.
    Skips unreadable files (never crashes); an empty/missing cache dir -> []."""
    from irc.narrative.schemas import Holding

    if not cache_dir.is_dir():
        return []
    funds = []
    for path in sorted(cache_dir.glob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _log.warning("rotation: unreadable holdings cache %s", path, exc_info=True)
            continue
        holdings = tuple(Holding(**h) for h in body.get("holdings", []))
        if holdings:
            funds.append((path.stem, path.stem, holdings, None))
    return funds


def resolve_candidates(root: Path, states: tuple[BoardState, ...], membership: Membership,
                       *, today: str):
    """PURE-glue L2 join: cached holdings x stock->board map -> exposure ->
    ranked candidates. Cold holdings cache (§7) -> no fetch, candidates stay
    empty, diagnostics flags it for the cold_holdings_note() render."""
    from irc.monitor.industry_map_store import fresh_slice, load_store

    cache_dir = root / "data" / "narrative_holdings"
    funds = _load_holdings_cache(cache_dir)
    watchlist, monitor_set, held = membership
    if not funds:
        return (), (), {
            "holdings_cache": "cold", "note": cold_holdings_note(),
            "holdings_coverage_pct": 0.0, "unmapped_syms": (),
        }
    map_path = root / "data" / "monitor" / "stock_industry_map.json"
    stock_to_board = fresh_slice(load_store(map_path), today)
    rows, exp_diag = build_exposure(funds, stock_to_board)
    candidates, new_ids = rank_candidates(
        rows, states, discovered_watchlist=watchlist, monitor_set=monitor_set, held=held)
    diag = {
        "holdings_cache": "ok",
        "holdings_coverage_pct": exp_diag["coverage_pct"],
        "unmapped_syms": exp_diag["unmapped_syms"],
    }
    return candidates, new_ids, diag
