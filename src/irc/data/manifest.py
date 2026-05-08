from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
import re
from pathlib import Path

from irc.io_utils import atomic_write_text

_SAFE_SOURCE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class ManifestEntry:
    source: str
    last_run_at: str  # ISO 8601 with offset
    schema_version: str
    record_counts: dict[str, int] = field(default_factory=dict)
    latest_data_date: str | None = None
    notes: str = ""


def _manifest_path(data_root: Path, source: str) -> Path:
    if not _SAFE_SOURCE_RE.fullmatch(source):
        raise ValueError(f"invalid manifest source: {source}")
    return data_root / "_manifest" / f"{source}.json"


def write_manifest(data_root: Path, entry: ManifestEntry) -> None:
    """Write/overwrite a manifest entry atomically."""
    path = _manifest_path(data_root, entry.source)
    payload = json.dumps(asdict(entry), ensure_ascii=False, indent=2)
    atomic_write_text(path, payload)


def read_manifest(data_root: Path, source: str) -> ManifestEntry | None:
    """Read a manifest entry by source. Returns None if file missing."""
    path = _manifest_path(data_root, source)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ManifestEntry(**raw)
