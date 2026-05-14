from __future__ import annotations
from pathlib import Path

import pytest

from irc.opportunity.theme_thesis import load_theme_thesis


def test_missing_file_returns_empty_dict(tmp_path: Path):
    out = load_theme_thesis(tmp_path)
    assert out == {}


def test_loads_valid_yaml(tmp_path: Path):
    cfg = tmp_path / "config" / "opportunity"
    cfg.mkdir(parents=True)
    (cfg / "theme_thesis.yaml").write_text(
        "themes:\n"
        "  semiconductor: intact\n"
        "  real_estate: falsified\n"
        "  consumer: under_pressure\n",
        encoding="utf-8",
    )
    out = load_theme_thesis(tmp_path)
    assert out["semiconductor"] == "intact"
    assert out["real_estate"] == "falsified"


def test_rejects_unknown_state_value(tmp_path: Path):
    cfg = tmp_path / "config" / "opportunity"
    cfg.mkdir(parents=True)
    (cfg / "theme_thesis.yaml").write_text(
        "themes:\n  semiconductor: amazing\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_theme_thesis(tmp_path)
