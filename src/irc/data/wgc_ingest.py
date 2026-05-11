from __future__ import annotations
from pathlib import Path
import csv
from datetime import date


def cb_purchases_yearly_tons(csv_path: Path, as_of_year: int) -> float:
    if not csv_path.exists():
        return 0.0
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["year"]) == as_of_year:
                return float(row["tons"])
    return 0.0


def etf_holdings_30d_change_tons(csv_path: Path, as_of: str) -> float:
    if not csv_path.exists():
        return 0.0
    target = date.fromisoformat(as_of)
    rows: list[tuple[date, float]] = []
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((date.fromisoformat(row["date"]), float(row["total_tons"])))
    rows.sort(key=lambda r: r[0])
    cur = next((t for d, t in reversed(rows) if d <= target), None)
    if cur is None:
        return 0.0
    horizon = target.toordinal() - 30
    prior = next((t for d, t in reversed(rows) if d.toordinal() <= horizon), None)
    if prior is None:
        return 0.0
    return cur - prior
