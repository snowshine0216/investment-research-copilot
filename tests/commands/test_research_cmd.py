from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from irc.commands.research_cmd import run_research


@patch("irc.commands.research_cmd.run_research_pipeline", return_value=0)
def test_research_cmd_loads_env_from_repo_root(mock_pipeline, tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    repo_root.mkdir()
    other_cwd.mkdir()
    (repo_root / ".env").write_text(
        "LDR_BASE_URL=http://localhost:5001\n"
        "LDR_TIMEOUT_S=17\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(other_cwd)
    monkeypatch.delenv("LDR_BASE_URL", raising=False)
    monkeypatch.delenv("LDR_TIMEOUT_S", raising=False)

    rc = run_research(repo_root=str(repo_root))

    assert rc == 0
    assert mock_pipeline.call_args.kwargs["repo_root"] == repo_root
    assert mock_pipeline.call_args.kwargs["time_budget_s"] == 17
    assert os.environ["LDR_BASE_URL"] == "http://localhost:5001"