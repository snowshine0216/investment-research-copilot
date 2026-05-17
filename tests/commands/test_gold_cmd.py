from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.gold_cmd import run_gold


@pytest.fixture
def repo_with_gold_data(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    from irc.data.manifest import ManifestEntry, write_manifest
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    base = date(2026, 5, 7)
    for i in range(180):
        d = base - timedelta(days=180 - i)
        con.execute(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["518880", d.isoformat(), 4.20, 4.25, 4.18, 4.20 + i * 0.005, 1e7,
             "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:prices:518880:{d.isoformat()}"],
        )
    # Macro series
    for s, v in (("DGS10", 4.0), ("DXY", 104.0)):
        con.execute(
            "INSERT INTO macro_series VALUES (?, ?, ?, ?, ?, ?)",
            [s, base.isoformat(), v, "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:macro_series:{s}:{base.isoformat()}"],
        )
    con.close()
    # Write a fresh akshare manifest so the freshness gate passes by default.
    fresh_ts = datetime.now(timezone.utc).isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=fresh_ts,
        schema_version="v1", record_counts={"prices": 180},
    ))
    return tmp_path


def test_gold_writes_regime_and_band(repo_with_gold_data: Path):
    rc = run_gold(repo_root=str(repo_with_gold_data))
    assert rc == 0
    out_dir = next(p for p in (repo_with_gold_data / "outputs").iterdir())
    assert (out_dir / "gold_regime.json").exists()
    assert (out_dir / "gold_band.yaml").exists()


def test_gold_refuses_to_run_when_ingest_is_stale(repo_with_gold_data: Path, monkeypatch):
    """When data/_manifest/akshare.json is >24h old, gold exits without producing
    artifacts and writes STALE_INGEST.md."""
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_gold_data
    # Overwrite the manifest with a stale timestamp.
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))

    monkeypatch.delenv("IRC_ALLOW_STALE", raising=False)
    rc = run_gold(str(repo))
    assert rc == 1
    markers = list((repo / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_gold_allow_stale_env_proceeds(repo_with_gold_data: Path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_gold_data
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    rc = run_gold(str(repo))
    assert rc == 0  # proceeds with stale data
    assert (repo / "outputs" / next(iter((repo / "outputs").iterdir())).name
            / "STALE_INGEST.md").exists()


def test_gold_uses_geopolitical_stress_from_theme_report(monkeypatch, repo_with_gold_data: Path):
    """When a stressful geopolitics theme report exists in data/research/,
    gold_cmd uses a stress score above the hardcoded 0.4 default."""
    from irc.research.theme_research import ThemeReport

    captured: dict[str, float] = {}
    stress_report = ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md="war war sanction tariff strike conflict",
        citations=[], failure_reason="",
    )

    monkeypatch.setattr(
        "irc.commands.gold_cmd.load_theme_reports",
        lambda root: {"geopolitics": stress_report},
    )

    def capture_score(inputs, cfg):
        captured["stress"] = inputs.geopolitical_stress_0to1
        from irc.scoring.gold_score import compute_gold_score as real_fn
        return real_fn(inputs, cfg)

    monkeypatch.setattr("irc.commands.gold_cmd.compute_gold_score", capture_score)

    rc = run_gold(repo_root=str(repo_with_gold_data))
    assert rc == 0
    assert captured["stress"] > 0.4
