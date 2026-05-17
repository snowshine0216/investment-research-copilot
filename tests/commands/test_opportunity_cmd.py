from __future__ import annotations
import json
from pathlib import Path



def _seed_minimal_repo(tmp_path: Path) -> None:
    """Create the minimum file layout needed by run_opportunity."""
    from datetime import datetime, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    # Write a fresh akshare manifest so the freshness gate passes by default.
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))

    # inputs/account.yaml
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund, cn_brokerage]\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )

    # inputs/preferences.yaml — minimal viable
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band:\n  max_drawdown: [0.05, 0.20]\n  horizon: long_core_medium_rotation\n"
        "universe:\n  cn_funds: true\n  cn_etfs: true\n  hk_etfs: true\n  us_etfs: true\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance:\n  cny: [0.5, 1.0]\n  usd: [0.0, 0.4]\n  hkd: [0.0, 0.3]\n"
        "constraints:\n  allow_short: false\n  allow_leverage: false\n  exclude_themes: []\n"
        "investment_plan:\n  monthly_new_capital_cny: 5000\n"
        "report_language: zh\n",
        encoding="utf-8",
    )

    # config files — copy from the project's templates directory at runtime; the
    # tested command does not need the full bundle for opportunity-only logic.
    repo = Path(__file__).resolve().parents[2]
    src_tpl = repo / "src" / "irc" / "templates"
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((src_tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")

    # outputs/2026-05-14/scoring.json — a single instrument
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({
            "scores": [{
                "instrument_id": "510300",
                "asset_class": "cn_etf",
                "role": "core_cn_equity",
                "composite_score": 75.0,
                "action": "buy_candidate",
                "data_completeness": 0.85,
                "factor_breakdown": {
                    "valuation_cost": {"score": 80, "raw_refs": []},
                    "risk": {"score": 70, "raw_refs": []},
                    "quality": {"score": 75, "raw_refs": []},
                    "macro_fit": {"score": 65, "raw_refs": []},
                    "thesis_news": {"score": 80, "raw_refs": []},
                },
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_opportunity_command_writes_three_outputs(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd._today", lambda: "2026-05-14"
    )
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    out = tmp_path / "outputs" / "2026-05-14"
    assert (out / "opportunity_report.json").exists()
    assert (out / "thesis_cards.yaml").exists()
    assert (out / "discipline_report.md").exists()


def test_opportunity_report_json_has_summary_and_rows(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    payload = json.loads((tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json").read_text())
    assert payload["date"] == "2026-05-14"
    assert "summary" in payload
    assert isinstance(payload["rows"], list)


def test_opportunity_markdown_starts_with_chinese_sections(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    md = (tmp_path / "outputs" / "2026-05-14" / "discipline_report.md").read_text()
    assert "## 今日可定投" in md
    assert "## 关于回撤的说明" in md


def test_opportunity_does_not_read_external_worktree_path(tmp_path: Path, monkeypatch):
    """Acceptance criterion: never read the external worktree generated universe."""
    import irc.commands.opportunity_cmd as opp_mod
    src = Path(opp_mod.__file__).read_text(encoding="utf-8")
    assert "investment-research-copilot.worktrees" not in src


def test_opportunity_works_with_missing_scoring(tmp_path: Path, monkeypatch):
    """Falls back to latest outputs when today's scoring.json missing."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    # Move scoring under an older date
    today_dir = tmp_path / "outputs" / "2026-05-14"
    older_dir = tmp_path / "outputs" / "2026-05-13"
    older_dir.mkdir(parents=True)
    (today_dir / "scoring.json").rename(older_dir / "scoring.json")
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0


def test_opportunity_returns_error_for_invalid_theme_thesis(tmp_path: Path, monkeypatch, capsys):
    """Issue 4 fix: invalid theme_thesis.yaml must return rc=2 with a clean error."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    (tmp_path / "config" / "opportunity").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "opportunity" / "theme_thesis.yaml").write_text(
        "themes:\n  semiconductor: TYPO_STATE\n", encoding="utf-8"
    )
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 2
    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "theme_thesis.yaml" in captured.out


def test_opportunity_prints_warning_for_stale_scoring(tmp_path: Path, monkeypatch, capsys):
    """Issue 5 fix: stale scoring.json fallback must emit a WARNING."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    today_dir = tmp_path / "outputs" / "2026-05-14"
    older_dir = tmp_path / "outputs" / "2026-05-13"
    older_dir.mkdir(parents=True)
    (today_dir / "scoring.json").rename(older_dir / "scoring.json")
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "2026-05-13" in captured.out


def test_empty_available_venues_treats_all_instruments_as_compatible(tmp_path: Path, monkeypatch, capsys):
    """Empty available_venues (no restriction configured) means venue_compatible=True for all.

    An account with no venues declared should not block every instrument;
    'no venue restriction configured' is treated as 'allow all'.
    """
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    # Override account.yaml to have no available_venues
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: []\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    # With empty venues, no instrument should be in exclude state due to venue.
    # Since scoring row has no venue_required in the minimal seed, all rows should be non-exclude.
    out_path = tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    excluded = [r for r in rows if r.get("opportunity_state") == "exclude"]
    assert not excluded, f"No rows should be venue-excluded when available_venues is empty: {excluded}"


def test_opportunity_refuses_to_run_when_ingest_is_stale(tmp_path: Path, monkeypatch):
    """When data/_manifest/akshare.json is >24h old, opportunity exits with rc=1
    and writes STALE_INGEST.md."""
    from datetime import datetime, timedelta, timezone
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.data.manifest import ManifestEntry, write_manifest

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.delenv("IRC_ALLOW_STALE", raising=False)
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 1
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_opportunity_allow_stale_env_proceeds(tmp_path: Path, monkeypatch):
    """With IRC_ALLOW_STALE=1, opportunity proceeds despite stale ingest."""
    from datetime import datetime, timedelta, timezone
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.data.manifest import ManifestEntry, write_manifest

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_build_input_empty_venues_treats_instrument_as_compatible():
    """Unit test: _build_input with empty set() treats venue_required instruments as compatible."""
    from irc.commands.opportunity_cmd import _build_input
    from irc.data.duckdb_helper import ensure_schema
    from unittest.mock import MagicMock
    import duckdb
    instr = MagicMock()
    instr.asset_class = "cn_etf"
    instr.market = "cn_brokerage"
    instr.theme = "broad"
    instr.tracked_index = "沪深300"
    instr.name_cn = "沪深300ETF"
    instr.venue_required = ["cn_brokerage"]
    con = duckdb.connect(":memory:")
    ensure_schema(con)
    try:
        inp = _build_input(
            {"instrument_id": "510300", "role": ""},
            instr, None, None, 0.0, set(),  # empty venues
            con,
        )
    finally:
        con.close()
    assert inp.venue_compatible is True


def test_opportunity_cmd_passes_snapshot_when_available(tmp_path: Path, monkeypatch) -> None:
    """When snapshot data is available, it is passed into build_opportunity_row."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.fundamentals.snapshot import write_snapshot
    from irc.fundamentals.types import ConstituentSnapshot

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")

    snap = ConstituentSnapshot(
        lookthrough_target="沪深300",
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=(),
    )
    write_snapshot(snap, tmp_path / "data")

    captured_kwargs: list[dict] = []
    import irc.commands.opportunity_cmd as opp_mod
    original_build = opp_mod.build_opportunity_row

    def capturing_build(inp, theme_thesis, *, snapshot=None, theme_report=None):
        captured_kwargs.append({"snapshot": snapshot, "theme_report": theme_report})
        return original_build(inp, theme_thesis, snapshot=snapshot, theme_report=theme_report)

    monkeypatch.setattr(opp_mod, "build_opportunity_row", capturing_build)

    rc = run_opportunity(repo_root=str(tmp_path))

    assert rc == 0
    assert any(c["snapshot"] is not None for c in captured_kwargs)


def test_opportunity_cmd_passes_none_snapshot_when_no_cache(tmp_path: Path, monkeypatch) -> None:
    """When no snapshot exists, snapshot=None is passed (degrade-not-halt)."""
    from irc.commands.opportunity_cmd import run_opportunity

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")

    captured_kwargs: list[dict] = []
    import irc.commands.opportunity_cmd as opp_mod
    original_build = opp_mod.build_opportunity_row

    def capturing_build(inp, theme_thesis, *, snapshot=None, theme_report=None):
        captured_kwargs.append({"snapshot": snapshot, "theme_report": theme_report})
        return original_build(inp, theme_thesis, snapshot=snapshot, theme_report=theme_report)

    monkeypatch.setattr(opp_mod, "build_opportunity_row", capturing_build)

    rc = run_opportunity(repo_root=str(tmp_path))

    assert rc == 0
    assert all(c["snapshot"] is None for c in captured_kwargs)
