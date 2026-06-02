"""On-disk JSON cache for ConstituentSnapshot and ActiveFundSnapshot.

Keeps the orchestration logic in snapshot.py thin by separating all I/O
(path resolution, quarter inference, serialize/deserialise) here.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
from typing import Any

from irc.fundamentals.types import (
    ActiveFundSnapshot,
    BrokerReport,
    Constituent,
    ConstituentAnalysis,
    ConstituentSnapshot,
    FilingDigest,
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
    ThesisEvidence,
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


# ── Item 003: Active-fund cache I/O ──────────────────────────────────────────


def active_fund_cache_path(fund_id: str, quarter: str, root: Path) -> Path:
    return root / "fundamentals" / quarter / "active_fund" / f"fund_{fund_id}.json"


def _evidence_to_dict(e: ThesisEvidence) -> dict[str, Any]:
    return {
        "type": e.type, "source": e.source, "url": e.url, "date": e.date,
        "summary": e.summary, "scope": e.scope, "citation_kind": e.citation_kind,
        "owner_instrument_id": e.owner_instrument_id,
        "parent_fund_id": e.parent_fund_id,
        "constituent_key": e.constituent_key,
        "citation_id": e.citation_id,
        "holding_weight_pct": e.holding_weight_pct,
    }


def _evidence_from_dict(d: dict[str, Any]) -> ThesisEvidence:
    """Deprecated shim — delegates to ThesisEvidence.from_dict. New code should
    call the classmethod directly."""
    return ThesisEvidence.from_dict(d)


def _constituent_to_dict(c: ConstituentAnalysis) -> dict[str, Any]:
    return {
        "symbol": c.symbol, "name_cn": c.name_cn, "weight_pct": c.weight_pct,
        "evidence": [_evidence_to_dict(e) for e in c.evidence],
        "failure_reasons": list(c.failure_reasons),
        "one_line_view": c.one_line_view,
    }


def _constituent_from_dict(d: dict[str, Any]) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=d["symbol"], name_cn=d["name_cn"], weight_pct=float(d["weight_pct"]),
        evidence=tuple(_evidence_from_dict(e) for e in d.get("evidence", [])),
        failure_reasons=tuple(d.get("failure_reasons", ())),
        one_line_view=d.get("one_line_view", ""),
    )


def _active_fund_to_dict(snap: ActiveFundSnapshot) -> dict[str, Any]:
    return {
        "fund_id": snap.fund_id,
        "source_report_date": snap.source_report_date,
        "source_report_quarter": snap.source_report_quarter,
        "cache_probed_at": snap.cache_probed_at,
        "constituent_analyses": [
            _constituent_to_dict(c) for c in snap.constituent_analyses
        ],
        "failure_reasons_by_symbol": {
            k: list(v) for k, v in snap.failure_reasons_by_symbol.items()
        },
        "fund_level_failure_reasons": list(snap.fund_level_failure_reasons),
        # Item 001 (ADR 0003 §7): row-level NAV+announcement evidence consumed
        # by Policy B rule 2.5. Older cache files lacking this key re-hydrate
        # with `()`; the next freshness probe fires a fresh fetch.
        "fund_level_evidence": [
            _evidence_to_dict(e) for e in snap.fund_level_evidence
        ],
    }


def _active_fund_from_dict(body: dict[str, Any]) -> ActiveFundSnapshot | None:
    needed = {"fund_id", "source_report_quarter", "constituent_analyses"}
    if not needed.issubset(body):
        return None
    try:
        analyses = tuple(
            _constituent_from_dict(c) for c in body["constituent_analyses"]
        )
        fund_level_evidence = tuple(
            _evidence_from_dict(e) for e in body.get("fund_level_evidence", [])
        )
    except (KeyError, TypeError, ValueError):
        return None
    return ActiveFundSnapshot(
        fund_id=str(body["fund_id"]),
        source_report_date=str(body.get("source_report_date", "")),
        source_report_quarter=str(body["source_report_quarter"]),
        cache_probed_at=str(body.get("cache_probed_at", "")),
        constituent_analyses=analyses,
        failure_reasons_by_symbol={
            k: tuple(v) for k, v in body.get("failure_reasons_by_symbol", {}).items()
        },
        fund_level_failure_reasons=tuple(body.get("fund_level_failure_reasons", ())),
        fund_level_evidence=fund_level_evidence,
    )


def write_active_fund_cache(snap: ActiveFundSnapshot, root: Path) -> Path:
    path = active_fund_cache_path(snap.fund_id, snap.source_report_quarter, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # P1-g: PID-qualified tmp suffix to avoid collisions between concurrent writers.
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(_active_fund_to_dict(snap), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_active_fund_cache(
    fund_id: str, quarter: str, root: Path,
) -> ActiveFundSnapshot | None:
    path = active_fund_cache_path(fund_id, quarter, root)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return _active_fund_from_dict(body)


# ── Item 005: NAV cache I/O ───────────────────────────────────────────────────


def nav_cache_path(fund_id: str, quarter: str, root: Path) -> Path:
    return root / "fundamentals" / quarter / "nav" / f"fund_{fund_id}.json"


def _nav_report_to_dict(r: FundNavReport) -> dict[str, Any]:
    return {
        "fund_id": r.fund_id,
        "fund_name": r.fund_name,
        "latest_nav": r.latest_nav,
        "latest_nav_date": r.latest_nav_date,
        "nav_history": [list(t) for t in r.nav_history],
        "source_report_quarter": r.source_report_quarter,
    }


def _nav_report_from_dict(d: dict[str, Any]) -> FundNavReport:
    return FundNavReport(
        fund_id=str(d["fund_id"]),
        fund_name=str(d.get("fund_name", "")),
        latest_nav=float(d["latest_nav"]),
        latest_nav_date=str(d["latest_nav_date"]),
        nav_history=tuple(
            (str(item[0]), float(item[1]))
            for item in d.get("nav_history", [])
        ),
        source_report_quarter=str(d["source_report_quarter"]),
    )


def _ann_to_dict(a: FundAnnouncement) -> dict[str, Any]:
    return {
        "fund_id": a.fund_id,
        "title": a.title,
        "topic": a.topic,
        "date": a.date,
        "report_id": a.report_id,
    }


def _ann_from_dict(d: dict[str, Any]) -> FundAnnouncement:
    return FundAnnouncement(
        fund_id=str(d["fund_id"]),
        title=str(d["title"]),
        topic=str(d["topic"]),  # type: ignore[arg-type]
        date=str(d["date"]),
        report_id=str(d["report_id"]),
    )


def _fund_level_to_dict(snap: FundLevelSnapshot) -> dict[str, Any]:
    return {
        "fund_id": snap.fund_id,
        "nav_report": (
            _nav_report_to_dict(snap.nav_report)
            if snap.nav_report is not None else None
        ),
        "announcements": [_ann_to_dict(a) for a in snap.announcements],
        "evidence": [_evidence_to_dict(e) for e in snap.evidence],
        "source_report_quarter": snap.source_report_quarter,
        "cache_probed_at": snap.cache_probed_at,
        "fund_level_failure_reasons": list(snap.fund_level_failure_reasons),
        "evidence_gaps": list(snap.evidence_gaps),
    }


def _fund_level_from_dict(body: dict[str, Any]) -> FundLevelSnapshot | None:
    needed = {"fund_id", "source_report_quarter", "evidence"}
    if not needed.issubset(body):
        return None
    try:
        nav_report = (
            _nav_report_from_dict(body["nav_report"])
            if body.get("nav_report") is not None else None
        )
        announcements = tuple(
            _ann_from_dict(a) for a in body.get("announcements", [])
        )
        evidence = tuple(
            _evidence_from_dict(e) for e in body.get("evidence", [])
        )
    except (KeyError, TypeError, ValueError):
        return None
    return FundLevelSnapshot(
        fund_id=str(body["fund_id"]),
        nav_report=nav_report,
        announcements=announcements,
        evidence=evidence,
        source_report_quarter=str(body["source_report_quarter"]),
        cache_probed_at=str(body.get("cache_probed_at", "")),
        fund_level_failure_reasons=tuple(
            body.get("fund_level_failure_reasons", ())
        ),
        evidence_gaps=tuple(body.get("evidence_gaps", ())),
    )


def write_nav_cache(snap: FundLevelSnapshot, root: Path) -> Path:
    """Atomic write of `FundLevelSnapshot` to NAV cache. Skips QDII sentinel
    (grill Q5: gap-only rows have nothing to cache)."""
    # Sentinel detection: QDII rows have this gap and nothing fetched.
    if "qdii_information_unavailable" in snap.evidence_gaps:
        return root / "fundamentals" / "qdii_sentinel_skipped.placeholder"
    path = nav_cache_path(snap.fund_id, snap.source_report_quarter, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(_fund_level_to_dict(snap), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_nav_cache(
    fund_id: str, quarter: str, root: Path,
) -> FundLevelSnapshot | None:
    path = nav_cache_path(fund_id, quarter, root)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    return _fund_level_from_dict(body)


def load_latest_nav_cached(
    fund_id: str, root: Path,
) -> FundLevelSnapshot | None:
    """Scan `root/fundamentals/*/nav/fund_{fund_id}.json`; return most-recent quarter."""
    base = root / "fundamentals"
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"*/nav/fund_{fund_id}.json"))
    for path in reversed(candidates):
        quarter = path.parent.parent.name
        loaded = load_nav_cache(fund_id, quarter, root)
        if loaded is not None:
            return loaded
    return None
