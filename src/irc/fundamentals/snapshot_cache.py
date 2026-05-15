"""On-disk JSON cache for ConstituentSnapshot.

Keeps the orchestration logic in snapshot.py thin by separating all I/O
(path resolution, quarter inference, serialize/deserialise) here.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
from typing import Any

from irc.fundamentals.types import (
    BrokerReport,
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
)


def cache_path(lookthrough_target: str, quarter: str, root: Path) -> Path:
    return root / "fundamentals" / quarter / f"{lookthrough_target}.json"


def infer_quarter(as_of_iso: str) -> str:
    """Label a snapshot with the most-recently-reported fiscal quarter.

    Earnings season for Qn ends ~midway through calendar Q(n+1), so the
    snapshot for an as_of date in calendar Qx is tagged Q(x-1).
    """
    try:
        ts = date.fromisoformat(as_of_iso)
    except (TypeError, ValueError):
        ts = date.today()
    cal_q = (ts.month - 1) // 3 + 1
    if cal_q == 1:
        return f"{ts.year - 1}Q4"
    return f"{ts.year}Q{cal_q - 1}"


def _snapshot_to_dict(snap: ConstituentSnapshot) -> dict[str, Any]:
    return {
        "lookthrough_target": snap.lookthrough_target,
        "as_of_iso": snap.as_of_iso,
        "constituents": [asdict(c) for c in snap.constituents],
        "filings": [asdict(f) for f in snap.filings],
        "broker_reports": [asdict(r) for r in snap.broker_reports],
        "failure_reasons": list(snap.failure_reasons),
    }


def _snapshot_from_dict(body: dict[str, Any]) -> ConstituentSnapshot | None:
    needed = {"lookthrough_target", "as_of_iso", "constituents", "filings", "broker_reports"}
    if not needed.issubset(body):
        return None
    try:
        constituents = tuple(Constituent(**c) for c in body["constituents"])
        filings = tuple(FilingDigest(**f) for f in body["filings"])
        broker_reports = tuple(BrokerReport(**r) for r in body["broker_reports"])
    except TypeError:
        return None
    return ConstituentSnapshot(
        lookthrough_target=str(body["lookthrough_target"]),
        as_of_iso=str(body["as_of_iso"]),
        constituents=constituents,
        filings=filings,
        broker_reports=broker_reports,
        failure_reasons=tuple(body.get("failure_reasons", ())),
    )


def write_snapshot(snapshot: ConstituentSnapshot, root: Path) -> Path:
    quarter = infer_quarter(snapshot.as_of_iso)
    path = cache_path(snapshot.lookthrough_target, quarter, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_snapshot_to_dict(snapshot), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_cached_snapshot(
    lookthrough_target: str,
    quarter: str,
    root: Path,
) -> ConstituentSnapshot | None:
    path = cache_path(lookthrough_target, quarter, root)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return _snapshot_from_dict(body)


def load_latest_cached_snapshot(
    lookthrough_target: str,
    root: Path,
) -> ConstituentSnapshot | None:
    """Return the most recent cached snapshot for `lookthrough_target`.

    Scans `root/fundamentals/*/` for quarter directories, sorts lexicographically
    (works for <YYYY>Q<N> format), and tries the most recent first.
    """
    base = root / "fundamentals"
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"*/{lookthrough_target}.json"))
    for path in reversed(candidates):
        quarter = path.parent.name
        loaded = load_cached_snapshot(lookthrough_target, quarter, root)
        if loaded is not None:
            return loaded
    return None
