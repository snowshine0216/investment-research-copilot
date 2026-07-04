from __future__ import annotations
from pathlib import Path
from irc.monitor.holding_metrics import build_holding_metrics, HoldingMetric
from irc.monitor.types import MonitorFund, SignalRecord, FactorContribution, NarrativeDoc
from irc.monitor.valuation import ValuationResolution
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


def test_build_holding_metrics_assembles_from_loaded_inputs():
    # Pure assembly helper — NO I/O. Top holdings + pre-loaded series in → metrics out.
    class _H:
        def __init__(self, s, n, w):
            self.symbol, self.name_cn, self.weight_pct = s, n, w
    holdings = (_H("600519", "贵州茅台", 12.0),)
    flow_by_code = {"600519": (("2026-06-16", 4.0),) * 20}
    metrics = build_holding_metrics(holdings, series_by_code={}, flow_series_by_code=flow_by_code)
    assert isinstance(metrics[0], HoldingMetric)
    assert metrics[0].flow_score == 1.0


# ── Finding 1: flow aggregate wired into FactorInputs for active_cn_equity ───

class _Cfg:
    class history:
        minimum_observations = 2


def _active_fund():
    return MonitorFund(
        id="110011",
        name_cn="易方达蓝筹",
        market="cn_off_exchange",
        analysis_profile="active_cn_equity",
        themes=("cn_equity_property_policy",),
        constituent_news=True,
        weights={"trend": 0.25, "valuation": 0.20, "flow": 0.15,
                 "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40},
        minimum_confidence=0.50,
    )


def _fake_snap():
    """ActiveFundSnapshot with 2 holdings (> 0.50 total weight → coverage gate passes)."""
    def _ca(symbol, name, weight):
        return ConstituentAnalysis(
            symbol=symbol, name_cn=name, weight_pct=weight,
            evidence=(), failure_reasons=(), one_line_view="stub",
        )
    return ActiveFundSnapshot(
        fund_id="110011",
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at="2026-06-19T09:00:00",
        constituent_analyses=(
            _ca("600519", "贵州茅台", 35.0),
            _ca("000858", "五粮液", 25.0),
        ),
        failure_reasons_by_symbol={},
    )


def _flow_series_with_coverage():
    """20 daily flow rows for each symbol — enough for coverage >= 0.50."""
    rows = tuple(("2026-06-" + str(i).zfill(2), 3.5) for i in range(1, 21))
    return {
        "600519": rows,
        "000858": rows,
    }


def test_flow_wired_into_composite_for_active_cn_equity(monkeypatch, tmp_path: Path):
    """FINDING 1 (RED): flow aggregate must be passed to FactorInputs for active_cn_equity.
    Before the fix, FactorInputs.flow is None → _flow() returns 'flow_no_data' →
    FactorScore(eligible=False). After the fix, eligible=True and value is non-None."""
    import irc.commands.monitor_cmd as mc

    monkeypatch.setattr(mc, "nav_series_for", lambda _fid: None)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())
    monkeypatch.setattr(mc, "gather_impacts", lambda **_kw: _FakeImpacts())
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: _fake_snap())
    monkeypatch.setattr(mc, "_load_flow_store_slice",
                        lambda root, symbols: _flow_series_with_coverage())
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(None, False, "valuation_no_anchor"))
    monkeypatch.setattr(mc, "heat_inputs_for", lambda fid, purchase_table: (None, None))
    # _stock_series_by_code is imported inside _process_fund from irc.opportunity.inputs_loader
    import irc.opportunity.inputs_loader as il
    monkeypatch.setattr(il, "_stock_series_by_code", lambda con, syms: {})

    fund = _active_fund()
    cfg = _Cfg()
    llm_config = object()

    view, _costs, _bundle = mc._process_fund(
        fund, cfg, tmp_path, llm_config, today="2026-06-19",
    )

    flow_scores = [s for s in view.factor_scores if s.name == "flow"]
    assert flow_scores, "No flow FactorScore returned"
    fs = flow_scores[0]
    assert fs.eligible, (
        f"flow factor should be eligible (value present), got eligible={fs.eligible}, "
        f"reason={fs.reason!r}"
    )
    assert fs.value is not None, "flow factor value should be non-None"


class _FakeImpacts:
    impacts = ()
    cost_entries = []
    status = "ok"

    def _impact_rows_from(self, fund):
        return ()


# ── Finding 2: exception in flow_reconciliation must yield WARN, not PASS ─────

