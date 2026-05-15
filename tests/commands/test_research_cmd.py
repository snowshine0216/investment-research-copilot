from __future__ import annotations
from pathlib import Path
from unittest.mock import patch

from irc.commands.research_cmd import run_research


def test_research_cmd_skips_when_no_providers_configured(tmp_path: Path, monkeypatch) -> None:
    """No search keys set → command exits 0 with a clear message, no pipeline call."""
    repo_root = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    repo_root.mkdir()
    elsewhere.mkdir()
    (repo_root / ".env").write_text("DEEPSEEK_API_KEY=sk-test\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)  # avoid picking up the project's real .env
    for key in ("TAVILY_API_KEY", "BRAVE_API_KEY", "BOCHA_API_KEY", "JINA_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    with patch("irc.commands.research_cmd.run_research_pipeline") as mock_pipeline:
        rc = run_research(repo_root=str(repo_root))

    assert rc == 2
    assert mock_pipeline.call_count == 0


def test_research_cmd_loads_env_and_calls_pipeline_when_providers_present(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    repo_root.mkdir()
    other_cwd.mkdir()
    (repo_root / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test\nTAVILY_API_KEY=tvly-test\n", encoding="utf-8"
    )
    monkeypatch.chdir(other_cwd)
    for key in ("TAVILY_API_KEY", "BRAVE_API_KEY", "BOCHA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    with patch("irc.commands.research_cmd.run_research_pipeline", return_value=0) as mock_pipeline, \
         patch("irc.commands.research_cmd.load_repo_configs") as mock_cfg, \
         patch("irc.commands.research_cmd.resolve_route") as mock_route:
        mock_cfg.return_value.llm = object()
        mock_route.return_value = object()
        rc = run_research(repo_root=str(repo_root))

    assert rc == 0
    assert mock_pipeline.call_args.kwargs["repo_root"] == repo_root
    providers = mock_pipeline.call_args.kwargs["providers"]
    assert len(providers) == 1
    assert providers[0].name == "tavily"


def test_research_cmd_accepts_selected_themes(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    repo_root.mkdir()
    other_cwd.mkdir()
    (repo_root / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test\nTAVILY_API_KEY=tvly-test\nBOCHA_API_KEY=bocha-test\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    with patch("irc.commands.research_cmd.run_research_pipeline", return_value=0) as mock_pipeline, \
         patch("irc.commands.research_cmd.load_repo_configs") as mock_cfg, \
         patch("irc.commands.research_cmd.resolve_route") as mock_route:
        mock_cfg.return_value.llm = object()
        mock_route.return_value = object()
        rc = run_research(repo_root=str(repo_root), themes=("us_monetary", "cn_monetary"))

    assert rc == 0
    assert mock_pipeline.call_args.kwargs["themes"] == ("us_monetary", "cn_monetary")
