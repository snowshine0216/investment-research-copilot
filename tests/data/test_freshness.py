from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from irc.data.freshness import (
    IngestFreshness,
    check_ingest_freshness,
    require_fresh_ingest,
)
from irc.data.manifest import ManifestEntry, write_manifest


def _write_akshare_manifest(repo_root: Path, last_run_at: str) -> None:
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    entry = ManifestEntry(
        source="akshare", last_run_at=last_run_at,
        schema_version="v1", record_counts={"prices": 100},
    )
    write_manifest(repo_root / "data", entry)


def test_fresh_ingest_within_window(tmp_path: Path):
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_akshare_manifest(tmp_path, one_hour_ago)
    result = check_ingest_freshness(tmp_path, max_age=timedelta(hours=24))
    assert isinstance(result, IngestFreshness)
    assert result.is_fresh is True
    assert result.last_ingest_at is not None


def test_stale_ingest_beyond_window(tmp_path: Path):
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    _write_akshare_manifest(tmp_path, two_days_ago)
    result = check_ingest_freshness(tmp_path, max_age=timedelta(hours=24))
    assert result.is_fresh is False
    assert result.observed_age > timedelta(hours=24)


def test_missing_manifest_is_stale(tmp_path: Path):
    result = check_ingest_freshness(tmp_path, max_age=timedelta(hours=24))
    assert result.is_fresh is False
    assert result.last_ingest_at is None


def test_require_fresh_passes_when_fresh(tmp_path: Path):
    _write_akshare_manifest(tmp_path,
                            datetime.now(timezone.utc).isoformat())
    assert require_fresh_ingest(tmp_path, "gold") is True
    assert not (tmp_path / "outputs").exists() or not list(
        (tmp_path / "outputs").rglob("STALE_INGEST.md")
    )


def test_require_fresh_writes_stale_marker_when_stale(tmp_path: Path):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    ok = require_fresh_ingest(tmp_path, "gold")
    assert ok is False
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1
    body = markers[0].read_text(encoding="utf-8")
    assert "gold" in body
    assert "24:00:00" in body or "1 day" in body or "max" in body.lower()
    assert "IRC_ALLOW_STALE" in body
    assert "STALE INGEST" in body.upper()


def test_allow_stale_env_lets_stage_proceed(tmp_path: Path, monkeypatch):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    assert require_fresh_ingest(tmp_path, "gold") is True
    # marker still written for transparency, just not blocking
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes", "on"])
def test_allow_stale_env_truthy_values(tmp_path: Path, monkeypatch, value):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    monkeypatch.setenv("IRC_ALLOW_STALE", value)
    assert require_fresh_ingest(tmp_path, "gold") is True


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_allow_stale_env_falsy_values(tmp_path: Path, monkeypatch, value):
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_akshare_manifest(tmp_path, stale)
    monkeypatch.setenv("IRC_ALLOW_STALE", value)
    assert require_fresh_ingest(tmp_path, "gold") is False
