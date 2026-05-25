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


# ── Task 6: find_uncited_discipline_rows ──────────────────────────────────────

def _discipline_row(
    *, iid="005827", thesis_evidence=(), constituent_analyses=(),
):
    from irc.opportunity.types import DisciplineRow
    return DisciplineRow(
        instrument_id=iid,
        name_cn="X",
        asset_class="cn_equity_fund",
        theme=None,
        opportunity_state="core_dca",
        dca_action="normal_dca",
        risk_action="none",
        note_cn="",
        thesis_evidence=thesis_evidence,
        constituent_analyses=constituent_analyses,
        evidence_gaps=(),
        fetch_types_attempted=(),
    )


def test_find_uncited_discipline_rows_dual_leg_present_returns_empty() -> None:
    """AC4 (i) — both legs on row.thesis_evidence → no finding."""
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    data = _ev_for_pick(citation_kind="data", owner="005827")
    info = _ev_for_pick(citation_kind="information", owner="005827",
                        date="2024-04-16")
    row = _discipline_row(thesis_evidence=(data, info))
    assert find_uncited_discipline_rows((row,), {}) == []


def test_find_uncited_discipline_rows_missing_data_emits_finding() -> None:
    """AC4 (i) — info-only → missing data."""
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    info = _ev_for_pick(citation_kind="information", owner="005827")
    row = _discipline_row(thesis_evidence=(info,))
    findings = find_uncited_discipline_rows((row,), {})
    assert any(f.kind == "missing_data_citation" for f in findings)


def test_find_uncited_discipline_rows_wrong_instrument_emits_finding() -> None:
    """AC4 (ii) — entry.owner_instrument_id != row.instrument_id is flagged."""
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    foreign_data = _ev_for_pick(citation_kind="data", owner="OTHER")
    foreign_info = _ev_for_pick(citation_kind="information", owner="OTHER",
                                date="2024-04-16")
    row = _discipline_row(thesis_evidence=(foreign_data, foreign_info))
    findings = find_uncited_discipline_rows((row,), {})
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds


def test_find_uncited_discipline_rows_constituent_parent_check() -> None:
    """AC4 (ii) — constituent-scoped entry must have parent_fund_id == row.instrument_id."""
    from irc.fundamentals.types import ThesisEvidence
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    bad_parent = ThesisEvidence(
        type="filing", source="src", url="https://x", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827",  # owner matches
        parent_fund_id="WRONG_PARENT",  # but parent doesn't
        constituent_key="600519",
        holding_weight_pct=None,
    )
    good_info = _ev_for_pick(citation_kind="information", owner="005827",
                             date="2024-04-16")
    row = _discipline_row(thesis_evidence=(bad_parent, good_info))
    findings = find_uncited_discipline_rows((row,), {})
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds


# ── Task 7: find_uncited_conclusions body tests ──────────────────────────────

_ACTIONABLE = "加仓"  # one of the 10 frozen keywords


def _cited_map_single(iid="005827", *, kinds=("data", "information")):
    """Build a CitedMap with one data and one information entry for `iid`."""
    from irc.opportunity.types import CitationMeta
    m = {}
    for i, k in enumerate(kinds):
        cid = f"{i:016x}"
        m.setdefault(iid, {})[cid] = CitationMeta(
            scope="instrument", citation_kind=k,
            owner_instrument_id=iid, asset_class="cn_equity_fund",
            parent_fund_id=None, constituent_key=None,
        )
    return m


