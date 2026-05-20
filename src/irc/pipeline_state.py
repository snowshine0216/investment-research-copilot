from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path
from irc.io_utils import atomic_write_text


STATE_FILENAME = ".pipeline_state.json"


@dataclass(frozen=True)
class PipelineState:
    status: str
    failed_stage: str
    halted_at: str
    reason_kind: str


def write_state(out_dir: Path, state: PipelineState) -> Path:
    """Persist `state` as JSON in `out_dir/.pipeline_state.json` and return the path."""
    path = out_dir / STATE_FILENAME
    atomic_write_text(path, json.dumps(asdict(state), ensure_ascii=False, indent=2))
    return path


def read_state(out_dir: Path) -> PipelineState | None:
    """Return the persisted state, or None if absent / malformed / missing keys."""
    path = out_dir / STATE_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PipelineState(
            status=str(raw["status"]),
            failed_stage=str(raw["failed_stage"]),
            halted_at=str(raw["halted_at"]),
            reason_kind=str(raw["reason_kind"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        # OSError covers PermissionError, IsADirectoryError, and other I/O
        # faults that would otherwise propagate a raw traceback out of the
        # CLI instead of the intended "no resumable state" error message.
        return None


def clear_state(out_dir: Path) -> None:
    """Remove the state file if it exists. Idempotent."""
    (out_dir / STATE_FILENAME).unlink(missing_ok=True)
