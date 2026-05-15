from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from irc.io_utils import atomic_write_text
from irc.research.theme_research import ThemeReport


def format_report_markdown(report: ThemeReport) -> str:
    if report.failure_reason:
        return f"# {report.theme}\n\n_research failed: {report.failure_reason}_\n"
    cit_lines = "\n".join(
        f"[{c.index}] {c.title} — {c.url}" for c in report.citations
    )
    return f"# {report.theme}\n\n{report.report_md}\n\n## Citations\n{cit_lines}\n"


def status_for_reports(reports: list[ThemeReport]) -> dict[str, Any]:
    failures = [r for r in reports if r.failure_reason]
    return {
        "generated_at_iso": datetime.now(timezone.utc).isoformat(),
        "overall": "pass" if not failures else "warn",
        "theme_count": len(reports),
        "failure_count": len(failures),
        "themes": [
            {
                "theme": r.theme,
                "query": r.query,
                "locale": r.locale,
                "report_path": f"data/research/{r.theme}.md",
                "citation_count": len(r.citations),
                "citations": [asdict(c) for c in r.citations],
                "failure_reason": r.failure_reason,
            }
            for r in reports
        ],
    }


def write_research_outputs(out_dir: Path, reports: list[ThemeReport]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        atomic_write_text(out_dir / f"{report.theme}.md", format_report_markdown(report))
    atomic_write_text(
        out_dir / "research_status.json",
        json.dumps(status_for_reports(reports), ensure_ascii=False, indent=2),
    )
