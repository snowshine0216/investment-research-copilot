from __future__ import annotations

from irc.memo.numeric_audit import (
    find_prose_data_contradictions,
    render_findings_block,
)


_EVIDENCE_EXPENSIVE_000105 = (
    "[000105 建信安心回报债券A] 状态=expensive/normal/intact/strong "
    "opportunity=core_dca score=51.4 cost_grade=85 risk=47 quality=87"
)

_EVIDENCE_CHEAP_000105 = (
    "[000105 建信安心回报债券A] 状态=cheap/normal/intact/strong "
    "opportunity=core_dca score=51.4 cost_grade=85 risk=47 quality=87"
)


def test_finds_cheap_prose_when_state_is_expensive():
    # The 2026-05-18 audit's exact failure mode.
    prose = (
        "信用债条目 000105 估值便宜，可优先承接本期增量资金。"
    )
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_EXPENSIVE_000105])
    assert len(findings) == 1
    f = findings[0]
    assert f.instrument_id == "000105"
    assert f.kind == "cheap_claim_vs_state"
    assert "估值便宜" in f.prose_excerpt


def test_no_finding_when_prose_agrees_with_state():
    prose = "信用债条目 000105 估值便宜，可优先承接本期增量资金。"
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_CHEAP_000105])
    assert findings == []


def test_finds_expensive_prose_when_state_is_cheap():
    prose = "000105 估值偏高，赔率不佳。"
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_CHEAP_000105])
    assert len(findings) == 1
    assert findings[0].kind == "expensive_claim_vs_state"


def test_no_finding_when_phrase_is_far_from_id():
    # 300 characters of separation — outside the 200-char proximity window.
    prose = ("000105 是信用债。" + "占位文字" * 80 + "估值便宜，可考虑配置。")
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_EXPENSIVE_000105])
    assert findings == []


def test_handles_evidence_without_instrument_id():
    # Gold-regime line has no [<id> ...] prefix; should be skipped silently.
    prose = "000105 估值便宜。"
    pool = ["[gold] regime=range_bound zone=normal tilt=neutral", _EVIDENCE_EXPENSIVE_000105]
    findings = find_prose_data_contradictions(prose, pool)
    assert len(findings) == 1


def test_render_findings_block_empty_returns_empty_string():
    assert render_findings_block([]) == ""


def test_render_findings_block_includes_kind_and_excerpt():
    findings = find_prose_data_contradictions(
        "000105 估值便宜。", [_EVIDENCE_EXPENSIVE_000105],
    )
    rendered = render_findings_block(findings)
    assert "自动数值审核" in rendered
    assert "000105" in rendered
    assert "cheap_claim_vs_state" in rendered


# ── Item 007 D1c — find_uncited_conclusions stub ──────────────────────────────


def test_find_uncited_conclusions_non_empty_aliases_does_not_raise() -> None:
    """Non-empty instrument_aliases must pass the guard. Empty
    constituent_aliases is permitted (a publishable run may have zero
    active funds)."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    result = find_uncited_conclusions(
        prose="some prose",
        cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    # Item 007 ships the stub; the body is item 009's territory.
    assert result == []


def test_find_uncited_conclusions_empty_aliases_with_empty_prose_returns_empty() -> None:
    """Regression — post-ship code-review surfaced that the original empty-map
    `RuntimeError` raised even for the LEGITIMATE all-gapped-row case (every
    opportunity row failed Policy B → `build_alias_maps(())` returned `({}, {})`).

    Discriminator: if prose is empty/whitespace, there's nothing to audit; return [].
    """
    from irc.memo.numeric_audit import find_uncited_conclusions
    assert find_uncited_conclusions(
        prose="",
        cited_map={},
        instrument_aliases={},
        constituent_aliases={},
        constituent_cited_map={},
    ) == []
    assert find_uncited_conclusions(
        prose="   \n\t  ",
        cited_map={},
        instrument_aliases={},
        constituent_aliases={},
        constituent_cited_map={},
    ) == []


def test_find_uncited_conclusions_empty_aliases_with_non_empty_prose_returns_empty() -> None:
    """Item 009 will tighten this branch (raise IFF aliases empty AND
    publishable_set is non-empty per the upstream pipeline state). Item 007's
    stub returns [] for the all-gapped case (the most defensive choice that
    doesn't crash the memo audit on legitimate empty-publishable runs).
    """
    from irc.memo.numeric_audit import find_uncited_conclusions
    assert find_uncited_conclusions(
        prose="some prose mentioning 005827",
        cited_map={},
        instrument_aliases={},
        constituent_aliases={},
        constituent_cited_map={},
    ) == []


# ── Task 5: find_missing_pick_citations ──────────────────────────────────────

def _ev_for_pick(
    *, citation_kind="data", owner="005827",
    constituent_key=None, scope="instrument", date="2024-04-15",
    url="https://x",
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type="filing", source="src", url=url, date=date,
        summary="x", scope=scope, citation_kind=citation_kind,
        owner_instrument_id=owner, parent_fund_id=None,
        constituent_key=constituent_key, holding_weight_pct=None,
    )


def _pick(iid="005827", citations=()):
    from irc.memo.picks_table import PickRow
    return PickRow(
        instrument_id=iid, name_cn="X", asset_class="cn_equity_fund",
        role="core", target_weight=0.1, composite_score=70.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        citations=citations,
    )


def test_find_missing_pick_citations_dual_leg_present_returns_empty() -> None:
    """AC2 — top-3 has both kinds → no finding."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    data = _ev_for_pick(citation_kind="data")
    info = _ev_for_pick(citation_kind="information", date="2024-04-16")
    pick = _pick(citations=(data, info))
    assert find_missing_pick_citations((pick,), {}) == []


def test_find_missing_pick_citations_empty_citations_flagged() -> None:
    """AC2 — empty citations tuple emits one `missing_pick_citations`."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    pick = _pick(citations=())
    findings = find_missing_pick_citations((pick,), {})
    assert len(findings) == 1
    assert findings[0].kind == "missing_pick_citations"
    assert findings[0].instrument_id == "005827"


def test_find_missing_pick_citations_data_only_flagged() -> None:
    """AC2 — data-only pick row → one finding for missing info leg."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    pick = _pick(citations=(_ev_for_pick(citation_kind="data"),))
    findings = find_missing_pick_citations((pick,), {})
    kinds = [f.kind for f in findings]
    # Either explicit "missing_information_citation" OR the general
    # "missing_pick_citations" — spec AC2 doesn't differentiate at the empty
    # vs single-leg level, but the wrapper kind for completely empty is
    # distinct. For single-leg, the test asserts the missing-info leg surfaces.
    assert any(k in {"missing_pick_citations", "missing_information_citation"}
               for k in kinds)


def test_find_missing_pick_citations_wrong_instrument_flagged() -> None:
    """AC2 — a citation pointing at a different owner_instrument_id is
    a provenance leak from select_citations → `wrong_instrument_citation`."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    leaked = _ev_for_pick(citation_kind="data", owner="OTHER_FUND")
    info = _ev_for_pick(citation_kind="information", date="2024-04-16")
    pick = _pick(iid="005827", citations=(leaked, info))
    findings = find_missing_pick_citations((pick,), {})
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds
