from __future__ import annotations
from pathlib import Path
import yaml
from irc.commands.init_cmd import run_init
from irc.commands.validate_cmd import run_validate


def test_validate_passes_after_init(tmp_path: Path):
    assert run_init(str(tmp_path), force=False) == 0
    rc = run_validate(repo_root=str(tmp_path))
    assert rc == 0


def test_validate_fails_on_corrupted_yaml(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    (tmp_path / "inputs/preferences.yaml").write_text("not: valid: yaml: :", encoding="utf-8")
    rc = run_validate(repo_root=str(tmp_path))
    assert rc != 0


def test_validate_fails_on_schema_violation(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    raw = yaml.safe_load((tmp_path / "config/scoring.yaml").read_text())
    raw["factor_weights"]["risk"] = 0.99  # break sum
    (tmp_path / "config/scoring.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    rc = run_validate(repo_root=str(tmp_path))
    assert rc != 0
