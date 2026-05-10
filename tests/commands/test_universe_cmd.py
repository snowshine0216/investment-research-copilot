from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml
from click.testing import CliRunner

from irc.cli import main
from irc.commands.universe_cmd import run_build_cn_funds


def _catalog() -> pd.DataFrame:
    return pd.DataFrame([
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
        {"fund_code": "003096", "fund_name": "中欧医疗健康混合C", "fund_type": "混合型"},
        {"fund_code": "510300", "fund_name": "华泰柏瑞沪深300ETF", "fund_type": "指数型-股票"},
        {"fund_code": "000001", "fund_name": "华夏现金增利货币A", "fund_type": "货币型"},
    ])


def test_build_cn_funds_writes_generated_yaml_atomically(tmp_path: Path) -> None:
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        rc = run_build_cn_funds(repo_root=str(tmp_path))

    assert rc == 0
    generated_path = tmp_path / "config" / "universe" / "cn_funds.generated.yaml"
    assert generated_path.exists()
    raw = yaml.safe_load(generated_path.read_text(encoding="utf-8"))
    ids = [row["instrument_id"] for row in raw["instruments"]]
    assert ids == ["003095", "510300"]
    assert raw["instruments"][0]["asset_class"] == "cn_equity_fund"
    assert raw["instruments"][0]["theme"] == "healthcare"


def test_build_cn_funds_prints_counts(tmp_path: Path, capsys) -> None:
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        rc = run_build_cn_funds(repo_root=str(tmp_path))

    captured = capsys.readouterr()
    assert rc == 0
    assert "cn_equity_fund/healthcare: 1" in captured.out
    assert "cn_etf/broad: 1" in captured.out


def test_build_cn_funds_leaves_existing_file_untouched_on_fetch_failure(tmp_path: Path) -> None:
    generated_path = tmp_path / "config" / "universe" / "cn_funds.generated.yaml"
    generated_path.parent.mkdir(parents=True)
    generated_path.write_text("sentinel: true\n", encoding="utf-8")

    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", side_effect=RuntimeError("network down")):
        rc = run_build_cn_funds(repo_root=str(tmp_path))

    assert rc == 1
    assert generated_path.read_text(encoding="utf-8") == "sentinel: true\n"


def test_cli_universe_build_cn_funds_command(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        result = runner.invoke(main, ["universe", "build-cn-funds", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "universe build-cn-funds OK" in result.output
    assert (tmp_path / "config" / "universe" / "cn_funds.generated.yaml").exists()
