"""Forward ledger: pure ledger_row + latest_per_key; EDGE append_ledger.
Roadmap §3.2b (schema) / §3.2d (idempotency). Real append-mode JSONL — a single
line < PIPE_BUF is atomic on POSIX, so concurrent/rerun rows are never lost.
ADR 0017 §"Monitor-eval data contracts": deliberate deviation from temp+replace."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Iterable
from irc.monitor.eval.types import GateDecision
from irc.monitor.types import SignalRecord

_log = logging.getLogger(__name__)


def ledger_row(
    *, run_date: str, fund_id: str, written_at: str, signal: SignalRecord,
    nav_acc: float | None, nav_unit: float, as_of_date: str,
    published_state: str, gate: GateDecision, manifest_versions: dict,
    market_composite: float | None = None, market_bias: str | None = None,
) -> dict:
    """PURE: one forward-ledger row. nav_acc is COALESCE(nav_acc, nav) perf basis.
    market_composite / market_bias are additive optional fields (backcompat: None)."""
    return {
        "run_date": run_date,
        "fund_id": fund_id,
        "written_at": written_at,
        "raw_status": signal.status,
        "raw_bias": signal.bias,
        "raw_composite": signal.composite,
        "signal_confidence": signal.signal_confidence,
        "published_state": published_state,
        "gate_reason": gate.reason,
        "nav_acc": nav_acc,
        "nav_unit": nav_unit,
        "nav_basis": "coalesce(nav_acc,nav)",
        "as_of_date": as_of_date,
        "manifest_versions": manifest_versions,
        "market_composite": market_composite,
        "market_bias": market_bias,
    }


def append_ledger(path: Path, rows: list[dict]) -> None:
    """EDGE: real append (open(path,"a")), one JSON object per line. Failures are
    logged and swallowed — never crash the brief."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("append_ledger failed for %s", path, exc_info=True)


def latest_per_key(rows: Iterable[dict]) -> list[dict]:
    """PURE: dedup by (run_date, fund_id) keeping max written_at (tie → last line)."""
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["run_date"], row["fund_id"])
        cur = best.get(key)
        if cur is None or row.get("written_at", "") >= cur.get("written_at", ""):
            best[key] = row
    return list(best.values())
