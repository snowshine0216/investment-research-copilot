from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from irc.io_utils import atomic_write_text


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
