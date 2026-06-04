from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.stock_valuation_ingestor import (
    ingest_stock_valuation_history,
    is_stock_valuation_stale,
)
from irc.fundamentals.akshare_stock_valuation import fetch_stock_valuation_history
from irc.fundamentals.provider import _read_tushare_token, default_cn_provider
from irc.fundamentals.snapshot import (
    build_snapshot,
    registered_snapshot_targets,
    write_snapshot,
)
from irc.fundamentals.stock_valuation_types import StockValuationHistory
from irc.fundamentals.tushare_stock_valuation import (
    fetch_stock_valuation_history_tushare,
)
from irc.opportunity.types import LookthroughTarget

_log = logging.getLogger(__name__)
_ASHARE_RE = re.compile(r"^\d{6}$")  # 6-digit, no surrounding whitespace (§6.1)


def _expand_targets(targets: tuple[str, ...]) -> tuple[str, ...]:
    stripped = tuple(t.strip() for t in targets if t.strip())
    if not stripped:
        return ()
    expanded: list[str] = []
    for target in stripped:
        if target.lower() == "all":
            expanded.extend(registered_snapshot_targets())
        else:
            expanded.append(target)
    return tuple(dict.fromkeys(expanded))


def run_snapshot_rebuild(
    repo_root: str,
    targets: tuple[str, ...],
    top_n: int = 10,
) -> int:
    """Build and cache constituent snapshots for each target.

    Returns 0 for all completed runs (including those with failure_reasons).
    Returns 2 when no targets are specified.
    """
    expanded_targets = _expand_targets(targets)
    if not expanded_targets:
        print("ERROR: provide at least one --target for snapshot rebuild.")
        return 2

    root = Path(repo_root)
    provider = default_cn_provider()
    for target in expanded_targets:
        lt = LookthroughTarget(
            kind="broad_index", key=target, display_cn=target,
        )
        snapshot = build_snapshot(lt, top_n=top_n, provider=provider)
        path = write_snapshot(snapshot, root / "data")
        if snapshot.failure_reasons:
            joined = "; ".join(snapshot.failure_reasons)
            print(f"WARNING: {target} snapshot has gaps: {joined}")
        print(f"fundamentals snapshot OK: {target} -> {path}")
    return 0


# ── stock-valuation refresh (Phase D PR1) ────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _china_today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _discover_ashare_codes(con) -> tuple[str, ...]:
    """DISTINCT holding_ticker from fund_holdings filtered to A-share shape
    `^\\d{6}$` (no surrounding whitespace), sorted + deduped (§6.1)."""
    rows = con.execute(
        "SELECT DISTINCT holding_ticker FROM fund_holdings"
    ).fetchall()
    codes = {
        r[0] for r in rows
        if r[0] is not None and _ASHARE_RE.fullmatch(r[0])
    }
    return tuple(sorted(codes))


def _fetch_stock_valuation(
    code: str, token: str
) -> tuple[StockValuationHistory, str] | None:
    """EastMoney primary; Tushare on miss. Returns (history, source) or None."""
    hist = fetch_stock_valuation_history(code)
    if hist is not None:
        return hist, "eastmoney"
    ts_hist = fetch_stock_valuation_history_tushare(code, token=token)
    if ts_hist is not None:
        return ts_hist, "tushare"
    return None


def run_stock_valuation_refresh(
    repo_root: str, *, force: bool = False, threshold_days: int = 30
) -> int:
    """Refresh per-stock PE/PB history for every distinct A-share in
    fund_holdings. Per-stock failure-isolating: returns 0 on a completed run
    (even with per-stock misses), non-zero only on a structural error.
    Heavy / own cadence — NOT part of `irc run` (spec §3.7)."""
    root = Path(repo_root)
    db_path = root / "data" / "local.duckdb"
    try:
        con = connect(db_path)
        ensure_schema(con)
    except Exception as exc:  # structural error → non-zero
        print(f"ERROR: cannot open DuckDB at {db_path}: {exc}")
        return 1
    try:
        codes = _discover_ashare_codes(con)
        token = _read_tushare_token()
        today = _china_today()
        now = _now_iso()
        targets = tuple(
            c for c in codes
            if force or is_stock_valuation_stale(
                con, c, today_iso=today, threshold_days=threshold_days
            )
        )
        written = 0
        for code in targets:
            try:
                written += ingest_stock_valuation_history(
                    con, (code,),
                    fetch=lambda c, _t=token: _fetch_stock_valuation(c, _t),
                    now_iso=now,
                )
            except Exception as exc:  # per-stock isolation — never abort the run
                _log.warning(
                    "stock-valuation refresh failed for %s: %s: %s",
                    code, type(exc).__name__, exc,
                )
        print(
            f"stock-valuation refresh OK: {len(targets)}/{len(codes)} A-shares "
            f"considered, {written} rows written."
        )
        return 0
    finally:
        con.close()