def test_find_uncited_conclusions_empty_prose_returns_empty() -> None:
    """AC18 — empty/whitespace prose short-circuits regardless of other args."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    assert find_uncited_conclusions(
        prose="", cited_map={}, instrument_aliases={},
        constituent_aliases={}, constituent_cited_map={},
    ) == []
    assert find_uncited_conclusions(
        prose="   \n  ", cited_map={}, instrument_aliases={},
        constituent_aliases={}, constituent_cited_map={},
    ) == []


def test_find_uncited_conclusions_strict_empty_alias_check_raises() -> None:
    """AC17 — strict_empty_alias_check=True AND empty aliases AND non-empty
    prose → RuntimeError("empty instrument_aliases — D1c builder did not run")."""
    import pytest
    from irc.memo.numeric_audit import find_uncited_conclusions
    with pytest.raises(RuntimeError, match="empty instrument_aliases"):
        find_uncited_conclusions(
            prose="some prose 加仓",
            cited_map={},
            instrument_aliases={},
            constituent_aliases={},
            constituent_cited_map={},
            strict_empty_alias_check=True,
        )


def test_find_uncited_conclusions_default_strict_false_no_raise() -> None:
    """AC17 — default strict_empty_alias_check=False preserves item 007's
    all-gapped pipeline-state semantic: returns [] without raising."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    result = find_uncited_conclusions(
        prose="some prose 加仓",
        cited_map={},
        instrument_aliases={},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert result == []


