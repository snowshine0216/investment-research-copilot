from __future__ import annotations

import json
import re
from dataclasses import replace

from irc.fundamentals.types import ConstituentAnalysis, ThesisEvidence
from irc.narrative.schemas import (
    NarrativeFundReport,
    OverlapResult,
    ProductMetrics,
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


# --- Task 1: schema tests ---

def test_product_metrics_defaults_are_none() -> None:
    pm = ProductMetrics()
    assert pm.expense_ratio is None
    assert pm.aum_cny is None
    assert pm.manager_tenure_years is None
    assert pm.tracking_error is None


def test_narrative_fund_report_new_fields_default_empty() -> None:
    # Existing _report() constructor must still be valid (no new required args).
    r = _report("A")
    assert r.constituent_analyses == ()
    assert r.product_metrics is None


# --- Task 3: AC1/AC2 — inline evidence bullet gains · {summary} ---

def test_report_md_inline_bullet_has_summary_suffix() -> None:
    ev = _evidence("A")  # summary = "601899 2026Q1 财报已披露（口径未核实）"
    md = render_report_md("算力金属", (_report("A", evidence=(ev,)),))
    assert (
        f"- [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date} · {ev.summary}"
        in md
    )


def test_report_md_inline_caps_at_three_with_summary() -> None:
    evs = tuple(
        ThesisEvidence(
            type="news", source=f"src{i}", url="", date=f"2026-03-0{i}",
            summary=f"headline-{i}", scope="instrument", citation_kind="information",
            owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
        )
        for i in range(1, 6)  # 5 records
    )
    md = render_report_md("算力金属", (_report("A", evidence=evs),))
    # Inline cell still capped at 3 distinct inline bullets.
    inline = md.split("证据 / evidence:")[1].split("\n\n")[0]
    assert inline.count("[ref:") == 3


# --- Task 4: AC4/AC5 — footnote appendix resolves every inline [ref:hex] ---

def _multi(iid: str) -> tuple[ThesisEvidence, ...]:
    return tuple(
        ThesisEvidence(
            type="news", source=f"src{i}", url=("" if i % 2 else f"http://u/{i}"),
            date=f"2026-03-0{i}", summary=f"headline-{i}",
            scope="instrument", citation_kind="information",
            owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
        )
        for i in range(1, 6)
    )


def test_report_md_every_inline_ref_resolves_to_footnote() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=_multi("A")),))
    block = md.split("## A ")[1]
    inline_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", block))
    # Footnote section header present + each inline id has exactly one footnote line.
    assert "证据明细" in block
    for cid in inline_ids:
        footnote = [ln for ln in block.splitlines()
                    if ln.startswith(f"[ref:{cid}]")]
        assert len(footnote) == 1, f"{cid} resolved {len(footnote)} times"


def test_report_md_footnote_table_is_byte_identical_two_calls() -> None:
    reports = (_report("A", evidence=_multi("A")),)
    assert render_report_md("算力金属", reports) == render_report_md("算力金属", reports)


def test_report_md_footnotes_sorted_by_citation_id_asc() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=_multi("A")),))
    footnotes = [ln[len("[ref:"):len("[ref:") + 16]
                 for ln in md.splitlines() if ln.startswith("[ref:")]
    assert footnotes == sorted(footnotes)


def test_report_md_no_evidence_has_no_footnote_table() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=()),))
    assert "证据明细" not in md
    assert not _REF_RE.search(md)


# --- Task 5: AC3 — per-constituent appendix prose ---

def _ca(symbol: str, weight: float, *, evidence=(), failures=(),
        oneline="prose", audit=()) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=f"co-{symbol}", weight_pct=weight,
        evidence=evidence, failure_reasons=failures,
        one_line_view=oneline, audit_errors=audit,
    )


def _report_with_constituents(iid: str, cas) -> NarrativeFundReport:
    base = _report(iid, evidence=tuple(e for c in cas for e in c.evidence))
    return replace(base, constituent_analyses=cas)


def test_report_md_appendix_renders_constituent_one_line_view() -> None:
    ev = _evidence("601899")
    cas = (_ca("601899", 8.5, evidence=(ev,), oneline="紫金矿业 营收 +20%"),)
    md = render_report_md("算力金属", (_report_with_constituents("A", cas),))
    block = md.split("## A ")[1]
    assert "601899 co-601899 (权重 8.5%): 紫金矿业 营收 +20%" in block
    assert f"[ref:{ev.citation_id}]" in block  # constituent refs present


def test_report_md_appendix_constituent_failure_only_no_oneline() -> None:
    cas = (_ca("000060", 3.0, evidence=(), failures=("no_filing",), oneline="X"),)
    md = render_report_md("算力金属", (_report_with_constituents("A", cas),))
    block = md.split("## A ")[1]
    assert "000060 co-000060 (权重 3.0%): ❌ no_filing" in block
    assert "X" not in block.split("证据明细")[0]  # no fabricated one_line_view


def test_report_md_passive_fund_has_no_constituent_block_but_has_footnotes() -> None:
    md = render_report_md("黄金", (_report("G", evidence=(_evidence("G"),)),))
    block = md.split("## G ")[1]
    assert "（权重" not in block  # no per-constituent bullets
    assert "证据明细" in block    # footnotes still render
