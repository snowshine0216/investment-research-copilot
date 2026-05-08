"""
End-to-end test for the full Plan 3 pipeline:
  init → ingest → discover → score → gold → allocate → plan → memo → ask → run

All external I/O (OpenBB, AKShare, LLM) is patched so this runs offline.
Assertions verify that every stage produces its expected output file and that
`irc run` can replay the entire chain via the orchestrator.
"""
from __future__ import annotations

import contextlib
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import json
import yaml
import pandas as pd
import pytest
from click.testing import CliRunner

from irc.cli import main


# ─── fake data helpers ──────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _fake_prices() -> pd.DataFrame:
    rows = [
        {"date": date(2026, d, 1), "open": 3300.0 + d, "high": 3310.0 + d,
         "low": 3290.0 + d, "close": 3305.0 + d, "volume": 1.5e8}
        for d in range(1, 10)
    ]
    return pd.DataFrame(rows)


def _fake_macro() -> pd.DataFrame:
    return pd.DataFrame({"date": [date(2026, 5, 7)], "value": [1.65]})


def _fake_nav() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-05-06", "2026-05-07"],
        "nav": [1.234, 1.245], "nav_acc": [2.345, 2.356],
    })


def _fake_fund_metadata(fund_code: str) -> dict:
    return {
        "fund_code": fund_code,
        "name_cn": f"基金{fund_code}",
        "fund_type": "ETF",
        "aum_text": "200亿",
        "inception_date": "2018-03-26",
        "expense_ratio": "0.20%",
        "manager_tenure_years": 6,
    }


def _discover_chat_response(instrument_id: str = "006075") -> MagicMock:
    """LLM reason that includes a valid raw_ref so the citation check passes.

    Cites both an akshare NAV ref (covers off-exchange feeders like 006075) and
    an openbb prices ref (covers on-exchange ETFs like 513500), so the same
    mocked response works for any candidate produced by discovery."""
    return MagicMock(
        text=(
            f"Reason cites akshare:nav_history:{instrument_id}:2026-05-06 "
            f"and openbb:prices:{instrument_id}:2026-05-01. Strong thesis."
        ),
        prompt_tokens=10,
        completion_tokens=5,
    )


def _macro_fit_response() -> MagicMock:
    return MagicMock(
        text='{"score": 70, "rationale": "stable rates"}',
        prompt_tokens=20,
        completion_tokens=10,
    )


def _memo_response() -> MagicMock:
    return MagicMock(
        text="# 投资决策备忘录\n综合分析显示黄金超配，标的风险适中。",
        prompt_tokens=100,
        completion_tokens=80,
    )


def _audit_response() -> MagicMock:
    return MagicMock(
        text="审计通过。无合规问题。",
        prompt_tokens=50,
        completion_tokens=20,
    )


def _ask_response() -> MagicMock:
    return MagicMock(
        text="该标的评分较高，建议关注。",
        prompt_tokens=30,
        completion_tokens=15,
    )


# ─── shared patch context ────────────────────────────────────────────────────

def _all_patches(instrument_id: str = "006075"):
    """Return a list of (target, kwargs) for unittest.mock.patch."""
    return [
        patch("irc.commands.ingest_cmd.fetch_etf_price_history",
              return_value=_fake_prices()),
        patch("irc.commands.ingest_cmd.fetch_macro_series",
              return_value=_fake_macro()),
        patch("irc.commands.ingest_cmd.fetch_fund_nav_history",
              return_value=_fake_nav()),
        patch("irc.commands.ingest_cmd.fetch_fund_metadata",
              side_effect=_fake_fund_metadata),
        patch("irc.commands.ingest_cmd.fetch_etf_metadata_em",
              side_effect=_fake_fund_metadata),
        patch("irc.discovery.reason_writer.call_chat",
              side_effect=lambda *a, **kw: _discover_chat_response(instrument_id)),
        patch("irc.scoring.factors.macro_fit.call_chat",
              return_value=_macro_fit_response()),
        patch("irc.memo.synthesizer.call_chat",
              return_value=_memo_response()),
        patch("irc.memo.auditor.call_chat",
              return_value=_audit_response()),
        patch("irc.queries.responder.call_chat",
              return_value=_ask_response()),
    ]


# ─── test: stage-by-stage (verifies each output artifact) ────────────────────

