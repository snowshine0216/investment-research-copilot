from __future__ import annotations
from pathlib import Path
import json
from irc.data.manifest import write_manifest, ManifestEntry, read_manifest


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


def test_write_manifest_uses_atomic_write(tmp_path: Path):
    entry = ManifestEntry(
        source="akshare", last_run_at="2026-05-07T16:00:00+08:00",
        schema_version="v1", record_counts={"nav_history": 5000},
        latest_data_date="2026-05-06",
    )
    write_manifest(tmp_path, entry)
    # No leftover .tmp file
    assert not list((tmp_path / "_manifest").glob("*.tmp"))
    raw = json.loads((tmp_path / "_manifest" / "akshare.json").read_text())
    assert raw["source"] == "akshare"
