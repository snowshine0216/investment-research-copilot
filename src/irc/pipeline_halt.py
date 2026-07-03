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


_REMEDIATION_BY_KIND: dict[str, str] = {
    "akshare_unreachable": (
        "Akshare/EastMoney was unreachable during the preflight network "
        "check. Verify outbound connectivity to push2.eastmoney.com and "
        "fund.eastmoney.com (e.g., `curl -I https://push2.eastmoney.com`), "
        "then re-run `irc ingest --repo-root .`."
    ),
    "akshare_empty": (
        "Every akshare fetch attempt failed (see the Diagnostics section "
        "for per-source attempt/success counts and the first error). "
        "Inspect the stage stdout for the per-instrument failure pattern, "
        "then re-run `irc ingest --repo-root .` after the upstream is healthy."
    ),
    "akshare_error": (
        "The akshare preflight call raised a non-network error (likely a "
        "schema change or upstream API change). Re-run with `DEBUG=1 irc "
        "ingest --repo-root .` to capture the full traceback."
    ),
    "missing_required_outputs": (
        "The stage exited with code 0 but the expected output artifact(s) "
        "were not written to `outputs/<today>/`. This usually indicates a "
        "silent failure inside the stage (e.g., an exception swallowed by "
        "a try/except, or a code path that returned 0 without producing "
        "results). Inspect the stage stdout above for warnings, then re-run "
        "`irc <stage> --repo-root .` after fixing. Once the stage produces "
        "its outputs, resume the pipeline with `irc run --resume`."
    ),
    "invalid_env_config": (
        "The stage could not parse `.env` (see First error for the exact "
        "field). Fix the named variable in `.env`, validate with "
        "`irc config validate`, then resume with `irc run --resume`."
    ),
    "db_write_failed": (
        "A DuckDB write failed mid-ingest (see First error). Check free "
        "disk space and whether another irc process holds "
        "`data/local.duckdb` (monitor / fundamentals stock-valuation), "
        "then re-run `irc ingest --repo-root .`."
    ),
}


def _render_stats_table(stats: Mapping[str, int]) -> str:
    if not stats:
        return ""
    lines = ["| Metric | Value |", "|---|---:|"]
    for key, value in stats.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines) + "\n"


def _render_diagnostics(reason: HaltReason) -> str:
    parts = [
        "## Diagnostics\n",
        f"- **kind:** `{reason.kind}`",
        f"- **detail:** {reason.detail}",
    ]
    stats_table = _render_stats_table(reason.stats)
    if stats_table:
        parts.append("\n" + stats_table)
    if reason.first_error:
        safe_error = (reason.first_error or "").replace("```", "'''")
        parts.append("\n**First error:**\n\n```\n" + safe_error + "\n```")
    return "\n".join(parts) + "\n"


def write_halted_structured(
    repo_root: Path, date: str, reason: HaltReason,
) -> Path:
    out_dir = repo_root / "outputs" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    remediation = _REMEDIATION_BY_KIND.get(
        reason.kind,
        f"Inspect the stage output and re-run `irc {reason.stage} "
        f"--repo-root .` after fixing.",
    )
    body = (
        f"# Pipeline Halted — {date}\n\n"
        f"**Stopped at stage:** `{reason.stage}`\n\n"
        f"**Reason:** {reason.kind} — {reason.detail}\n\n"
        f"**Remediation:**\n{remediation}\n\n"
        f"{_render_diagnostics(reason)}\n"
        f"**Generated at:** {datetime.now(timezone(timedelta(hours=8))).isoformat()}\n"
    )
    path = out_dir / "PIPELINE_HALTED.md"
    atomic_write_text(path, body)
    return path