def test_find_uncited_conclusions_uncited_conclusion_emitted() -> None:
    """AC8 (a) — paragraph mentions instrument + actionable keyword but has
    no [ref:...] marker resolving to that instrument."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = f"## CN权益基金\n\n易方达蓝筹精选 (005827) {_ACTIONABLE}\n"
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map=_cited_map_single("005827"),
        instrument_aliases={
            "005827": "005827",
            "易方达蓝筹精选": "005827",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "uncited_conclusion" in kinds


def test_find_uncited_conclusions_with_dual_leg_markers_passes() -> None:
    """AC8 — paragraph with both data + information markers for the
    referenced instrument → no finding."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = _cited_map_single("005827")
    data_id, info_id = sorted(cited["005827"].keys())
    prose = (
        f"## CN权益基金\n\n"
        f"易方达蓝筹精选 (005827) {_ACTIONABLE} "
        f"[ref:{data_id}] [ref:{info_id}]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={
            "005827": "005827", "易方达蓝筹精选": "005827",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "uncited_conclusion" not in kinds


def test_find_uncited_conclusions_audits_markdown_table_rows_independently() -> None:
    """A picks table is one markdown block, but each row carries citations for
    a different instrument. The prose auditor must not pool markers across
    table rows and then report wrong-instrument citations."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "A001": {
            "aaaaaaaaaaaaaaaa": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="A001", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
            "bbbbbbbbbbbbbbbb": CitationMeta(
                scope="instrument", citation_kind="information",
                owner_instrument_id="A001", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
        "B002": {
            "cccccccccccccccc": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="B002", asset_class="cn_bond_fund",
                parent_fund_id=None, constituent_key=None,
            ),
            "dddddddddddddddd": CitationMeta(
                scope="instrument", citation_kind="information",
                owner_instrument_id="B002", asset_class="cn_bond_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    prose = (
        "| 代码 | 本期行动 | 证据 |\n"
        "|---|---|---|\n"
        "| A001 | 减速定投 | [ref:aaaaaaaaaaaaaaaa] [ref:bbbbbbbbbbbbbbbb] |\n"
        "| B002 | 减速定投 | [ref:cccccccccccccccc] [ref:dddddddddddddddd] |\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={"A001": "A001", "B002": "B002"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_raw_evidence_appendix() -> None:
    """The raw evidence appendix is a traceability dump, not synthesized prose.
    It intentionally contains many instruments and refs in one block."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "A001": {
            "aaaaaaaaaaaaaaaa": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="A001", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
            "bbbbbbbbbbbbbbbb": CitationMeta(
                scope="instrument", citation_kind="information",
                owner_instrument_id="A001", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    prose = (
        "## 附录·原始证据 (Raw Evidence)\n\n"
        "- B002 暂停加仓 [ref:aaaaaaaaaaaaaaaa] [ref:bbbbbbbbbbbbbbbb]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={"B002": "B002"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_wrong_instrument_citation() -> None:
    """AC8 (b) — marker resolves to a different owner_instrument_id."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "OTHER_FUND": {
            "deadbeefdeadbeef": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="OTHER_FUND", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    prose = (
        f"## CN权益基金\n\n"
        f"易方达蓝筹精选 (005827) {_ACTIONABLE} [ref:deadbeefdeadbeef]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={
            "005827": "005827", "易方达蓝筹精选": "005827",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds


def test_find_uncited_conclusions_ambiguous_constituent_reference() -> None:
    """AC8 (e) + AC19 — constituent resolves to ≥2 owner pairs with no
    section header → ambiguous_constituent_reference, no further checks
    in this paragraph for this constituent."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = f"贵州茅台 {_ACTIONABLE}\n"
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"x": "x"},  # non-empty to bypass empty-map case
        constituent_aliases={
            "贵州茅台": frozenset({
                ("005827", "600519"), ("163417", "600519"),
            }),
        },
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" in kinds


def test_find_uncited_conclusions_section_header_disambiguates_constituent() -> None:
    """AC19 — section header (### iid in name) resolves the multi-owner."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    constituent_cited = {
        "005827": {
            "600519": {
                "aaaaaaaaaaaaaaaa": CitationMeta(
                    scope="constituent", citation_kind="data",
                    owner_instrument_id="005827",
                    asset_class="cn_equity_fund",
                    parent_fund_id="005827", constituent_key="600519",
                ),
                "bbbbbbbbbbbbbbbb": CitationMeta(
                    scope="constituent", citation_kind="information",
                    owner_instrument_id="005827",
                    asset_class="cn_equity_fund",
                    parent_fund_id="005827", constituent_key="600519",
                ),
            },
        },
    }
    prose = (
        f"### 易方达蓝筹精选 (005827)\n\n"
        f"贵州茅台 {_ACTIONABLE} [ref:aaaaaaaaaaaaaaaa] [ref:bbbbbbbbbbbbbbbb]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={
            "贵州茅台": frozenset({
                ("005827", "600519"), ("163417", "600519"),
            }),
        },
        constituent_cited_map=constituent_cited,
    )
    # Resolved cleanly under the header context — no ambiguous finding,
    # no uncited finding (markers cover both legs).
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" not in kinds
    assert "uncited_conclusion" not in kinds


def test_find_uncited_conclusions_instrument_mention_disambiguates_constituent() -> None:
    """When a paragraph names both the parent fund and a multi-owner holding,
    the fund mention is enough context to resolve the constituent owner."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "519770": {
            "aaaaaaaaaaaaaaaa": CitationMeta(
                scope="constituent", citation_kind="data",
                owner_instrument_id="519770",
                asset_class="cn_equity_fund",
                parent_fund_id="519770", constituent_key="300308",
            ),
            "bbbbbbbbbbbbbbbb": CitationMeta(
                scope="constituent", citation_kind="information",
                owner_instrument_id="519770",
                asset_class="cn_equity_fund",
                parent_fund_id="519770", constituent_key="300308",
            ),
        },
    }
    constituent_cited = {
        "519770": {
            "300308": {
                "aaaaaaaaaaaaaaaa": CitationMeta(
                    scope="constituent", citation_kind="data",
                    owner_instrument_id="519770",
                    asset_class="cn_equity_fund",
                    parent_fund_id="519770", constituent_key="300308",
                ),
                "bbbbbbbbbbbbbbbb": CitationMeta(
                    scope="constituent", citation_kind="information",
                    owner_instrument_id="519770",
                    asset_class="cn_equity_fund",
                    parent_fund_id="519770", constituent_key="300308",
                ),
            },
        },
    }
    prose = (
        "519770 交银优择回报持有 300308，中际旭创作为底层证据支持观察，"
        f"{_ACTIONABLE} [ref:aaaaaaaaaaaaaaaa] [ref:bbbbbbbbbbbbbbbb]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={"519770": "519770", "交银优择回报": "519770"},
        constituent_aliases={
            "300308": frozenset({
                ("519770", "300308"), ("000390", "300308"),
            }),
        },
        constituent_cited_map=constituent_cited,
    )
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" not in kinds
    assert "uncited_conclusion" not in kinds


