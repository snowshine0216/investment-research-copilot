from __future__ import annotations
import json
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
    mock_build.return_value = ([_ok_report("us_monetary"), _ok_report("gold_drivers")], [], {})
    rc, _, _units = run_research_pipeline(
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
def test_research_pipeline_returns_zero_and_writes_warn_status_when_any_theme_fails(mock_build, tmp_path: Path):
    mock_build.return_value = (
        [_ok_report("us_monetary"), _failed_report("gold_drivers", "timeout")],
        [],
        {},
    )
    rc, _, _units = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        providers=(),
        extractor=None,  # type: ignore[arg-type]
        route=_route(),
    )
    assert rc == 0
    status_path = tmp_path / "data/research/research_status.json"
    body = json.loads(status_path.read_text(encoding="utf-8"))
    assert body["overall"] == "warn"
    assert "research failed" in (tmp_path / "data/research/gold_drivers.md").read_text()


@patch("irc.research.pipeline.build_theme_reports")
def test_research_pipeline_writes_status_json(mock_build, tmp_path: Path):
    mock_build.return_value = (
        [_ok_report("us_monetary"), _failed_report("gold_drivers", "timeout")],
        [],
        {},
    )
    rc, _, _units = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        providers=(),
        extractor=None,  # type: ignore[arg-type]
        route=_route(),
    )

    status_path = tmp_path / "data/research/research_status.json"
    assert rc == 0
    assert status_path.exists()
    body = json.loads(status_path.read_text(encoding="utf-8"))
    assert body["overall"] == "warn"
    assert body["themes"][0]["theme"] == "us_monetary"
    assert body["themes"][0]["citation_count"] == 1
    assert body["themes"][1]["failure_reason"] == "timeout"


# --- Task 8: quality gate integration ---

def test_run_research_pipeline_returns_2_when_quality_gate_fails(tmp_path, monkeypatch):
    from irc.research import pipeline as p
    from irc.research.theme_research import ThemeReport

    def _all_failed(themes, **_):
        return (
            [
                ThemeReport(theme=t, query="q", locale="zh", report_md="",
                            citations=[], failure_reason="bocha 403")
                for t in themes
            ],
            [],
            {},
        )
    monkeypatch.setattr(p, "build_theme_reports", _all_failed)

    rc, _, _units = p.run_research_pipeline(
        repo_root=tmp_path,
        themes=("cn_monetary", "cn_equity_property_policy"),
        providers=(),
        extractor=object(),
        route=_route(),
    )
    assert rc == 2
    # Status file must still be written so downstream debugging works.
    import json
    status_path = tmp_path / "data" / "research" / "research_status.json"
    assert status_path.exists(), "status file must be written even on gate failure"
    status = json.loads(status_path.read_text())
    assert len(status["themes"]) == 2


def test_run_research_pipeline_prints_summary(tmp_path, monkeypatch, capsys):
    from irc.research import pipeline as p
    from irc.research.theme_research import ThemeReport

    def _mixed(themes, **_):
        return (
            [
                ThemeReport(theme="us_monetary", query="q", locale="en", report_md="x",
                            citations=[], failure_reason=""),
                ThemeReport(theme="cn_monetary", query="q", locale="zh", report_md="",
                            citations=[], failure_reason="bocha 403"),
            ],
            [],
            {},
        )
    monkeypatch.setattr(p, "build_theme_reports", _mixed)

    p.run_research_pipeline(
        repo_root=tmp_path, themes=("us_monetary", "cn_monetary"),
        providers=(), extractor=object(), route=_route(),
    )
    captured = capsys.readouterr()
    out = captured.out + captured.err
    # User must see both the OK and the failing theme by name.
    assert "us_monetary" in out, f"us_monetary not in output: {out!r}"
    assert "cn_monetary" in out, f"cn_monetary not in output: {out!r}"
    assert "bocha 403" in out, f"failure reason not in output: {out!r}"


@patch("irc.research.pipeline.build_theme_reports")
def test_research_pipeline_returns_search_units(mock_build, tmp_path: Path):
    """pipeline threads search_units from build_theme_reports to caller (ADR 0013)."""
    mock_build.return_value = (
        [_ok_report("us_monetary")],
        [],
        {"tavily": 3, "jina": 2},
    )
    _rc, _costs, units = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary",),
        providers=(),
        extractor=None,  # type: ignore[arg-type]
        route=_route(),
    )
    assert units == {"tavily": 3, "jina": 2}
