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


# ── Task 4: find_incomplete_constituent_analyses ──────────────────────────────

def _constituent(symbol, *, evidence=(), failure_reasons=()):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol,
        name_cn=symbol,
        weight_pct=5.0,
        evidence=evidence,
        failure_reasons=failure_reasons,
        one_line_view="",
    )


def test_find_incomplete_constituent_analyses_pure_failure_flagged() -> None:
    """AC5 + AC7 — evidence == () AND failure_reasons != () is fatal."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    bad = _constituent("600519", evidence=(), failure_reasons=("timeout",))
    row = _row(
        thesis_evidence=(_ev(citation_kind="data"), _ev(citation_kind="information", date="2024-04-17")),
        contributing_dimensions=frozenset({"thesis"}),
        constituent_analyses=(bad,),
    )
    findings = find_incomplete_constituent_analyses((row,))
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "constituent_pure_failure"
    assert f.instrument_id == "005827"
    assert "symbol=600519" in f.prose_excerpt
    assert "evidence=()" in f.evidence_excerpt
    assert "timeout" in f.evidence_excerpt


def test_find_incomplete_constituent_analyses_partial_success_not_flagged() -> None:
    """AC7 — partial-success (both fields non-empty) is NOT a violation.

    Policy B's per-holding data leg + top-half info quorum is the correct
    disposition; the auditor does not second-guess it."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    partial = _constituent(
        "600519",
        evidence=(_ev(citation_kind="data", constituent_key="600519",
                      scope="constituent", parent="005827"),),
        failure_reasons=("broker_report_missing",),
    )
    row = _row(constituent_analyses=(partial,))
    findings = find_incomplete_constituent_analyses((row,))
    assert findings == []


def test_find_incomplete_constituent_analyses_intact_not_flagged() -> None:
    """Intact constituent (failure_reasons == ()) does not appear."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    intact = _constituent(
        "600519",
        evidence=(_ev(citation_kind="data", constituent_key="600519",
                      scope="constituent", parent="005827"),),
        failure_reasons=(),
    )
    row = _row(constituent_analyses=(intact,))
    assert find_incomplete_constituent_analyses((row,)) == []


def test_find_incomplete_constituent_analyses_returns_one_per_failing_constituent() -> None:
    """AC7 — one finding per pure-failure constituent, across multiple rows."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    bad1 = _constituent("600519", failure_reasons=("e1",))
    bad2 = _constituent("300750", failure_reasons=("e2",))
    intact = _constituent("601318",
                          evidence=(_ev(constituent_key="601318",
                                        scope="constituent", parent="005827"),),
                          failure_reasons=())
    row = _row(constituent_analyses=(bad1, bad2, intact))
    findings = find_incomplete_constituent_analyses((row,))
    symbols = sorted(f.prose_excerpt for f in findings)
    assert symbols == ["symbol=300750", "symbol=600519"]


def test_find_incomplete_constituent_analyses_foreign_heavy_exempt_not_flagged() -> None:
    """Policy B rule 2.5 (foreign-heavy) publishes the fund on fund-level
    NAV+announcement evidence and short-circuits ALL per-holding checks
    (ADR 0003 §7). A pure-failure foreign constituent (e.g. HK-listed 00998,
    whose CN filings pipeline is structurally unreachable) on such a row is
    therefore EXPECTED, not a programming bug — so it must be exempt when the
    fund's instrument_id is in `foreign_heavy_exempt_ids`."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    bad = _constituent(
        "00998", evidence=(),
        failure_reasons=("filing_empty:00998", "hk_news_fetch_failed:00998"),
    )
    row = _row(iid="006809", constituent_analyses=(bad,))
    # Baseline: without the exemption the gate still fires (no regression).
    assert len(find_incomplete_constituent_analyses((row,))) == 1
    # Exempt: the rule-2.5 publishable fund's pure-failures are tolerated.
    findings = find_incomplete_constituent_analyses(
        (row,), foreign_heavy_exempt_ids=frozenset({"006809"}),
    )
    assert findings == []


def test_find_incomplete_constituent_analyses_exemption_is_per_instrument() -> None:
    """Exemption applies ONLY to listed instrument_ids; a non-exempt fund's
    pure-failure constituent still produces a fatal finding even when another
    fund in the same batch is exempt."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    foreign = _row(
        iid="006809",
        constituent_analyses=(_constituent("00998", failure_reasons=("filing_empty:00998",)),),
    )
    domestic = _row(
        iid="005827",
        constituent_analyses=(_constituent("600519", failure_reasons=("timeout",)),),
    )
    findings = find_incomplete_constituent_analyses(
        (foreign, domestic), foreign_heavy_exempt_ids=frozenset({"006809"}),
    )
    assert [f.prose_excerpt for f in findings] == ["symbol=600519"]
    assert all(f.instrument_id == "005827" for f in findings)


def test_find_incomplete_constituent_analyses_exemption_is_whole_row() -> None:
    """DELIBERATE wholesale behavior (ADR 0003 §7): rule 2.5 publishes the fund
    on fund-level evidence and bypasses ALL per-holding checks, so an exempt
    row's pure-failures are tolerated regardless of constituent exchange —
    BOTH a foreign (HK 00998) and a CN (600519) pure-failure on the same
    rule-2.5 fund are exempt. The CN failure is not silently lost: it still
    renders as `❌` in the `## 持仓明细` appendix. Pinned so the broadness is a
    visible, intentional design choice, not an accidental over-exemption."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    row = _row(
        iid="006809",
        constituent_analyses=(
            _constituent("00998", failure_reasons=("filing_empty:00998",)),
            _constituent("600519", failure_reasons=("filing_fetch_failed:600519",)),
        ),
    )
    # Without the exemption BOTH pure-failures are fatal findings.
    assert len(find_incomplete_constituent_analyses((row,))) == 2
    # With 006809 exempt (rule-2.5 publishable) the whole row is skipped.
    findings = find_incomplete_constituent_analyses(
        (row,), foreign_heavy_exempt_ids=frozenset({"006809"}),
    )
    assert findings == []
