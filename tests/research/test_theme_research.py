from __future__ import annotations
from unittest.mock import patch
from irc.research.theme_research import build_theme_reports, ThemeReport
from irc.research.ldr_client import LDRResearchResult, LDRCitation


@patch("irc.research.theme_research.run_research")
def test_build_theme_reports_one_per_theme(mock_run):
    mock_run.return_value = LDRResearchResult(
        report_md="Markdown body",
        citations=[LDRCitation(index=1, title="Fed", url="https://fed")],
    )
    out = build_theme_reports(themes=("us_monetary", "gold_drivers"))
    assert len(out) == 2
    assert all(isinstance(r, ThemeReport) for r in out)
    assert out[0].theme in ("us_monetary", "gold_drivers")


@patch("irc.research.theme_research.run_research")
def test_failure_recorded_in_report(mock_run):
    mock_run.return_value = LDRResearchResult(report_md="", failure_reason="timeout")
    out = build_theme_reports(themes=("us_monetary",))
    assert out[0].failure_reason == "timeout"
    assert out[0].report_md == ""
