from __future__ import annotations
from pathlib import Path
import json
from irc.commands.freshness_cmd import run_freshness


def test_freshness_prints_no_manifest(tmp_path: Path, capsys):
    rc = run_freshness(repo_root=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "no manifest" in out.lower()


def test_freshness_summarizes_existing_manifest(tmp_path: Path, capsys):
    manifest_dir = tmp_path / "data/_manifest"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "openbb.json").write_text(json.dumps({
        "source": "openbb",
        "last_run_at": "2026-05-07T12:00:00+08:00",
        "schema_version": "v1",
    }), encoding="utf-8")
    rc = run_freshness(repo_root=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "openbb" in out
    assert "2026-05-07" in out
