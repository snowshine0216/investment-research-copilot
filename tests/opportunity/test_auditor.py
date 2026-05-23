"""Item 009 D2a — opportunity-stage auditor unit tests.

Pure unit tests; no run_opportunity invocation here. Each AC pattern is
verified at the per-function level with hand-built OpportunityRow instances.
"""
from __future__ import annotations


def _ev(
    *, type_="filing", source="src", url="https://x", date="2024-04-15",
    summary="x", scope="instrument", citation_kind="data",
    owner="005827", parent=None, constituent_key=None, weight=None,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _row(
    *, iid="005827", thesis_evidence=(), contributing_dimensions=frozenset(),
    opportunity_state="core_dca", evidence_gaps=(),
    constituent_analyses=(),
):
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid,
        name_cn="X",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid,
            display_cn="X", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state=opportunity_state,
        opportunity_reason="",
        evidence_gaps=evidence_gaps,
        thesis_evidence=thesis_evidence,
        contributing_dimensions=contributing_dimensions,
        constituent_analyses=constituent_analyses,
    )


def test_find_uncited_opportunity_rows_dual_leg_present_returns_empty() -> None:
    """AC1 — both data + information legs present anywhere on row.thesis_evidence
    is the v1 structural-binding satisfier."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    data_ev = _ev(citation_kind="data")
    info_ev = _ev(citation_kind="information", url="https://x/info",
                  date="2024-04-16")
    row = _row(
        thesis_evidence=(data_ev, info_ev),
        contributing_dimensions=frozenset({"valuation", "thesis"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    assert findings == []


def test_find_uncited_opportunity_rows_missing_data_leg_emits_finding() -> None:
    """AC1 + AC6 — info-only row emits one `missing_data_citation`."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    info_ev = _ev(citation_kind="information")
    row = _row(
        thesis_evidence=(info_ev,),
        contributing_dimensions=frozenset({"valuation", "heat"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = [f.kind for f in findings]
    assert "missing_data_citation" in kinds
    # AC6: per-dimension informative prose_excerpt; uses first dim by sorted order.
    f = next(x for x in findings if x.kind == "missing_data_citation")
    assert f.prose_excerpt.startswith("dimension:")
    assert f.instrument_id == "005827"


def test_find_uncited_opportunity_rows_missing_information_leg_emits_finding() -> None:
    """AC1 + AC6 — data-only row emits one `missing_information_citation`."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    data_ev = _ev(citation_kind="data")
    row = _row(
        thesis_evidence=(data_ev,),
        contributing_dimensions=frozenset({"valuation"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = [f.kind for f in findings]
    assert "missing_information_citation" in kinds


def test_find_uncited_opportunity_rows_both_missing_emits_two_findings() -> None:
    """Empty thesis_evidence on a publishable row → two findings (both legs)."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    row = _row(
        thesis_evidence=(),
        contributing_dimensions=frozenset({"valuation"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["missing_data_citation", "missing_information_citation"]


def test_find_uncited_opportunity_rows_owner_mismatch_excluded() -> None:
    """Evidence whose owner_instrument_id != row.instrument_id is structurally
    excluded — the row is still uncited even if foreign-owned evidence exists."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    # Two rows so build_cited_map sees the right owners; only the second row
    # has its own evidence. The first row has zero owned evidence.
    other_row = _row(
        iid="OTHER_FUND",
        thesis_evidence=(_ev(citation_kind="data", owner="OTHER_FUND"),
                         _ev(citation_kind="information", owner="OTHER_FUND",
                             date="2024-04-18")),
    )
    row = _row(
        iid="005827", thesis_evidence=(_ev(citation_kind="information", owner="005827",
                                           date="2024-04-17"),),
        contributing_dimensions=frozenset({"valuation"}),
    )
    from irc.opportunity.citation_map import build_cited_map
    cited = build_cited_map((other_row, row))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = [f.kind for f in findings]
    assert "missing_data_citation" in kinds


def test_find_uncited_opportunity_rows_exclude_state_with_empty_dims_still_checked() -> None:
    """AC6 — an `exclude` row with empty contributing_dimensions still gets the
    row-level dual-leg check (excluding evidence still requires citation)."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    row = _row(
        thesis_evidence=(),
        contributing_dimensions=frozenset(),
        opportunity_state="exclude",
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    assert len(findings) >= 2  # both legs flagged


def test_find_uncited_opportunity_rows_empty_input_returns_empty() -> None:
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    assert find_uncited_opportunity_rows((), {}) == []


def test_find_uncited_opportunity_rows_returns_numeric_finding_type() -> None:
    """Return type contract — list[NumericFinding] from numeric_audit."""
    from irc.memo.numeric_audit import NumericFinding
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    row = _row(thesis_evidence=(), contributing_dimensions=frozenset({"thesis"}))
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    assert all(isinstance(f, NumericFinding) for f in findings)
