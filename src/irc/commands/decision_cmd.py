from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from irc.decision.report import compose_decision_report, render_decision_markdown
from irc.io_utils import atomic_write_text


_TZ = timezone(timedelta(hours=8))
_REQUIRED_ARTIFACTS = (
    "scoring.json",
    "proposed_allocation.yaml",
    "trade_plan.yaml",
    "memo_traceability.json",
)


def run_decision(repo_root: str) -> int:
    root = Path(repo_root)
    out_dir = _resolve_output_dir(root)
    missing = [name for name in _REQUIRED_ARTIFACTS if not (out_dir / name).exists()]
    if missing:
        print(f"ERROR: missing decision inputs in {out_dir}: {', '.join(missing)}")
        return 2
    scoring = _read_json(out_dir / "scoring.json")
    allocation = _read_yaml(out_dir / "proposed_allocation.yaml")
    trade_plan = _read_yaml(out_dir / "trade_plan.yaml")
    memo_traceability = _read_json(out_dir / "memo_traceability.json")
    report = compose_decision_report(
        date=out_dir.name,
        scoring=scoring,
        allocation=allocation,
        trade_plan=trade_plan,
        memo_traceability=memo_traceability,
        pipeline_halted=(out_dir / "PIPELINE_HALTED.md").exists(),
    )
    atomic_write_text(out_dir / "decision_report.json", json.dumps(report, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "decision_report.md", render_decision_markdown(report))
    print(f"decision {report['overall_status']} -> {out_dir / 'decision_report.md'}")
    return 0


def _resolve_output_dir(root: Path) -> Path:
    today = datetime.now(_TZ).date().isoformat()
    today_dir = root / "outputs" / today
    if today_dir.exists():
        return today_dir
    outputs_dir = root / "outputs"
    candidates = sorted(path for path in outputs_dir.glob("*") if path.is_dir()) if outputs_dir.is_dir() else []
    return candidates[-1] if candidates else today_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
