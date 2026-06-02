from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from irc.cli import main as cli_main
from irc.commands import narrative_cmd
from irc.fundamentals.types import ThesisEvidence
from irc.narrative.schemas import Holding, NarrativeFundReport


def _wire_repo(tmp_path: Path) -> Path:
    # minimal repo: a narratives config + a tiny cn_funds universe.
    (tmp_path / "config" / "narratives").mkdir(parents=True)
    (tmp_path / "config" / "narratives" / "compute_metals.yaml").write_text(
        "narrative_id: compute_metals\n"
        "display_name_cn: 算力金属\n"
        "display_name_en: Compute-demand metals\n"
        "thesis_cn: t\n"
        "basket:\n"
        "  - { symbol: '601899', name_cn: 紫金矿业 }\n"
        "  - { symbol: '600362', name_cn: 江西铜业 }\n"
        "industries_sw: [有色金属/工业金属]\n"
        "thresholds: { min_basket_weight_pct: 15.0, min_overlap_count: 2 }\n"
        "top_n: 15\n",
        encoding="utf-8",
    )
    return tmp_path


def _evidence(iid: str) -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary=f"{iid} 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def test_screen_only_writes_shortlist_and_diagnostics(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    universe = (
        ("000A", "有色基金", "cn_equity_fund"),
        ("000B", "空仓基金", "cn_equity_fund"),
    )
    monkeypatch.setattr(narrative_cmd, "_enumerate_cn_funds", lambda root: universe)
    holdings_by_id = {
        "000A": (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=12.0),
            Holding(symbol="600362", name_cn="江西铜业", weight_pct=8.0),
        ),
        "000B": (),
    }
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: holdings_by_id[fid],
    )
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=False,
        out_dir=str(out_dir),
    )
    assert rc == 0
    shortlist = json.loads((out_dir / "compute_metals_shortlist.json").read_text())
    assert [r["instrument_id"] for r in shortlist["funds"]] == ["000A"]
    diags = json.loads((out_dir / "compute_metals_screen_diagnostics.json").read_text())
    assert diags["excluded"][0]["instrument_id"] == "000B"
    assert "no_published_holdings" in diags["excluded"][0]["reason"]


def test_unknown_narrative_returns_error(tmp_path: Path) -> None:
    repo = _wire_repo(tmp_path)
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="does_not_exist", analyze=False,
        out_dir=str(repo / "out"),
    )
    assert rc == 2


def test_analyze_renders_real_citations(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    # make analyze deterministic + DB-free: stub the open-db edge + per-fund analyze.
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))
    monkeypatch.setattr(narrative_cmd, "autobuild_active_funds",
                        lambda *a, **k: None)
    expensive = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金",
        position_risk_level="high", risk_rationale="high — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=("theme thesis moves to falsified",),
        trim_triggers=("valuation_state in [expensive, very_expensive]",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(), thesis_evidence=(_evidence("000A"),),
    )
    monkeypatch.setattr(narrative_cmd, "analyze_fund",
                        lambda row, **k: expensive)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 0
    report_md = (out_dir / "compute_metals_report.md").read_text()
    assert re.search(r"\[ref:[0-9a-f]{16}\]", report_md)
    assert "high" in report_md and "trim_review" in report_md


def test_analyze_missing_db_writes_screen_then_errors(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    # no data/local.duckdb in the temp repo, no cached quarter
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: None)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 2
    # screen outputs still written before the error
    assert (out_dir / "compute_metals_shortlist.json").exists()
    assert not (out_dir / "compute_metals_report.json").exists()


def test_run_twice_byte_identical(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir))
    first = (out_dir / "compute_metals_shortlist.json").read_text()
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir))
    second = (out_dir / "compute_metals_shortlist.json").read_text()
    assert first == second


def test_min_overlap_override_widens_shortlist(tmp_path: Path, monkeypatch) -> None:
    # spec §3.1: --min-overlap lowers the basket-weight bar. Config is
    # min_basket_weight_pct=15 / min_overlap_count=2. A fund with one basket
    # holding at 12% (count=1) misses BOTH config thresholds → dropped by default,
    # but qualifies once --min-overlap=10 overrides the weight bar.
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=12.0),
        ),
    )
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir))
    default_funds = json.loads((out_dir / "compute_metals_shortlist.json").read_text())["funds"]
    assert default_funds == []  # 12% < 15% weight and count 1 < 2 → dropped
    narrative_cmd.run_narrative(repo_root=str(repo), name="compute_metals",
                                analyze=False, out_dir=str(out_dir), min_overlap=10.0)
    widened = json.loads((out_dir / "compute_metals_shortlist.json").read_text())["funds"]
    assert [r["instrument_id"] for r in widened] == ["000A"]


