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


# ---------- load_theme_reports round-trip ----------


from irc.research.persistence import load_theme_reports  # noqa: E402


def test_load_theme_reports_returns_empty_when_no_status_file(tmp_path: Path):
    assert load_theme_reports(tmp_path) == {}


def test_load_theme_reports_round_trips_successful_theme(tmp_path: Path):
    reports = [_ok_report("us_monetary")]
    write_research_outputs(tmp_path / "data" / "research", reports)
    loaded = load_theme_reports(tmp_path)
    assert "us_monetary" in loaded
    r = loaded["us_monetary"]
    assert r.failure_reason == ""
    assert r.theme == "us_monetary"
    assert len(r.citations) == 1


def test_load_theme_reports_round_trips_failed_theme(tmp_path: Path):
    reports = [_failed_report("gold_drivers", "timeout")]
    write_research_outputs(tmp_path / "data" / "research", reports)
    loaded = load_theme_reports(tmp_path)
    assert "gold_drivers" in loaded
    r = loaded["gold_drivers"]
    assert r.failure_reason == "timeout"


def test_load_theme_reports_round_trips_provider_failures(tmp_path: Path):
    report = ThemeReport(
        theme="cn_monetary", query="q", locale="zh",
        report_md="body", citations=[],
        failure_reason="",
        provider_failures=("brave: http 429", "bocha: timeout"),
    )
    write_research_outputs(tmp_path / "data" / "research", [report])
    loaded = load_theme_reports(tmp_path)
    assert loaded["cn_monetary"].provider_failures == ("brave: http 429", "bocha: timeout")


def test_load_theme_reports_successful_theme_has_empty_failure_reason(tmp_path: Path):
    """Regression: failure_reason=null in JSON must deserialise to '' not 'None'."""
    status = {
        "generated_at_iso": "2026-05-15T00:00:00+00:00",
        "overall": "pass",
        "theme_count": 1,
        "failure_count": 0,
        "themes": [{
            "theme": "us_monetary",
            "query": "us fed rate",
            "locale": "en",
            "report_path": "data/research/us_monetary.md",
            "citation_count": 0,
            "citations": [],
            "failure_reason": None,      # null in JSON — the risky case
            "provider_failures": [],
        }],
    }
    research_dir = tmp_path / "data" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "research_status.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    loaded = load_theme_reports(tmp_path)
    assert loaded["us_monetary"].failure_reason == ""
