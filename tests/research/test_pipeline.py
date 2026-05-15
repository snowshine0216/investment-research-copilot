from __future__ import annotations
from pathlib import Path
from unittest.mock import patch

from irc.llm._types import ResolvedRoute
from irc.research.pipeline import run_research_pipeline
from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport


def _route() -> ResolvedRoute:
    return ResolvedRoute(
        task="research_synth", provider="deepseek", model="deepseek-chat",
        base_url="https://api.deepseek.com/v1", api_key_env="DEEPSEEK_API_KEY",
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


@patch("irc.research.pipeline.build_theme_reports")
def test_research_pipeline_writes_markdown_per_theme(mock_build, tmp_path: Path):
    mock_build.return_value = [_ok_report("us_monetary"), _ok_report("gold_drivers")]
    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        providers=(),
        extractor=None,  # type: ignore[arg-type]
        route=_route(),
    )
    assert rc == 0
    assert (tmp_path / "data/research/us_monetary.md").exists()
    assert (tmp_path / "data/research/gold_drivers.md").exists()


@patch("irc.research.pipeline.build_theme_reports")
def test_research_pipeline_returns_nonzero_when_any_theme_fails(mock_build, tmp_path: Path):
    mock_build.return_value = [
        _ok_report("us_monetary"),
        _failed_report("gold_drivers", "timeout"),
    ]
    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        providers=(),
        extractor=None,  # type: ignore[arg-type]
        route=_route(),
    )
    assert rc == 2
    assert "research failed" in (tmp_path / "data/research/gold_drivers.md").read_text()
