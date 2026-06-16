from __future__ import annotations
from pathlib import Path
import pytest
from irc.commands.init_cmd import run_init


def test_init_creates_inputs_and_config(tmp_path: Path):
    rc = run_init(repo_root=str(tmp_path), force=False)
    assert rc == 0
    assert (tmp_path / "inputs/account.yaml").exists()
    assert (tmp_path / "inputs/preferences.yaml").exists()
    assert (tmp_path / "config/llm.yaml").exists()
    assert (tmp_path / "config/scoring.yaml").exists()
    assert (tmp_path / "config/gold_drivers.yaml").exists()
    assert (tmp_path / "config/discovery.yaml").exists()
    assert (tmp_path / "config/valuation_buckets.yaml").exists()
    assert (tmp_path / "config/triggers.yaml").exists()
    assert (tmp_path / "config/overrides.yaml").exists()
    assert (tmp_path / "config/macro_view.yaml").exists()
    assert (tmp_path / "config/monitor.yaml").exists()
    for name in ("qdii_us", "qdii_hk", "cn_funds", "gold"):
        assert (tmp_path / f"config/universe/{name}.yaml").exists()
    # spend gate configs must be scaffolded too — `irc config validate` requires them
    assert (tmp_path / "config/spend_pricing.yaml").exists()
    assert (tmp_path / "config/spend_balances.yaml").exists()


def test_init_does_not_overwrite_unless_force(tmp_path: Path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/account.yaml").write_text("# user-modified", encoding="utf-8")
    rc = run_init(repo_root=str(tmp_path), force=False)
    assert rc == 0
    assert (tmp_path / "inputs/account.yaml").read_text() == "# user-modified"


def test_init_force_overwrites(tmp_path: Path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/account.yaml").write_text("# user-modified", encoding="utf-8")
    rc = run_init(repo_root=str(tmp_path), force=True)
    assert rc == 0
    assert "broker" in (tmp_path / "inputs/account.yaml").read_text()


def test_init_returns_1_on_write_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """run_init returns exit code 1 when a template write fails."""
    from irc.commands import init_cmd

    def _failing_read(rel_path: str) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(init_cmd, "_read_template", _failing_read)
    rc = run_init(repo_root=str(tmp_path), force=False)
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()