def test_e2e_plan3_all_stages(tmp_path: Path) -> None:
    runner = CliRunner()
    today = _today()

    # ── init ──────────────────────────────────────────────────────────────────
    r = runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    assert r.exit_code == 0, f"init failed:\n{r.output}"

    patches = _all_patches()
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        # ── ingest ────────────────────────────────────────────────────────────
        r = runner.invoke(main, ["ingest", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"ingest failed:\n{r.output}"
        assert (tmp_path / "data" / "local.duckdb").exists()

        # ── discover ──────────────────────────────────────────────────────────
        r = runner.invoke(main, ["discover", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"discover failed:\n{r.output}"
        watchlists = list((tmp_path / "outputs").rglob("discovered_watchlist.csv"))
        assert watchlists, "discover produced no discovered_watchlist.csv"
        df = pd.read_csv(watchlists[0])
        assert not df.empty, "discovered_watchlist.csv is empty"

        # ── score ─────────────────────────────────────────────────────────────
        r = runner.invoke(main, ["score", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"score failed:\n{r.output}"
        scoring_files = list((tmp_path / "outputs").rglob("scoring.json"))
        assert scoring_files, "score produced no scoring.json"
        scoring = json.loads(scoring_files[0].read_text())
        assert "scores" in scoring
        assert isinstance(scoring["scores"], list)
        assert len(scoring["scores"]) > 0

        # ── gold ──────────────────────────────────────────────────────────────
        r = runner.invoke(main, ["gold", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"gold failed:\n{r.output}"
        gold_files = list((tmp_path / "outputs").rglob("gold_regime.json"))
        band_files = list((tmp_path / "outputs").rglob("gold_band.yaml"))
        assert gold_files, "gold produced no gold_regime.json"
        assert band_files, "gold produced no gold_band.yaml"
        gold = json.loads(gold_files[0].read_text())
        assert "regime" in gold, f"gold_regime.json missing 'regime': {gold}"
        assert "score" in gold
        assert "tilt" in gold
        assert "zone" in gold
        assert gold["regime"] in ("range_bound", "uptrend", "downtrend")

        # ── allocate ──────────────────────────────────────────────────────────
        r = runner.invoke(main, ["allocate", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"allocate failed:\n{r.output}"
        alloc_files = list((tmp_path / "outputs").rglob("proposed_allocation.yaml"))
        assert alloc_files, "allocate produced no proposed_allocation.yaml"
        alloc = yaml.safe_load(alloc_files[0].read_text())
        assert "selected_instruments" in alloc
        assert "gold_tilt" in alloc
        assert "target_weights_per_class" in alloc

        # ── plan ──────────────────────────────────────────────────────────────
        r = runner.invoke(main, ["plan", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"plan failed:\n{r.output}"
        plan_files = list((tmp_path / "outputs").rglob("trade_plan.yaml"))
        assert plan_files, "plan produced no trade_plan.yaml"
        plan = yaml.safe_load(plan_files[0].read_text())
        assert "trades" in plan
        assert "mode" in plan
        assert plan["mode"] in ("build", "hybrid", "steady_state")

        # ── memo ──────────────────────────────────────────────────────────────
        r = runner.invoke(main, ["memo", "--repo-root", str(tmp_path)])
        assert r.exit_code == 0, f"memo failed:\n{r.output}"
        memo_files = list((tmp_path / "outputs").rglob("memo.md"))
        audit_files = list((tmp_path / "outputs").rglob("memo_audit.txt"))
        trace_files = list((tmp_path / "outputs").rglob("memo_traceability.json"))
        assert memo_files, "memo produced no memo.md"
        assert audit_files, "memo produced no memo_audit.txt"
        assert trace_files, "memo produced no memo_traceability.json"
        memo_text = memo_files[0].read_text()
        assert len(memo_text) > 10, "memo.md is empty"
        trace = json.loads(trace_files[0].read_text())
        assert "coverage_ratio" in trace
        assert "missing_count" in trace

        # ── ask ───────────────────────────────────────────────────────────────
        r = runner.invoke(main, ["ask", "--repo-root", str(tmp_path), "黄金标的如何？"])
        assert r.exit_code == 0, f"ask failed:\n{r.output}"
        assert len(r.output.strip()) > 0, "ask returned empty output"


# ─── test: irc run orchestrator (full pipeline in one call) ──────────────────

def test_e2e_irc_run_full_pipeline(tmp_path: Path) -> None:
    """irc run with no flags must produce all 7 stage outputs."""
    runner = CliRunner()

    r = runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    assert r.exit_code == 0, f"init failed:\n{r.output}"

    patches = _all_patches()
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        r = runner.invoke(main, ["run", "--repo-root", str(tmp_path)])

    assert r.exit_code == 0, f"irc run failed:\n{r.output}"
    assert "pipeline OK" in r.output

    out = tmp_path / "outputs"
    assert any(out.rglob("discovered_watchlist.csv")), "missing discovered_watchlist.csv"
    assert any(out.rglob("scoring.json")),             "missing scoring.json"
    assert any(out.rglob("gold_regime.json")),         "missing gold_regime.json"
    assert any(out.rglob("gold_band.yaml")),           "missing gold_band.yaml"
    assert any(out.rglob("proposed_allocation.yaml")), "missing proposed_allocation.yaml"
    assert any(out.rglob("trade_plan.yaml")),          "missing trade_plan.yaml"
    assert any(out.rglob("memo.md")),                  "missing memo.md"
    assert any(out.rglob("memo_audit.txt")),           "missing memo_audit.txt"
    assert any(out.rglob("memo_traceability.json")),   "missing memo_traceability.json"


# ─── test: irc run --only <stage> ────────────────────────────────────────────

def test_e2e_irc_run_only_stage(tmp_path: Path) -> None:
    """--only gold must run exactly that stage and produce gold_regime.json."""
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])

    # seed DuckDB with prices so gold_cmd can read them
    patches = _all_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        runner.invoke(main, ["ingest", "--repo-root", str(tmp_path)])

    with patches[5]:  # macro_fit not needed here, but keep patches clean
        r = runner.invoke(main, ["run", "--repo-root", str(tmp_path), "--only", "gold"])

    assert r.exit_code == 0, f"run --only gold failed:\n{r.output}"
    assert any((tmp_path / "outputs").rglob("gold_regime.json")), "missing gold_regime.json"
    # allocate / plan / memo must NOT have run
    assert not any((tmp_path / "outputs").rglob("proposed_allocation.yaml")), \
        "--only gold should not produce proposed_allocation.yaml"


# ─── test: irc run --from allocate (resumes mid-pipeline) ────────────────────

def test_e2e_irc_run_from_stage(tmp_path: Path) -> None:
    """--from allocate must skip ingest/discover/score/gold and run allocate→memo."""
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    today = _today()

    # Pre-seed the outputs that the early stages would produce
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    scoring_payload = {
        "scores": [
            {
                "instrument_id": "518880",
                "asset_class": "gold",
                "role": "core_gold",
                "composite_score": 72.0,
                "action": "buy",
                "conviction": "high",
                "completeness": 0.9,
                "factor_breakdown": {},
            }
        ]
    }
    (out_dir / "scoring.json").write_text(json.dumps(scoring_payload), encoding="utf-8")
    (out_dir / "gold_regime.json").write_text(
        json.dumps({"regime": "uptrend", "score": 78.0, "tilt": "overweight",
                    "zone": "normal", "vol_ratio": 1.2, "adx": 28.0,
                    "trend_sign": 1, "scenario": "strong_bull",
                    "scenario_triggers": []}),
        encoding="utf-8",
    )

    patches = _all_patches()
    with patches[6], patches[7], patches[8]:  # memo synthesizer, auditor, ask
        r = runner.invoke(main, ["run", "--repo-root", str(tmp_path), "--from", "allocate"])

    assert r.exit_code == 0, f"run --from allocate failed:\n{r.output}"
    assert "pipeline OK" in r.output

    out = tmp_path / "outputs"
    assert any(out.rglob("proposed_allocation.yaml")), "missing proposed_allocation.yaml"
    assert any(out.rglob("trade_plan.yaml")),          "missing trade_plan.yaml"
    assert any(out.rglob("memo.md")),                  "missing memo.md"
    # early-stage outputs must NOT exist (not produced by this run)
    assert not any(out.rglob("discovered_watchlist.csv")), \
        "--from allocate should not produce discovered_watchlist.csv"


# ─── test: unknown stage names are rejected ───────────────────────────────────

def test_e2e_irc_run_invalid_stage(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    r = runner.invoke(main, ["run", "--repo-root", str(tmp_path), "--only", "nonexistent"])
    assert r.exit_code != 0 or "ERROR" in r.output
