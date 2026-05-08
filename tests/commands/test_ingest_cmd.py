from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from irc.commands.init_cmd import run_init
from irc.commands.ingest_cmd import run_ingest


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    return tmp_path


def test_ingest_creates_duckdb_and_manifest(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6), date(2026, 5, 7)],
        "open": [4.2, 4.25], "high": [4.3, 4.31], "low": [4.18, 4.22],
        "close": [4.25, 4.28], "volume": [1e8, 1.1e8],
    })
    fake_macro = pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})
    fake_nav = pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.23, 1.24], "nav_acc": [2.34, 2.35],
    })
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=fake_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=fake_nav),
    ):
        rc = run_ingest(repo_root=str(repo))

    assert rc == 0
    assert (repo / "data" / "local.duckdb").exists()
    assert (repo / "data" / "_manifest" / "openbb.json").exists()
    assert (repo / "data" / "_manifest" / "akshare.json").exists()


def test_ingest_idempotent(repo: Path) -> None:
    fake_prices = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3],
        "low": [4.18], "close": [4.25], "volume": [1e8],
    })
    empty_macro = pd.DataFrame({"date": [], "value": []})
    empty_nav = pd.DataFrame({"date": [], "nav": [], "nav_acc": []})
    with (
        patch("irc.commands.ingest_cmd.fetch_etf_price_history", return_value=fake_prices),
        patch("irc.commands.ingest_cmd.fetch_macro_series", return_value=empty_macro),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history", return_value=empty_nav),
    ):
        rc1 = run_ingest(repo_root=str(repo))
        rc2 = run_ingest(repo_root=str(repo))

    assert rc1 == rc2 == 0
