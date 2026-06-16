"""EDGE read: newest StageReport for a stage, China-date max <= today.
There is no 'newest report for a stage' API in locator.py (artifact-set oriented),
so this adds one (roadmap §2.4)."""
from __future__ import annotations
import json
import logging
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from evals._shared.report_schema import MetricReport, StageReport

_log = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=8))
_DATE_LEN = 10


def _today_iso() -> str:
    return datetime.now(_TZ).date().isoformat()


def _is_date_dir(name: str) -> bool:
    if len(name) != _DATE_LEN:
        return False
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _parse_report(path: Path) -> StageReport:
    raw = json.loads(path.read_text(encoding="utf-8"))
    metrics = [MetricReport(**m) for m in raw.get("metrics", [])]
    return StageReport(
        stage=raw["stage"], ran_at=raw["ran_at"], based_on=raw.get("based_on", []),
        metrics=metrics, overall=raw["overall"], notes=raw.get("notes", ""),
        config_versions=raw.get("config_versions", {}),
    )


def latest_stage_report(
    repo_root: Path, stage: str, *, today_iso: str | None = None,
) -> StageReport | None:
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return None
    today = today_iso if today_iso is not None else _today_iso()
    dates = sorted(
        (d.name for d in outputs.iterdir()
         if d.is_dir() and _is_date_dir(d.name) and d.name <= today),
        reverse=True,
    )
    for d in dates:
        report_path = outputs / d / "evals" / stage / "report.json"
        if report_path.is_file():
            try:
                return _parse_report(report_path)
            except Exception:
                _log.warning("corrupt report at %s, skipping", report_path, exc_info=True)
                continue
    return None


StageReportEntry = namedtuple("StageReportEntry", ["artifact_date", "report"])
# artifact_date: str  — YYYY-MM-DD, from the output directory name
# report:        StageReport


def list_stage_reports(
    repo_root: Path, stage: str, *, limit: int | None = None,
    today_iso: str | None = None,
) -> list[StageReportEntry]:
    """All parseable reports for a stage as StageReportEntry, descending by
    artifact_date (dir name), ran_at descending tiebreak within a date. Applies the
    same `dir_name <= today_iso` clamp as latest_stage_report so the trigger's
    K-week window is deterministic. Corrupt report.json skipped + logged."""
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return []
    today = today_iso if today_iso is not None else _today_iso()
    dates = sorted(
        (d.name for d in outputs.iterdir()
         if d.is_dir() and _is_date_dir(d.name) and d.name <= today),
        reverse=True,
    )
    entries: list[StageReportEntry] = []
    for d in dates:
        report_path = outputs / d / "evals" / stage / "report.json"
        if not report_path.is_file():
            continue
        try:
            entries.append(StageReportEntry(d, _parse_report(report_path)))
        except Exception:
            _log.warning("corrupt report at %s, skipping", report_path, exc_info=True)
    entries.sort(key=lambda e: (e.artifact_date, e.report.ran_at), reverse=True)
    return entries[:limit] if limit is not None else entries


def latest_stage_report_entry(
    repo_root: Path, stage: str, *, today_iso: str | None = None,
) -> StageReportEntry | None:
    """Newest StageReportEntry (with artifact_date for the staleness check), or None."""
    out = list_stage_reports(repo_root, stage, limit=1, today_iso=today_iso)
    return out[0] if out else None
