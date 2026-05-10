from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from irc.commands.discover_cmd import run_discover
from irc.commands.init_cmd import run_init


@pytest.fixture
def repo_with_db(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    con.execute("""
        INSERT INTO instruments VALUES
        ('006075', '006075', 'cn_off_exchange', '易方达标普500', NULL, 'us_etf', 'cny',
         '2018-03-26', 0.005, 1e10, 'S&P 500', 5,
         '2026-05-07T10:00:00+08:00', 'akshare', 'akshare:meta:006075:2026-05-07')
    """)
    con.execute("""
        INSERT INTO prices VALUES
        ('006075', '2026-05-06', 4.2, 4.3, 4.1, 4.25, 1e8,
         '2026-05-07T10:00:00+08:00', 'openbb', 'openbb:prices:006075:2026-05-06')
    """)
    con.execute("""
        INSERT INTO fund_metrics VALUES
        ('006075', '2026-05-07', 0.15, 0.12, 0.80, 0.005, 1.2,
         '2026-05-07T10:00:00+08:00', 'akshare', 'akshare:metrics:006075:2026-05-07')
    """)
    con.close()
    return tmp_path


def test_discover_writes_watchlist(repo_with_db: Path) -> None:
    fake_resp_text = (
        "Reason: tracks SP500 (openbb:prices:006075:2026-05-06). Risk: USD strength."
    )
    with patch("irc.discovery.reason_writer.call_chat") as mock_chat:
        mock_chat.return_value.__class__ = type(
            "ChatResponse", (), {
                "text": fake_resp_text, "prompt_tokens": 10, "completion_tokens": 5,
            }
        )()
        mock_chat.return_value.text = fake_resp_text
        mock_chat.return_value.prompt_tokens = 10
        mock_chat.return_value.completion_tokens = 5
        rc = run_discover(repo_root=str(repo_with_db))

    assert rc == 0
    out_dir = next(p for p in (repo_with_db / "outputs").iterdir())
    assert (out_dir / "discovered_watchlist.csv").exists()
    df = pd.read_csv(out_dir / "discovered_watchlist.csv")
    assert "instrument_id" in df.columns


@pytest.fixture
def repo_with_prices_no_metrics(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    discovery_path = tmp_path / "config" / "discovery.yaml"
    discovery_path.write_text(
        discovery_path.read_text(encoding="utf-8").replace(
            "etf_daily_volume_cny_min: 10000000",
            "etf_daily_volume_cny_min: 0",
        ),
        encoding="utf-8",
    )

    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        con.execute("""
            INSERT INTO instruments VALUES
            ('006075', '006075', 'cn_off_exchange', '易方达标普500', NULL, 'us_etf', 'cny',
             '2018-03-26', 0.002, 1e10, 'S&P 500', 5,
             '2026-05-07T10:00:00+08:00', 'akshare', 'akshare:meta:006075:2026-05-07')
        """)
        con.execute("""
            INSERT INTO prices VALUES
            ('006075', '2026-05-06', 4.2, 4.3, 4.1, 4.25, 1e8,
             '2026-05-07T10:00:00+08:00', 'openbb', 'openbb:prices:006075:2026-05-06'),
            ('006075', '2026-05-07', 4.25, 4.35, 4.2, 4.30, 1e8,
             '2026-05-07T10:00:00+08:00', 'openbb', 'openbb:prices:006075:2026-05-07')
        """)
    finally:
        con.close()
    return tmp_path


def test_discover_derives_metrics_when_fund_metrics_empty(
    repo_with_prices_no_metrics: Path,
) -> None:
    fake_resp_text = (
        "Reason: tracks SP500 (openbb:prices:006075:2026-05-06). Risk: USD strength."
    )
    with patch("irc.discovery.reason_writer.call_chat") as mock_chat:
        mock_chat.return_value.__class__ = type(
            "ChatResponse", (), {
                "text": fake_resp_text, "prompt_tokens": 10, "completion_tokens": 5,
            }
        )()
        mock_chat.return_value.text = fake_resp_text
        mock_chat.return_value.prompt_tokens = 10
        mock_chat.return_value.completion_tokens = 5
        rc = run_discover(repo_root=str(repo_with_prices_no_metrics))

    assert rc == 0
    out_dir = next(p for p in (repo_with_prices_no_metrics / "outputs").iterdir())
    df = pd.read_csv(out_dir / "discovered_watchlist.csv", dtype={"instrument_id": str})
    assert df["instrument_id"].tolist() == ["006075"]


def test_discover_passes_excluded_themes_to_pipeline(repo_with_db: Path) -> None:
    preferences_path = repo_with_db / "inputs" / "preferences.yaml"
    preferences_path.write_text(
        preferences_path.read_text(encoding="utf-8").replace(
            "exclude_themes: []",
            "exclude_themes: [healthcare]",
        ),
        encoding="utf-8",
    )

    with patch("irc.commands.discover_cmd.run_discovery") as mock_run:
        mock_run.return_value = pd.DataFrame(columns=["instrument_id"])
        rc = run_discover(repo_root=str(repo_with_db))

    assert rc == 0
    assert mock_run.call_args.kwargs["excluded_themes"] == ("healthcare",)
