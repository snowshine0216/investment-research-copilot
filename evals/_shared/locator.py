"""Shared artifact locator for dated runner outputs.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/003-spec.md

Strategy:
1. Prefer ``outputs/<today>/`` when every required filename is present.
2. Otherwise pick the latest ``outputs/<YYYY-MM-DD>/`` whose contents satisfy
   the full contract.
3. Return ``None`` only when no dated directory satisfies the contract.

The ``today_iso`` parameter is the only "today" knob — runners and tests can
inject a fixed date. The default delegates to ``_today_iso()`` which returns
the current Asia/Shanghai date (the project's reporting timezone).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


_TZ = timezone(timedelta(hours=8))  # Asia/Shanghai — project convention
_DATE_LEN = 10  # YYYY-MM-DD


@dataclass(frozen=True)
class LocatedArtifacts:
    paths: tuple[Path, ...]
    artifact_date: str


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


def _all_present(date_dir: Path, required_filenames: Iterable[str]) -> bool:
    return all((date_dir / fn).is_file() for fn in required_filenames)


def _build(
    date_dir: Path,
    date_iso: str,
    required_filenames: tuple[str, ...],
) -> LocatedArtifacts:
    return LocatedArtifacts(
        paths=tuple(date_dir / fn for fn in required_filenames),
        artifact_date=date_iso,
    )


def locate(
    repo_root: Path,
    required_filenames: tuple[str, ...],
    *,
    today_iso: str | None = None,
) -> LocatedArtifacts | None:
    """Find the dated artifact set satisfying ``required_filenames``."""
    if not required_filenames:
        raise ValueError("locate() requires at least one filename")
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return None
    today = today_iso if today_iso is not None else _today_iso()
    today_dir = outputs / today
    if today_dir.is_dir() and _all_present(today_dir, required_filenames):
        return _build(today_dir, today, required_filenames)
    candidates = sorted(
        (d for d in outputs.iterdir() if d.is_dir() and _is_date_dir(d.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    for d in candidates:
        if _all_present(d, required_filenames):
            return _build(d, d.name, required_filenames)
    return None
