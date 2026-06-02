from __future__ import annotations

import json
import re

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.schemas import (
    NarrativeFundReport,
    OverlapResult,
    ShortlistRow,
)
from irc.narrative.report import (
    render_diagnostics_json,
    render_report_json,
    render_report_md,
    render_shortlist_json,
    render_shortlist_md,
)

_REF_RE = re.compile(r"\[ref:[0-9a-f]{16}\]")


def _row(iid: str) -> ShortlistRow:
    ov = OverlapResult(
        basket_weight_pct=22.5, overlap_count=3,
        matched_symbols=("600362", "601899"), industry_credit_symbols=("000060",),
    )
    return ShortlistRow(
        instrument_id=iid, name_cn=f"fund-{iid}",
        asset_class="cn_equity_fund", overlap=ov, holdings=(),
    )


def _evidence(iid: str) -> ThesisEvidence:
    """A real ThesisEvidence — citation_id is computed in __post_init__ (16 hex)."""
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary="601899 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def _report(iid: str, *, level: str = "elevated",
            evidence: tuple[ThesisEvidence, ...] = ()) -> NarrativeFundReport:
    return NarrativeFundReport(
        instrument_id=iid, name_cn=f"fund-{iid}",
        position_risk_level=level,  # type: ignore[arg-type]
        risk_rationale=f"{level} — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive", heat_state="overheated",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=("theme thesis moves to falsified",),
        trim_triggers=("valuation_state in [expensive, very_expensive]",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(), thesis_evidence=evidence,
    )


def test_shortlist_md_has_header_and_rows() -> None:
    md = render_shortlist_md("算力金属", (_row("A"), _row("B")))
    assert md.startswith("# ")
    assert "算力金属" in md
    assert "A" in md and "B" in md
    assert md.endswith("\n")


def test_shortlist_json_is_deterministic_and_parses() -> None:
    j1 = render_shortlist_json("算力金属", (_row("A"), _row("B")))
    j2 = render_shortlist_json("算力金属", (_row("A"), _row("B")))
    assert j1 == j2
    doc = json.loads(j1)
    assert doc["narrative"] == "算力金属"
    assert [r["instrument_id"] for r in doc["funds"]] == ["A", "B"]
    assert doc["funds"][0]["basket_weight_pct"] == 22.5


def test_diagnostics_json_lists_excluded_with_reason() -> None:
    j = render_diagnostics_json((("X", "fund-X", "no_published_holdings"),))
    doc = json.loads(j)
    assert doc["excluded"][0]["instrument_id"] == "X"
    assert doc["excluded"][0]["reason"] == "no_published_holdings"


def test_report_md_emits_ref_from_thesis_evidence() -> None:
    ev = _evidence("A")
    md = render_report_md("算力金属", (_report("A", evidence=(ev,)),))
    # Citation rendered from the REAL evidence id (16 hex), reusing report.py format.
    assert _REF_RE.search(md)
    assert f"[ref:{ev.citation_id}]" in md
    # the locked line shape: `- [ref:{id}] {type} · {source} · {date}`
    assert f"[ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}" in md


def test_report_md_renders_risk_and_action_fields() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=(_evidence("A"),)),))
    assert "elevated" in md
    assert "small_watch" in md        # opportunity_state
    assert "slow_dca" in md           # dca_action
    assert "trim_review" in md        # risk_action
    assert "weekly_light_monthly_full" in md  # review_cadence


def test_report_md_no_evidence_has_no_ref() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=()),))
    assert not _REF_RE.search(md)  # no citations when evidence is empty


def test_report_json_round_trips_states_and_evidence() -> None:
    ev = _evidence("A")
    doc = json.loads(render_report_json("算力金属", (_report("A", level="high",
                                                            evidence=(ev,)),)))
    fund = doc["funds"][0]
    assert fund["position_risk_level"] == "high"
    assert fund["opportunity_state"] == "small_watch"
    assert fund["risk_action"] == "trim_review"
    assert fund["thesis_evidence"][0]["citation_id"] == ev.citation_id
    assert fund["thesis_evidence"][0]["type"] == "filing"