def test_flow_health_exception_fallback_is_warn(monkeypatch, tmp_path: Path):
    """FINDING 2 (RED): when flow_reconciliation raises, the fallback StageHealth
    must have status='WARN', not 'PASS' (the current bug)."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.eval.types import FundTraceBundle

    def _signal(fid):
        return SignalRecord(
            fund_id=fid, status="ok", bias="ADD_BIAS", composite=0.3,
            signal_confidence=1.0, available_weight=1.0,
            present_families=("price-momentum",),
            contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
            divergence_codes=(),
        )

    from irc.monitor.render_types import FundView

    def _view(fid):
        return FundView(
            fund_id=fid, name_cn="测试", latest_nav=2.0, as_of_date="2026-06-19",
            nav_series=(("2026-06-18", 2.4), ("2026-06-19", 2.5)),
            signal=_signal(fid),
            narrative=NarrativeDoc(fid, (), (), (), "ok"),
            evidence_pool=(), return_table={}, factor_freshness={},
            missing_factor_reasons=(), factor_scores=(),
        )

    fund = _active_fund()
    view = _view(fund.id)
    bundle = FundTraceBundle(fund.id, (), (), ())

    # Patch flow_reconciliation to raise
    def _boom(_proj):
        raise RuntimeError("boom")
    monkeypatch.setattr(mc, "flow_reconciliation", _boom)

    _, _sh, _dh, flow_recon_healths, _fch, _vrh, _vch = mc._compute_gates(
        [fund], [view], [bundle],
        min_obs=2, suite_healths=(),
        trading_days=None,
    )

    health = flow_recon_healths.get(fund.id)
    assert health is not None, "No flow_recon_health returned for fund"
    assert health.status == "WARN", (
        f"Expected WARN on exception fallback, got status={health.status!r}. "
        f"Reasons: {health.reasons}"
    )


# ── board-dark-note e2e (Phase 6 review fix): real run_monitor -> report.html ──


def test_run_monitor_board_dark_note_collapses_all_na_industry_column(tmp_path, monkeypatch):
    """e2e wiring check: a real active_cn_equity fund with a real snapshot on disk
    (via write_active_fund_cache/_make_active_snapshot from test_monitor_constituent)
    but NO valuation DB (no data/local.duckdb -> con stays None, per run_monitor's
    own db_path.exists() guard) and NO flow store on disk -> every _BOARD_NA_COLUMNS
    column, including the industry-valuation legs, is N/A for every holdings-board
    row. Asserts the rendered report.html collapses this to a single
    board-dark-note header carrying a structured reason code (never a bare dash
    wall) for the 行业 column, and that the collapsed columns' raw values are
    absent from the board body (only na-reason spans remain per-cell).

    Wiring bug exposed + fixed (minimal, TDD, see test_dual_track_self_and_
    industry_both_na_sets_industry_no_data_reason in test_holding_metrics.py):
    dual_track_score's self_score-None early return (src/irc/monitor/_dual_track.py)
    never set industry_reason even when the industry leg was ALSO unusable, so
    HoldingMetric.industry_reason stayed None whenever a stock had no PE/PB
    history at all. holdings_board_html's _row_reason fallback chain then read
    past the (always-None) industry_reason key straight to flow_reason for the
    行业 column's board-dark-note label ('行业（flow_no_data）') — a real stock
    had no industry data, mislabeled with an unrelated column's reason. Fixed by
    setting industry_reason='industry_no_data' whenever the industry leg itself
    is unusable, independent of the self leg."""
    import textwrap
    import irc.commands.monitor_cmd as mc
    from tests.commands.test_monitor_cmd import _patch_edges
    from tests.commands.test_monitor_constituent import (
        _make_active_snapshot, _patch_process_fund_edges,
    )
    from irc.fundamentals.snapshot_cache import write_active_fund_cache

    yaml_cfg = textwrap.dedent("""
    schema_version: 1
    history: { minimum_observations: 10, fetch_calendar_days: 550 }
    defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
    funds:
      - { id: "519069", name_cn: 汇添富价值精选, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary, cn_equity_property_policy], constituent_news: true }
    """)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(yaml_cfg, encoding="utf-8")
    snap = _make_active_snapshot("519069")
    write_active_fund_cache(snap, tmp_path / "data")  # real snapshot -> real top-5 holdings

    _patch_process_fund_edges(monkeypatch, "519069")  # _process_fund I/O edges (real helper)
    _patch_edges(monkeypatch)  # preflight/load_yaml/load_trading_days/_build_theme_results
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: _FakeImpacts())
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    monkeypatch.setattr(mc, "_batch_flow_industry", lambda root, symbols: (None, None))
    # No data/local.duckdb written -> run_monitor's own `db_path.exists()` guard
    # keeps con=None; no flow store written -> _load_flow_store_slice degrades to
    # {} — both are real production degrade paths, not hand-built fixtures.

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(
        encoding="utf-8")

    assert "board-dark-note" in html
    # Locate the actual <table class='holdings-board'> section, NOT the earlier
    # `.holdings-board{...}` CSS selector occurrence in <style> (both contain the
    # substring "holdings-board").
    board_start = html.index("<table class='holdings-board'>")
    board_html = html[board_start:]
    note = board_html.split("board-dark-note")[1].split("</p>")[0]
    assert "行业" in note                  # industry column label present in the note
    assert "industry_no_data" in note      # structured reason code, not a bare dash wall
    # collapsed columns must not appear as raw cell content in the board body —
    # only the note carries the reason code, never a per-cell reason span for a
    # fully-dark column (per-row na-reason spans only appear for partially-dark
    # columns, e.g. valuation_state's no_series here).
    board_body = board_html.split("<table", 1)[1].split("</table>")[0]
    assert "industry_no_data" not in board_body
