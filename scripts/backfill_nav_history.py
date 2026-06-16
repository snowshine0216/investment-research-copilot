"""ONE-TIME migration: seed data/monitor/nav_history.jsonl from the latest
outputs/<date>/monitor/eval_trace.json nav.acc_series. NEVER part of the eval
runner (the eval surface must not mutate data/). Idempotent under the reader's
dedup. Run once after deploying M3, before the first `irc eval monitor_forward`.

Usage: uv run python -m scripts.backfill_nav_history [REPO_ROOT]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from irc.monitor.eval.nav_history import NavHistoryRow, append_nav_history

_TZ = timezone(timedelta(hours=8))
_HUGE_WINDOW = 100_000   # keep the FULL seeded series — never trim historical depth


def backfill_rows_from_trace(
    trace: dict, *, source_run_date: str, written_at: str,
) -> list[NavHistoryRow]:
    rows: list[NavHistoryRow] = []
    for fund_id, entry in trace.get("funds", {}).items():
        for nav_date, nav_acc in entry.get("nav", {}).get("acc_series", []):
            if nav_acc is None:
                continue
            rows.append(NavHistoryRow(
                fund_id=fund_id, nav_date=str(nav_date), nav_acc=float(nav_acc),
                written_at=written_at, source_run_date=source_run_date,
            ))
    return rows


def _latest_trace(repo_root: Path) -> Path | None:
    cands = sorted(repo_root.glob("outputs/*/monitor/eval_trace.json"), reverse=True)
    return cands[0] if cands else None


def run_backfill(repo_root: Path) -> int:
    trace_path = _latest_trace(repo_root)
    if trace_path is None:
        print("backfill: no eval_trace.json found under outputs/*/monitor/")
        return 1
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        run_date = trace.get("run_date") or trace_path.parent.parent.name
        written_at = datetime.now(_TZ).isoformat()
        rows = backfill_rows_from_trace(trace, source_run_date=run_date, written_at=written_at)
        append_nav_history(repo_root / "data" / "monitor" / "nav_history.jsonl", rows)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"backfill: failed to process {trace_path}: {exc}")
        return 1
    print(f"backfill: seeded {len(rows)} nav_history rows from {trace_path}")
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    raise SystemExit(run_backfill(root))
