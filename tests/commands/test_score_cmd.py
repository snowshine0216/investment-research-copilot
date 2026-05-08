from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from irc.commands.init_cmd import run_init
from irc.commands.score_cmd import run_score


@pytest.fixture
def repo_with_watchlist(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / "2026-05-07"
    out_dir.mkdir(parents=True)
    pd.DataFrame([{
        "instrument_id": "VTI", "name_cn": "VTI", "asset_class": "us_etf",
        "role": "core_us_equity", "cited_refs": "r1", "tracked_index": "S&P 500",
    }]).to_csv(out_dir / "discovered_watchlist.csv", index=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    con.close()
    return tmp_path


@patch("irc.scoring.pipeline.score_macro_fit")
def test_score_writes_scoring_json(mock_macro, repo_with_watchlist: Path) -> None:
    mock_macro.return_value = MagicMock(score=70, raw_refs=("r",), components={})
    rc = run_score(repo_root=str(repo_with_watchlist))
    assert rc == 0
    scoring_files = list((repo_with_watchlist / "outputs").rglob("scoring.json"))
    assert len(scoring_files) == 1
