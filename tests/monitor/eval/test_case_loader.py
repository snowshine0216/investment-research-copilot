from __future__ import annotations
import json
from pathlib import Path
from irc.monitor.eval.case_loader import load_cases


def test_load_cases_returns_sorted_dicts(tmp_path: Path):
    d = tmp_path / "impact"
    d.mkdir()
    (d / "b.json").write_text(json.dumps({"category": "injection"}), encoding="utf-8")
    (d / "a.json").write_text(json.dumps({"category": "directional-strong"}), encoding="utf-8")
    cases = load_cases(tmp_path / "impact")
    assert [c["category"] for c in cases] == ["directional-strong", "injection"]  # sorted by filename
    assert isinstance(cases, tuple)


def test_load_cases_empty_dir_returns_empty_tuple(tmp_path: Path):
    d = tmp_path / "narrative"
    d.mkdir()
    assert load_cases(d) == ()


def test_load_cases_ignores_non_json(tmp_path: Path):
    d = tmp_path / "impact"
    d.mkdir()
    (d / "a.json").write_text(json.dumps({"category": "injection"}), encoding="utf-8")
    (d / "README.md").write_text("not json", encoding="utf-8")
    assert len(load_cases(d)) == 1