def test_cli_narrative_unknown_exits_2(tmp_path: Path) -> None:
    _wire_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["narrative", "nope", "--repo-root", str(tmp_path), "--out", str(tmp_path / "o")],
    )
    assert result.exit_code == 2


def test_analyze_per_fund_error_yields_partial_results(tmp_path: Path, monkeypatch) -> None:
    """F3: if analyze_fund raises for one fund the run still returns rc=0 and
    writes a report with 2 entries; the failed one has position_risk_level='insufficient'."""
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (
            ("000A", "失败基金", "cn_equity_fund"),
            ("000B", "正常基金", "cn_equity_fund"),
        ),
    )
    holdings_by_id = {
        "000A": (Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),),
        "000B": (Holding(symbol="600362", name_cn="江西铜业", weight_pct=16.0),),
    }
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: holdings_by_id[fid],
    )
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))
    monkeypatch.setattr(narrative_cmd, "autobuild_active_funds",
                        lambda *a, **k: None)

    ok_report = NarrativeFundReport(
        instrument_id="000B", name_cn="正常基金",
        position_risk_level="moderate", risk_rationale="ok",
        risk_drivers=(), valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", falsification_triggers=(), trim_triggers=(),
        review_cadence="monthly", evidence_gaps=(), thesis_evidence=(),
    )

    def _patched_analyze(row, **k):
        if row.instrument_id == "000A":
            raise RuntimeError("simulated per-fund crash")
        return ok_report

    monkeypatch.setattr(narrative_cmd, "analyze_fund", _patched_analyze)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 0
    report_data = json.loads((out_dir / "compute_metals_report.json").read_text())
    funds = report_data["funds"]
    assert len(funds) == 2
    failed = next(f for f in funds if f["instrument_id"] == "000A")
    assert failed["position_risk_level"] == "insufficient"


def test_cli_narrative_screen_only(tmp_path: Path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    out = repo / "outputs" / "2026-06-02" / "narrative"
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["narrative", "compute_metals", "--repo-root", str(repo),
         "--out", str(out), "--screen-only"],
    )
    assert result.exit_code == 0
    assert (out / "compute_metals_shortlist.json").exists()


def test_analyze_invokes_autobuild_with_resolved_quarter(tmp_path, monkeypatch) -> None:
    repo = _wire_repo(tmp_path)
    monkeypatch.setattr(
        narrative_cmd, "_enumerate_cn_funds",
        lambda root: (("000A", "有色基金", "cn_equity_fund"),),
    )
    monkeypatch.setattr(
        narrative_cmd, "fetch_top_holdings",
        lambda fid, *, cache_dir: (
            Holding(symbol="601899", name_cn="紫金矿业", weight_pct=20.0),
        ),
    )
    monkeypatch.setattr(narrative_cmd, "_open_analyze_context",
                        lambda root, db_path, quarter: ("CON", "PROV", "2026Q1", {}))
    calls: list = []
    monkeypatch.setattr(
        narrative_cmd, "autobuild_active_funds",
        lambda shortlist, *, provider, quarter, data_dir, today_iso:
        calls.append((tuple(r.instrument_id for r in shortlist), provider, quarter)),
    )
    # analyze_fund stays read-only; stub it to a known report
    expensive = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金", position_risk_level="high",
        risk_rationale="r", risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review", falsification_triggers=(), trim_triggers=(),
        review_cadence="weekly_light_monthly_full", evidence_gaps=(),
        thesis_evidence=(_evidence("000A"),),
    )
    monkeypatch.setattr(narrative_cmd, "analyze_fund", lambda row, **k: expensive)
    out_dir = repo / "outputs" / "2026-06-02" / "narrative"
    rc = narrative_cmd.run_narrative(
        repo_root=str(repo), name="compute_metals", analyze=True,
        out_dir=str(out_dir),
    )
    assert rc == 0
    assert len(calls) == 1
    ids, provider, quarter = calls[0]
    assert ids == ("000A",)
    assert provider == "PROV"
    assert quarter == "2026Q1"  # resolved-context quarter, not None
