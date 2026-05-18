"""Locator behaviour tests.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/003-spec.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from evals._shared.locator import locate


def _touch(p: Path, content: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_returns_none_when_no_outputs_dir(tmp_path: Path) -> None:
    assert locate(tmp_path, ("foo.csv",)) is None


def test_returns_none_when_no_dated_dir_satisfies_contract(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-01" / "other.csv")
    assert locate(tmp_path, ("required.csv",)) is None


def test_selects_today_when_full_contract_present(tmp_path: Path) -> None:
    today = "2026-05-18"
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / today / "foo.csv")
    result = locate(tmp_path, ("foo.csv",), today_iso=today)
    assert result is not None
    assert result.artifact_date == today
    assert result.paths == (tmp_path / "outputs" / today / "foo.csv",)


def test_falls_back_to_latest_when_today_absent(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-01" / "foo.csv")
    result = locate(tmp_path, ("foo.csv",), today_iso="2026-05-18")
    assert result is not None
    assert result.artifact_date == "2026-05-17"


def test_falls_back_when_today_partial(tmp_path: Path) -> None:
    today = "2026-05-18"
    _touch(tmp_path / "outputs" / today / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-17" / "bar.yaml")
    result = locate(tmp_path, ("foo.csv", "bar.yaml"), today_iso=today)
    assert result is not None
    assert result.artifact_date == "2026-05-17"


def test_rejects_partial_multi_file_set_in_history(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-01" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-01" / "bar.yaml")
    result = locate(tmp_path, ("foo.csv", "bar.yaml"), today_iso="2026-05-18")
    assert result is not None
    assert result.artifact_date == "2026-05-01"


def test_ignores_non_date_subdirs(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "logs" / "foo.csv")
    _touch(tmp_path / "outputs" / "tmp" / "foo.csv")
    assert locate(tmp_path, ("foo.csv",), today_iso="2026-05-18") is None


def test_empty_required_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        locate(tmp_path, (), today_iso="2026-05-18")


def test_paths_preserve_caller_order(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "a")
    _touch(tmp_path / "outputs" / "2026-05-17" / "b")
    _touch(tmp_path / "outputs" / "2026-05-17" / "c")
    result = locate(tmp_path, ("c", "a", "b"), today_iso="2026-05-18")
    assert result is not None
    assert [p.name for p in result.paths] == ["c", "a", "b"]


def test_located_artifacts_is_frozen(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo")
    result = locate(tmp_path, ("foo",), today_iso="2026-05-18")
    assert result is not None
    with pytest.raises(Exception):
        result.artifact_date = "x"  # type: ignore[misc]


def test_default_today_iso_uses_helper(monkeypatch, tmp_path: Path) -> None:
    """The default `today_iso` comes from `_today_iso()`; verify the wiring."""
    import evals._shared.locator as loc
    fixed = "2099-01-02"
    _touch(tmp_path / "outputs" / fixed / "foo")
    monkeypatch.setattr(loc, "_today_iso", lambda: fixed)
    result = locate(tmp_path, ("foo",))
    assert result is not None
    assert result.artifact_date == fixed


def test_directory_named_like_required_filename_is_rejected(tmp_path: Path) -> None:
    """If a directory shares a name with a required filename, the contract
    must be unsatisfied — we want a file, not a directory."""
    (tmp_path / "outputs" / "2026-05-17" / "foo").mkdir(parents=True)
    assert locate(tmp_path, ("foo",), today_iso="2026-05-18") is None