def test_find_uncited_conclusions_uncited_portfolio_conclusion() -> None:
    """AC8 (d) — actionable keyword + zero alias hits + zero markers →
    uncited_portfolio_conclusion."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = f"## CN权益基金\n\n本周 {_ACTIONABLE} 整个权益板块\n"
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "uncited_portfolio_conclusion" in kinds


def test_find_uncited_conclusions_ignores_execution_mode_labels() -> None:
    """`建仓模式` / `建仓方式` are labels, not standalone actionable conclusions."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "- 建仓模式：build（按节奏定投，不一次性投入）。\n"
            "- **519770 交银优择回报灵活配置混合A** | 建仓方式 small_account_anchor\n"
        ),
        cited_map=_cited_map_single("519770"),
        instrument_aliases={"519770": "519770", "交银优择回报灵活配置混合A": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_negated_add_position_language() -> None:
    """`不新增加仓` is cautionary language, not an add-position instruction."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中黄金 ETF（518880、159937、159934、518800、518850）状态多为 "
        "expensive 或 very_expensive，本期对黄金类标的不新增加仓，等待估值回落后再评估。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_not_included_for_add_position() -> None:
    """`不纳入加仓` is a negated add-position phrase."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中可见的境内黄金 ETF（518880、159937、159934、518800、518850）"
        "opportunity=pause_wait，本期均不纳入加仓。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_not_equivalent_to_add_position() -> None:
    """`不能等同于可加仓结论` warns against over-reading a score."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "- 511220、159650、014502 三只债券型标的估值分桶均为 "
        "evidence_insufficient，故综合分高低不能等同于\"便宜/可加仓\"结论。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "511220": "511220",
            "159650": "159650",
            "014502": "014502",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_summary_count_caution_language() -> None:
    """Portfolio count summaries are disclosure, not standalone execution
    instructions."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "- core_dca 桶为空，本期无强信号建仓标的；"
        "19 只 small_watch 仅触发条件性减速定投，18 只 pause_wait 暂停加仓。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={"518880": "518880"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_grouped_current_period_pause() -> None:
    """Grouped `本期暂停加仓` language is conservative disclosure; per-row
    action citations are enforced elsewhere."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中 5 只境内黄金 ETF（518880、159937、159934、518800、518850）"
        "状态均为 expensive 或 very_expensive，opportunity 一致为 pause_wait，本期暂停加仓。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_grouped_pause_wait_no_add_phrase() -> None:
    """Grouped `暂停加仓、等待回落，不新增仓位` language is conservative."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中五只黄金 ETF（518880、159937、159934、518800、518850）"
        "机会标签均为 pause_wait，本期对应行动为暂停加仓、等待回落，不新增仓位。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_scoring_footnote_definitions() -> None:
    """The picks-table footnote defines scoring and weight semantics; it is not
    an executable portfolio conclusion."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "> 综合分由内部多因子模型生成，仅作为辅助参考，不构成投资建议。"
        "表中权重均为上限约束（≤），非强制建仓目标；"
        "条件性减速定投在第7节触发条件未满足时实际执行量为零。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_not_prioritized_for_building() -> None:
    """`未将其纳入建仓优先级` is a negative/cautionary ranking statement."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中 5 只黄金 ETF（518880、159937、159934、518800、518850）"
        "均处 pause_wait，模型未将其纳入建仓优先级。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_wait_for_trigger_summary() -> None:
    """A portfolio-level trigger reminder is not a new uncited recommendation."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "- 本期精选 4 只可有限执行的标的均为 small_watch，"
        "须等待第 7 节触发条件（weekly_drawdown_4pct）满足后方启动减速定投，"
        "未触发时实际执行量为零。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_no_core_dca_execution_summary() -> None:
    """A no-core-DCA execution summary is conservative disclosure."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "- 精选池中无 core_dca 标的；执行行均为条件性减速定投或暂缓执行，"
        "触发条件未达成时实际执行量为零。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_not_in_pick_pool_add_phrase() -> None:
    """`不纳入精选池加仓` is a negated add-position phrase."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中 5 只黄金 ETF 状态分桶集中在 expensive/very_expensive，"
        "opportunity 一致为 pause_wait，与 regime=downtrend 信号方向一致；"
        "按既定规则不纳入精选池加仓，维持中性倾斜。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={"518880": "518880"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_insufficient_valuation_no_add_basis() -> None:
    """Missing valuation evidence means no add-position basis."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "- 511220、159650、014502 估值维度均为 evidence_insufficient，"
        "本期数据缺失，待补充；cost_grade 分别为 95、95、85，"
        "但在估值证据补齐前不得作为加仓依据。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "511220": "511220",
            "159650": "159650",
            "014502": "014502",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_no_core_dca_cadence_summary() -> None:
    """No-core-candidate cadence language is not an add-position instruction."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "- 机会面：core_dca=0，small_watch=19，pause_wait=18；"
        "本期无核心定投候选，建仓节奏以小仓位观察为主。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_no_lump_sum_build_mode() -> None:
    """A build-mode label that says no lump-sum build is not actionable."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose="- 建仓模式：build（节奏定投，不一次性建仓）。",
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_weight_cap_conditional_dca_with_spaces() -> None:
    """The weight-cap footnote can contain spaced section references."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "- 表中所有权重均为上限约束（≤），非强制建仓目标；"
            "条件性减速定投在第 7 节触发条件未满足时实际执行量为零。"
        ),
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_all_conditional_dca_zero_execution_summary() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "- 本期 core_dca 桶为空，所有可执行标的均为条件性减速定投"
            "（触发条件未满足时实际执行量为零），组合层面缺角明显。"
        ),
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_tldr_small_watch_conditional_dca_paraphrase() -> None:
    """Regression: 2026-05-25 memo halted on TL;DR bullets paraphrasing
    `条件性减速定投`. The phrase is a meta-description of how
    pause_wait/small_watch picks execute (not an action recommendation),
    so any prose mention is exempt from `uncited_portfolio_conclusion`."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    for paraphrase in (
        "- 本期无 core_dca 候选，所有可执行标的均为 small_watch 且采用"
        "条件性减速定投，触发条件未满足时实际执行量为零。",
        "- 本期精选标的均为 small_watch，所有执行均为条件性减速定投；"
        "未触发第 7 节阈值时实际执行量为零。",
    ):
        findings = find_uncited_conclusions(
            prose=paraphrase,
            cited_map={},
            instrument_aliases={"519770": "519770"},
            constituent_aliases={},
            constituent_cited_map={},
        )
        assert findings == [], f"unexpected finding on paraphrase: {paraphrase!r}"


