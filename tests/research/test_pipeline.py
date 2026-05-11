from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
from irc.research.ldr_client import LDRResearchResult, LDRCitation
from irc.research.pipeline import run_research_pipeline


@patch("irc.research.theme_research.run_research")
def test_research_pipeline_writes_markdown_per_theme(mock_run, tmp_path: Path):
    mock_run.return_value = LDRResearchResult(
        report_md="Markdown body about ${theme}.",
        citations=[LDRCitation(index=1, title="Source", url="https://x")],
    )
    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        time_budget_s=10,
    )
    assert rc == 0
    assert (tmp_path / "data/research/us_monetary.md").exists()
    assert (tmp_path / "data/research/gold_drivers.md").exists()


@patch("irc.research.theme_research.run_research")
def test_research_pipeline_returns_nonzero_when_any_theme_fails(mock_run, tmp_path: Path):
    mock_run.side_effect = [
        LDRResearchResult(
            report_md="ok",
            citations=[LDRCitation(index=1, title="Source", url="https://x")],
        ),
        LDRResearchResult(report_md="", citations=[], failure_reason="timeout"),
    ]

    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        time_budget_s=10,
    )

    assert rc == 2
    assert "research failed" in (tmp_path / "data/research/gold_drivers.md").read_text()
