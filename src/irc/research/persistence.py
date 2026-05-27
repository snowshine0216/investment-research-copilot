from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from irc.io_utils import atomic_write_text
from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport


def extract_prose_from_report_md(report_md: str) -> str:
    """Return only the prose body of a persisted theme-report markdown string.

    Strips the ``# <theme>`` heading and the ``## Citations`` footer (and
    everything after it) so that keyword matching in ``score_thesis_news``
    operates on news *content* only, not on citation titles or URLs.

    This is the single source of truth for prose extraction — called by both
    ``news_summaries._summary_for_theme`` and
    ``gold_cmd._summary_from_theme_report``.  ADR 0007 §2 locks the invariant:
    the keyword rubric must never match citation metadata.

    Pure function: no I/O, no side effects.
    """
    prose_lines: list[str] = []
    for line in report_md.splitlines():
        stripped = line.strip()
        # Stop at the Citations footer (any ## heading signals end of prose)
        if stripped.startswith("## "):
            break
        # Skip the top-level # <theme> heading
        if stripped.startswith("#"):
            continue
        prose_lines.append(line)
    return "\n".join(prose_lines).strip()


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
                "provider_failures": list(r.provider_failures),
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


def load_theme_reports(root: Path) -> dict[str, ThemeReport]:
    """Load persisted theme reports from research_status.json.

    Returns an empty dict when the status file does not exist or cannot be parsed.
    Keys are theme names (e.g. "us_monetary").
    """
    status_path = root / "data" / "research" / "research_status.json"
    if not status_path.exists():
        return {}
    try:
        body = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    reports: dict[str, ThemeReport] = {}
    for item in body.get("themes", []):
        theme = str(item.get("theme", ""))
        if not theme:
            continue
        try:
            md_path = root / item.get("report_path", f"data/research/{theme}.md")
            report_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
            citations = [Citation(**c) for c in item.get("citations", [])]
            reports[theme] = ThemeReport(
                theme=theme,
                query=str(item.get("query") or ""),
                locale=str(item.get("locale") or ""),
                report_md=report_md,
                citations=citations,
                failure_reason=item.get("failure_reason") or "",
                provider_failures=tuple(item.get("provider_failures", ())),
            )
        except (TypeError, KeyError, OSError):
            continue
    return reports
