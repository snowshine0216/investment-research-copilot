from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from typing import Mapping
from irc.io_utils import atomic_write_text

_MAX_FIRST_ERROR_CHARS = 500


@dataclass(frozen=True)
class HaltReason:
    kind: str
    stage: str
    detail: str
    stats: Mapping[str, int] = field(default_factory=dict)
    first_error: str | None = None

    def __post_init__(self) -> None:
        if self.first_error is not None and len(self.first_error) > _MAX_FIRST_ERROR_CHARS:
            object.__setattr__(self, "first_error",
                               self.first_error[:_MAX_FIRST_ERROR_CHARS])

    @staticmethod
    def write_sidecar(path: Path, reason: "HaltReason") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(reason)
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    @staticmethod
    def read_sidecar(path: Path) -> "HaltReason | None":
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return HaltReason(
                kind=str(raw["kind"]),
                stage=str(raw["stage"]),
                detail=str(raw["detail"]),
                stats=dict(raw.get("stats") or {}),
                first_error=raw.get("first_error"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None


def write_halted(
    repo_root: Path, date: str, stage: str, reason: str, remediation: str,
) -> Path:
    out_dir = repo_root / "outputs" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    body = (
        f"# Pipeline Halted — {date}\n\n"
        f"**Stopped at stage:** `{stage}`\n\n"
        f"**Reason:** {reason}\n\n"
        f"**Remediation:**\n{remediation}\n\n"
        f"**Generated at:** {datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "PIPELINE_HALTED.md"
    atomic_write_text(path, body)
    return path
