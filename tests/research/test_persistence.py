from __future__ import annotations

import json
from pathlib import Path

from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport
from irc.research.persistence import (
    format_report_markdown,
    status_for_reports,
    write_research_outputs,
)


def _ok_report(theme: str) -> ThemeReport:
    return ThemeReport(
        theme=theme, query="q", locale="en",
        report_md=f"Markdown body about {theme}.",
        citations=[Citation(index=1, title="Source", url="https://x")],
        failure_reason="",
    )


def _failed_report(theme: str, reason: str) -> ThemeReport:
    return ThemeReport(
        theme=theme, query="q", locale="en",
        report_md="", citations=[], failure_reason=reason,
    )


def test_format_report_markdown_successful_theme():
    report = _ok_report("us_monetary")
    md = format_report_markdown(report)
    assert "# us_monetary" in md
    assert "Markdown body about us_monetary" in md
    assert "[1] Source — https://x" in md


def test_format_report_markdown_failed_theme():
    report = _failed_report("gold_drivers", "timeout")
    md = format_report_markdown(report)
    assert "# gold_drivers" in md
    assert "research failed: timeout" in md


def test_status_for_reports_all_pass():
    reports = [_ok_report("us_monetary"), _ok_report("cn_monetary")]
    status = status_for_reports(reports)
    assert status["overall"] == "pass"
    assert status["theme_count"] == 2
    assert status["failure_count"] == 0


def test_status_for_reports_partial_failure():
    reports = [_ok_report("us_monetary"), _failed_report("gold_drivers", "timeout")]
    status = status_for_reports(reports)
    assert status["overall"] == "warn"
    assert status["failure_count"] == 1
    assert status["themes"][1]["failure_reason"] == "timeout"


def test_status_for_reports_includes_provider_failures():
    report = ThemeReport(
        theme="us_monetary", query="q", locale="en",
        report_md="body", citations=[],
        failure_reason="",
        provider_failures=("brave: http 503",),
    )
    status = status_for_reports([report])
    assert status["themes"][0]["provider_failures"] == ["brave: http 503"]


def test_write_research_outputs_creates_files(tmp_path: Path):
    reports = [_ok_report("us_monetary"), _failed_report("gold_drivers", "timeout")]
    write_research_outputs(tmp_path, reports)

    assert (tmp_path / "us_monetary.md").exists()
    assert (tmp_path / "gold_drivers.md").exists()
    status_path = tmp_path / "research_status.json"
    assert status_path.exists()
    body = json.loads(status_path.read_text(encoding="utf-8"))
    assert body["overall"] == "warn"
