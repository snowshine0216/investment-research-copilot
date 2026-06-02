from __future__ import annotations

import re
from pathlib import Path

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.report import render_report_md
from irc.narrative.schemas import NarrativeFundReport

REPO = Path(__file__).resolve().parents[2]
NARRATIVE_SRC = REPO / "src" / "irc" / "narrative"
_REF_RE = re.compile(r"\[ref:[0-9a-f]{16}\]")


def test_forbidden_jijgaikuang_indicator_absent() -> None:
    # CONTEXT.md "Static-profile invariant": 基金概况 forbidden in fetch code.
    for path in NARRATIVE_SRC.rglob("*.py"):
        assert "基金概况" not in path.read_text(encoding="utf-8"), path


def test_holdings_fetch_uses_only_portfolio_endpoint() -> None:
    src = (NARRATIVE_SRC / "holdings_fetch.py").read_text(encoding="utf-8")
    assert "fund_portfolio_hold_em" in src
    assert "基金概况" not in src


def test_rendered_analyze_report_satisfies_citation_regex() -> None:
    # Build a report from a REAL ThesisEvidence (16-hex citation_id computed in
    # __post_init__) — NOT a hand-injected string — and assert the rendered
    # md carries the locked `\[ref:[0-9a-f]{16}\]` marker (spec §5 acceptance).
    ev = ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary="601899 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id="000A", parent_fund_id=None, constituent_key=None,
    )
    rpt = NarrativeFundReport(
        instrument_id="000A", name_cn="有色基金",
        position_risk_level="high", risk_rationale="high — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=(), trim_triggers=(),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(), thesis_evidence=(ev,),
    )
    md = render_report_md("算力金属", (rpt,))
    matches = _REF_RE.findall(md)
    assert matches  # at least one citation rendered
    for m in matches:
        assert re.fullmatch(r"\[ref:[0-9a-f]{16}\]", m)
    assert f"[ref:{ev.citation_id}]" in md