def test_find_uncited_conclusions_ignores_grouped_gold_pause_threshold_rule() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "证据池中 5 只黄金 ETF（518880、159937、159934、518800、518850）"
        "均处于 pause_wait 桶。按规则阈值，估值或热度高于阈值时暂停加仓；"
        "本期黄金标的均未进入精选表。[ref:34667ecabf916402]"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_grouped_gold_not_in_add_phrase() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose="证据池覆盖的 5 只黄金 ETF 状态分布如下，均为 pause_wait，本期不列入加仓：",
        cited_map={},
        instrument_aliases={"518880": "518880"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_rule_based_pause_disclosure() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "- 负面信号（必须对等披露）：估值=very_expensive、热度=overheated，"
            "opportunity=small_watch；macro_fit=45、thesis_news=50，"
            "宏观契合度偏弱；规则判定暂停加仓。"
        ),
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_negated_fund_add_basis_with_constituent() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "基金披露的重仓相关个股 300308 收到券商研报覆盖（西南证券「增持」、"
            "华龙证券「买入」，均围绕 800G/算力相关业绩），属于券商单边观点，"
            "不构成本基金加仓依据。"
        ),
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={
            "300308": frozenset({
                ("519770", "300308"),
                ("000390", "300308"),
            }),
        },
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_non_building_target_disclaimer() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose="- 结论：在估值/热度回到规则阈值内之前，仅维持小仓位观察；权重上限 12.8% 为约束而非建仓目标。",
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_pause_wait_count_summary() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "- core_dca=0 意味着本期无满足核心定投条件的标的；"
            "19 只 small_watch 标的均以小仓位观察形式纳入，"
            "18 只 pause_wait 标的暂停加仓。"
        ),
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_grouped_gold_no_add_window_summary() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "- 黄金板块本期全部落入 pause_wait"
            "（518880、159937、159934、518800、518850 状态均为 expensive 或 very_expensive），"
            "无加仓窗口。"
        ),
        cited_map={},
        instrument_aliases={
            "518880": "518880",
            "159937": "159937",
            "159934": "159934",
            "518800": "518800",
            "518850": "518850",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_grouped_gold_rule_pause_with_pooled_refs() -> None:
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "518880": {
            "aaaaaaaaaaaaaaaa": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="518880", asset_class="gold",
                parent_fund_id=None, constituent_key=None,
            ),
        },
        "159937": {
            "bbbbbbbbbbbbbbbb": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="159937", asset_class="gold",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    findings = find_uncited_conclusions(
        prose=(
            "证据池覆盖的 5 只黄金 ETF（518880、159937）当前估值状态均为 "
            "expensive 或 very_expensive，opportunity 状态均为 pause_wait，"
            "依据规则暂停加仓 [ref:aaaaaaaaaaaaaaaa][ref:bbbbbbbbbbbbbbbb]。"
        ),
        cited_map=cited,
        instrument_aliases={"518880": "518880", "159937": "159937"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_restrained_add_summary() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose="- 机会面：core_dca=0，small_watch=19，pause_wait=18；本期无 core_dca 候选，加仓动作整体克制。",
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_grouped_gold_all_pause_with_pooled_refs() -> None:
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "518880": {
            "aaaaaaaaaaaaaaaa": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="518880", asset_class="gold",
                parent_fund_id=None, constituent_key=None,
            ),
        },
        "159937": {
            "bbbbbbbbbbbbbbbb": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="159937", asset_class="gold",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    findings = find_uncited_conclusions(
        prose=(
            "- 候选黄金 ETF 状态一致偏紧：518880 华安、159937 博时均为 "
            "expensive/normal/intact/strong，opportunity=pause_wait "
            "[ref:aaaaaaaaaaaaaaaa][ref:bbbbbbbbbbbbbbbb]。按规则阈值，"
            "本期黄金 ETF 全部暂停加仓，待估值或热度回到阈值内再评估。"
        ),
        cited_map=cited,
        instrument_aliases={"518880": "518880", "159937": "159937"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_conditional_dca_primary_not_triggered() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose="- 本期入选的精选标的全部为 small_watch，无 core_dca；执行动作以条件性减速定投为主，未触发即不执行。",
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == []


def test_find_uncited_conclusions_ignores_negated_fund_add_basis_with_particle() -> None:
    from irc.memo.numeric_audit import find_uncited_conclusions
    findings = find_uncited_conclusions(
        prose=(
            "卖方报告涉及的底层公司 300308.SZ 收到正面研究观点；"
            "该等正面研究观点不构成对本基金加仓的依据。"
        ),
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={
            "300308": frozenset({
                ("519770", "300308"),
                ("000390", "300308"),
            }),
        },
        constituent_cited_map={},
    )
    assert findings == []
