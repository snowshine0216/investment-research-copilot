from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.data.manifest import read_manifest
from irc.io_utils import atomic_write_text


DEFAULT_MAX_AGE: timedelta = timedelta(hours=24)
"""Default ingest freshness window. Override via the `max_age` kwarg per stage.
Stages that depend on fresh prices/NAV (gold, opportunity, memo) gate on this.
"""

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "y", "t"})


def _allow_stale_env() -> bool:
    return os.environ.get("IRC_ALLOW_STALE", "").strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class IngestFreshness:
    is_fresh: bool
    last_ingest_at: datetime | None
    observed_age: timedelta
    max_age: timedelta
    source: str = "akshare"


def check_ingest_freshness(
    repo_root: Path, *, max_age: timedelta = DEFAULT_MAX_AGE,
    source: str = "akshare",
) -> IngestFreshness:
    """Pure read of the manifest. No I/O beyond reading the manifest file."""
    entry = read_manifest(repo_root / "data", source)
    if entry is None:
        return IngestFreshness(
            is_fresh=False, last_ingest_at=None,
            observed_age=timedelta.max, max_age=max_age, source=source,
        )
    try:
        last = datetime.fromisoformat(entry.last_run_at)
    except ValueError:
        return IngestFreshness(
            is_fresh=False, last_ingest_at=None,
            observed_age=timedelta.max, max_age=max_age, source=source,
        )
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age = now - last
    return IngestFreshness(
        is_fresh=age <= max_age, last_ingest_at=last,
        observed_age=age, max_age=max_age, source=source,
    )


def _format_age(td: timedelta) -> str:
    if td == timedelta.max:
        return "unknown"
    total_seconds = int(td.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def _write_stale_marker(
    repo_root: Path, stage: str, freshness: IngestFreshness,
) -> Path:
    """Write outputs/<date>/STALE_INGEST.md describing the freshness gap."""
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out_dir = repo_root / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    last_str = (
        freshness.last_ingest_at.isoformat()
        if freshness.last_ingest_at is not None else "never"
    )
    body = (
        f"# STALE INGEST — {today}\n\n"
        f"**Stage:** `{stage}`\n\n"
        f"**Source:** `{freshness.source}`\n\n"
        f"**Max age:** {freshness.max_age}\n\n"
        f"**Last ingest at:** {last_str}\n\n"
        f"**Observed age:** {_format_age(freshness.observed_age)}\n\n"
        f"**Remediation:**\n"
        f"Re-run `irc ingest --repo-root .` to refresh prices/NAV. To proceed "
        f"with stale data (artifacts will still be tagged), set "
        f"`IRC_ALLOW_STALE=1` and re-run the stage.\n\n"
        f"**Generated at:** "
        f"{datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "STALE_INGEST.md"
    atomic_write_text(path, body)
    return path


def require_fresh_ingest(
    repo_root: Path, stage: str, *,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> bool:
    """Returns True iff the stage may proceed. Writes STALE_INGEST.md when stale.

    Default behavior: stale ingest blocks the stage (returns False after writing
    the marker). When IRC_ALLOW_STALE is truthy, the stage proceeds but the
    marker is still written for transparency.
    """
    freshness = check_ingest_freshness(repo_root, max_age=max_age)
    if freshness.is_fresh:
        return True
    _write_stale_marker(repo_root, stage, freshness)
    return _allow_stale_env()
