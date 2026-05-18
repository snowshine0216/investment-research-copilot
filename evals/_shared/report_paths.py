"""Shared report-path helpers.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/004-spec.md

`write_report` writes ``outputs/<artifact_date>/evals/<stage>/report.json``.
For dated stages the caller passes the artifact date returned by the
locator; for mutable non-dated sources (data, research) the caller passes
today's date. There is one path-building site, not per-runner duplicates.
"""
from __future__ import annotations

import json
from pathlib import Path

from evals._shared.report_schema import StageReport, report_to_dict
from irc.io_utils import atomic_write_text


def report_dir(repo_root: Path, stage: str, artifact_date: str) -> Path:
    return repo_root / "outputs" / artifact_date / "evals" / stage


def write_report(
    repo_root: Path,
    report: StageReport,
    *,
    artifact_date: str,
) -> Path:
    out_dir = report_dir(repo_root, report.stage, artifact_date)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "report.json"
    atomic_write_text(out, json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    return out
