from __future__ import annotations

import json
from pathlib import Path

import pytest

import irc.data.manifest as manifest_module
from irc.data.manifest import ManifestEntry, read_manifest, write_manifest


def test_write_then_read_round_trip(tmp_path: Path):
    entry = ManifestEntry(
        source="openbb",
        last_run_at="2026-05-07T15:00:00+08:00",
        schema_version="v1",
        record_counts={"prices": 12500, "macro_series": 240},
        latest_data_date="2026-05-07",
        notes="test run",
    )
    write_manifest(tmp_path, entry)
    out = read_manifest(tmp_path, source="openbb")
    assert out == entry
    # File location
    assert (tmp_path / "_manifest" / "openbb.json").exists()


def test_read_manifest_missing_returns_none(tmp_path: Path):
    assert read_manifest(tmp_path, source="ghost") is None


def test_write_manifest_uses_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[Path, str]] = []

    def fake_atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
        assert encoding == "utf-8"
        calls.append((path, content))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)

    monkeypatch.setattr(manifest_module, "atomic_write_text", fake_atomic_write_text)
    entry = ManifestEntry(
        source="akshare", last_run_at="2026-05-07T16:00:00+08:00",
        schema_version="v1", record_counts={"nav_history": 5000},
        latest_data_date="2026-05-06",
    )
    write_manifest(tmp_path, entry)
    # No leftover .tmp file
    assert not list((tmp_path / "_manifest").glob("*.tmp"))
    assert len(calls) == 1
    assert calls[0][0] == tmp_path / "_manifest" / "akshare.json"
    raw = json.loads((tmp_path / "_manifest" / "akshare.json").read_text())
    assert raw["source"] == "akshare"


def test_write_manifest_rejects_unsafe_source(tmp_path: Path):
    entry = ManifestEntry(
        source="../escape",
        last_run_at="2026-05-07T16:00:00+08:00",
        schema_version="v1",
    )
    with pytest.raises(ValueError):
        write_manifest(tmp_path, entry)
