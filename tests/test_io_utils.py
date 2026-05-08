from __future__ import annotations

import os
from pathlib import Path

import pytest

from irc.io_utils import atomic_write_text


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "a/b/c.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    target.write_text("old")
    atomic_write_text(target, "new")
    assert target.read_text() == "new"


def test_atomic_write_no_partial_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "y.txt"
    target.write_text("old")

    def boom(*args: object, **kwargs: object) -> None:
        raise IOError("disk full")

    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(IOError):
        atomic_write_text(target, "new")
    assert target.read_text() == "old"
    assert not list(target.parent.glob("*.tmp"))
    monkeypatch.setattr(os, "fsync", real_fsync)