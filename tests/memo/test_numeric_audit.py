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
    an executable portfolio conclusion.

    Locks against the actual ``_SCORING_FOOTNOTE`` constant so that any future
    extension of the footnote (e.g. Item 003 added the 单次定投上限 /
    触发状态 explainer on 2026-05-26) is caught here before it halts the memo
    stage at the citation gate.
    """
    from irc.memo.numeric_audit import find_uncited_conclusions
    from irc.memo.picks_table import _SCORING_FOOTNOTE
    findings = find_uncited_conclusions(
        prose=_SCORING_FOOTNOTE,
        cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == [], f"footnote tripped audit: {findings}"


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
    `条件性减速定投` and structural pause_wait bucket enumerations like
    '5 个标的列入条件性减速定投或暂停加仓'. Both patterns describe how
    pause_wait/small_watch picks behave (not action recommendations), so
    any prose mention is exempt from `uncited_portfolio_conclusion`."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    for paraphrase in (
        "- 本期无 core_dca 候选，所有可执行标的均为 small_watch 且采用"
        "条件性减速定投，触发条件未满足时实际执行量为零。",
        "- 本期精选标的均为 small_watch，所有执行均为条件性减速定投；"
        "未触发第 7 节阈值时实际执行量为零。",
        "- 本期无 core_dca 候选，5 个标的列入条件性减速定投或暂停加仓；"
        "QDII 类标的因机会数据缺失全部暂缓执行。",
    ):
        findings = find_uncited_conclusions(
            prose=paraphrase,
            cited_map={},
            instrument_aliases={"519770": "519770"},
            constituent_aliases={},
            constituent_cited_map={},
        )
        assert findings == [], f"unexpected finding on paraphrase: {paraphrase!r}"


def test_find_uncited_conclusions_multi_instrument_paragraph_accepts_co_mentioned_citations() -> None:
    """Regression: 2026-05-25 memo halted on a single gold-ETF summary
    paragraph mentioning all 5 ETFs (518880, 159937, 159934, 518800,
    518850) with one citation per ETF. Each citation correctly resolves
    to its own ETF; the audit must NOT flag them as
    `wrong_instrument_citation` for the OTHER 4 ETFs in the same para.
    Only legitimate per-instrument dual-leg gaps should be reported."""
    from unittest.mock import MagicMock

    from irc.memo.numeric_audit import find_uncited_conclusions

    def make_meta(scope: str = "instrument", kind: str = "data"):
        m = MagicMock()
        m.scope = scope
        m.citation_kind = kind
        return m

    # 5 instruments, each with its own data marker. No info markers (typical
    # for gold ETFs whose info-leg is empty) — so `uncited_conclusion` is
    # still expected per-instrument, but `wrong_instrument_citation` must NOT
    # fire for co-mentioned siblings.
    cited_map = {
        "518880": {"3909fc27211e21a9": make_meta()},
        "159937": {"ecf5a0b85e1e94cf": make_meta()},
        "159934": {"558748cbe683f023": make_meta()},
        "518800": {"34667ecabf916402": make_meta()},
        "518850": {"86318c6b51ebd8c2": make_meta()},
    }
    prose = (
        "证据池内 5 只黄金 ETF（518880、159937、159934、518800、518850）"
        "状态分桶均为 expensive 或 very_expensive，热度 normal，长期逻辑 intact，"
        "机会面 pause_wait [ref:3909fc27211e21a9] [ref:ecf5a0b85e1e94cf] "
        "[ref:558748cbe683f023] [ref:34667ecabf916402] [ref:86318c6b51ebd8c2]"
        "；按规则全部暂停加仓。"
    )
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map=cited_map,
        instrument_aliases={iid: iid for iid in cited_map},
        constituent_aliases={},
        constituent_cited_map={},
    )
    # No wrong_instrument_citation findings allowed (siblings co-mentioned)
    wrong = [f for f in findings if f.kind == "wrong_instrument_citation"]
    assert wrong == [], f"unexpected wrong_instrument_citation findings: {wrong}"


def test_find_uncited_conclusions_ignores_bucket_summary_pause_aggregations() -> None:
    """Regression: 2026-05-25 memo halted on the gold-ETF section header
    '**黄金ETF持仓**（本期全部暂停加仓）：'. Bucket-summary aggregations
    ('本期全部暂停加仓', '均暂停加仓', '全部暂停加仓') are factual statistics
    of pause_wait bucket membership, not action recommendations."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    for header in (
        "**黄金ETF持仓**（本期全部暂停加仓）：",
        "- CN ETF（本期均暂停加仓）：",
        "- 当前精选：全部暂停加仓。",
    ):
        findings = find_uncited_conclusions(
            prose=header,
            cited_map={},
            instrument_aliases={"519770": "519770"},
            constituent_aliases={},
            constituent_cited_map={},
        )
        assert findings == [], f"unexpected finding on header: {header!r}"


def test_find_uncited_conclusions_ignores_section_header_rule_based_pause() -> None:
    """Regression: 2026-05-25 memo halted on the gold-ETF section header
    '- 黄金 ETF 状态分布（均按规则暂停加仓）：'. This is a meta-description
    of what the pause_wait rule does (labels), not an action
    recommendation. The line introduces per-ETF bullets that each carry
    their own citation, so the header itself need not."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    for header in (
        "- 黄金 ETF 状态分布（均按规则暂停加仓）：",
        "- CN ETF 估值分布（按规则暂停加仓）：",
        "- 持仓状态：依据规则暂停加仓。",
        "- 配置面：根据规则暂停加仓。",
    ):
        findings = find_uncited_conclusions(
            prose=header,
            cited_map={},
            instrument_aliases={"519770": "519770"},
            constituent_aliases={},
            constituent_cited_map={},
        )
        assert findings == [], f"unexpected finding on header: {header!r}"


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


def test_find_uncited_conclusions_does_not_bleed_markers_across_instrument_paragraphs() -> None:
    """Two adjacent `**{iid} {name}**:` paragraphs each carry their own
    dual-leg markers for different instruments. The previous paragraph's
    markers must NOT bleed into the next paragraph's scope and trigger
    spurious `wrong_instrument_citation` findings on the new instrument.

    Regression for 2026-05-28 memo gate block: 003318's supplementary
    disclosure was flagged for citations that only appeared in 519770's
    paragraph because `prev_markers` carried across the blank-line break.
    """
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "519770": {
            "aaaa1111aaaa1111": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="519770", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
            "bbbb2222bbbb2222": CitationMeta(
                scope="instrument", citation_kind="information",
                owner_instrument_id="519770", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
        "003318": {
            "cccc3333cccc3333": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="003318", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
            "dddd4444dddd4444": CitationMeta(
                scope="instrument", citation_kind="information",
                owner_instrument_id="003318", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    prose = (
        "**519770 交银优择回报灵活配置混合A**: 该基金状态偏紧，暂停加仓 "
        "[ref:aaaa1111aaaa1111] [ref:bbbb2222bbbb2222]\n"
        "\n"
        "**003318 景顺长城中证500行业中性低波动指数A**: 该基金状态偏紧，暂停加仓 "
        "[ref:cccc3333cccc3333] [ref:dddd4444dddd4444]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={
            "519770": "519770",
            "003318": "003318",
            "交银优择回报灵活配置混合A": "519770",
            "景顺长城中证500行业中性低波动指数A": "003318",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" not in kinds, (
        f"prev_markers bleed across instrument paragraphs: {findings!r}"
    )


# ── 2026-06-01 memo gate block — substring-alias crosstalk + disclosure owner ──


def test_instrument_alias_hits_suppresses_substring_name_alias() -> None:
    """A shorter fund name that is a substring of a longer fund name must not
    produce a phantom hit for the shorter instrument inside the longer one's
    row. `国债ETF国泰` (511010) ⊂ `十年国债ETF国泰` (511260)."""
    from irc.memo.numeric_audit import _instrument_alias_hits
    aliases = {
        "国债ETF国泰": "511010",
        "十年国债ETF国泰": "511260",
        "511260": "511260",
        "511010": "511010",
    }
    # A block naming only 511260 must not also hit 511010 via the substring.
    assert _instrument_alias_hits(
        "511260 十年国债ETF国泰 暂停加仓", aliases,
    ) == {"511260"}
    # A standalone mention of the shorter name still hits 511010.
    assert _instrument_alias_hits(
        "511010 国债ETF国泰 暂停加仓", aliases,
    ) == {"511010"}
    # Both standalone in one block → both hit.
    assert _instrument_alias_hits(
        "十年国债ETF国泰 与 国债ETF国泰 同列", aliases,
    ) == {"511260", "511010"}


def test_find_uncited_conclusions_substring_name_alias_does_not_crosstalk() -> None:
    """Regression (2026-06-01 memo gate block): 511010's name 国债ETF国泰 is a
    substring of 511260's name 十年国债ETF国泰. Auditing the 511260 picks-table
    row (which carries only 511260's own dual-leg markers) must NOT raise a
    spurious `uncited_conclusion` for 511010."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions

    def _meta(iid, kind):
        return CitationMeta(
            scope="instrument", citation_kind=kind,
            owner_instrument_id=iid, asset_class="cn_bond_fund",
            parent_fund_id=None, constituent_key=None,
        )

    cited = {
        "511260": {
            "b45ea84068346d23": _meta("511260", "data"),
            "31f2345be4ca3241": _meta("511260", "information"),
            "de5e66233a637b7f": _meta("511260", "information"),
        },
        "511010": {
            "4b03af24151fe798": _meta("511010", "data"),
            "6c6fb36b7f94be53": _meta("511010", "information"),
            "be4aa4a6ad2dd984": _meta("511010", "information"),
        },
    }
    prose = (
        "| 代码 | 名称 | 本期行动 | 证据 |\n"
        "|---|---|---|---|\n"
        "| 511260 | 十年国债ETF国泰 | 暂停加仓 | "
        "[ref:b45ea84068346d23] [ref:31f2345be4ca3241] [ref:de5e66233a637b7f] |\n"
        "| 511010 | 国债ETF国泰 | 暂停加仓 | "
        "[ref:4b03af24151fe798] [ref:6c6fb36b7f94be53] [ref:be4aa4a6ad2dd984] |\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={
            "511260": "511260", "十年国债ETF国泰": "511260",
            "511010": "511010", "国债ETF国泰": "511010",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert findings == [], f"substring alias crosstalk: {findings!r}"


def test_find_uncited_conclusions_disclosure_header_resolves_multi_owner_constituent() -> None:
    """Regression (2026-06-01 memo gate block): the 各标的补充披露 subsection
    renders a per-instrument bold header `**519770 ...**` on its own line,
    followed by a separate bullet that names a multi-owner holding
    (中际旭创 / 300308, held by 12 funds) WITHOUT repeating the fund code. The
    header establishes the owner context, so the constituent must resolve to
    519770 and pass its dual-leg check — NOT raise
    `ambiguous_constituent_reference`."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions

    constituent_cited = {
        "519770": {
            "300308": {
                "5d61abbf42c6af35": CitationMeta(
                    scope="constituent", citation_kind="data",
                    owner_instrument_id="519770", asset_class="cn_equity_fund",
                    parent_fund_id="519770", constituent_key="300308",
                ),
                "66db55d2c4c968aa": CitationMeta(
                    scope="constituent", citation_kind="information",
                    owner_instrument_id="519770", asset_class="cn_equity_fund",
                    parent_fund_id="519770", constituent_key="300308",
                ),
            },
        },
    }
    owners = frozenset(
        (f, "300308") for f in (
            "000390", "001075", "001184", "001194", "001877", "005825",
            "006751", "008382", "008555", "018956", "163417", "519770",
        )
    )
    prose = (
        "### 各标的补充披露\n\n"
        "**519770 交银优择回报灵活配置混合A**\n"
        "- 底层持仓涉及中际旭创（300308.SZ）；该底层持仓正面表现不能独立作为加仓依据 "
        "[ref:5d61abbf42c6af35] [ref:66db55d2c4c968aa]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={
            "519770": "519770",
            "交银优择回报灵活配置混合A": "519770",
        },
        constituent_aliases={"300308": owners, "中际旭创": owners},
        constituent_cited_map=constituent_cited,
    )
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" not in kinds, findings
    assert "uncited_conclusion" not in kinds, findings
    assert findings == [], findings


def test_find_uncited_conclusions_section_heading_does_not_set_owner_context() -> None:
    """A `##`/`###` markdown heading that incidentally names one instrument must
    NOT become the disclosure-owner context for constituents later in that
    section — only per-instrument `**{iid} {name}**` disclosure headers do.
    Without this, an instrument named in a section title would leak across the
    whole section and mis-resolve (or under-flag) any multi-owner holding it
    happens to co-own. A bare, uncited constituent action with no per-instrument
    header must stay `ambiguous_constituent_reference`."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = (
        "## 黄金板块 519770 概览\n\n"
        "- 贵州茅台 加仓\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"519770": "519770"},
        constituent_aliases={
            "贵州茅台": frozenset({("519770", "600519"), ("163417", "600519")}),
        },
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" in kinds, findings


# ── Per-instrument (memo-wide) dual-leg — picks-table SAME-3 satisfies legs ──


def test_find_uncited_conclusions_instrument_dual_leg_satisfied_memo_wide() -> None:
    """Regression (2026-06-01 fresh-synthesis block on 518850): a disclosure
    paragraph that cites only an instrument's INFO leg must pass when the DATA
    leg (NAV snapshot) is cited elsewhere in the memo — the deterministic picks
    table already renders each pick's dual-leg (SAME-3), so narrative
    paragraphs need not re-cite the data leg."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions

    def _m(kind):
        return CitationMeta(
            scope="instrument", citation_kind=kind, owner_instrument_id="518850",
            asset_class="gold", parent_fund_id=None, constituent_key=None,
        )

    cited = {"518850": {
        "aaaaaaaaaaaaaaaa": _m("data"),         # NAV snapshot — table only
        "bbbbbbbbbbbbbbbb": _m("information"),   # fund announcement
    }}
    prose = (
        "| 代码 | 证据 |\n|---|---|\n"
        "| 518850 | [ref:aaaaaaaaaaaaaaaa] [ref:bbbbbbbbbbbbbbbb] |\n"
        "\n"
        "### 各标的补充披露\n\n"
        "- **518850 黄金ETF华夏**：估值=expensive，本次暂停加仓 [ref:bbbbbbbbbbbbbbbb]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={"518850": "518850", "黄金ETF华夏": "518850"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert [f for f in findings if f.kind == "uncited_conclusion"] == [], findings


def test_find_uncited_conclusions_memo_wide_still_flags_truly_uncited() -> None:
    """The memo-wide relaxation must NOT defang the gate: an instrument whose
    data+info legs appear NOWHERE in the memo is still flagged."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = "## CN ETF\n\n- 518850 黄金ETF华夏 本次暂停加仓\n"  # no [ref:...] anywhere
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map=_cited_map_single("518850"),  # legs exist but none are cited in prose
        instrument_aliases={"518850": "518850"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert any(f.kind == "uncited_conclusion" for f in findings), findings


def test_find_uncited_conclusions_constituent_dual_leg_memo_wide() -> None:
    """A constituent's data and info legs may be cited in different paragraphs
    of the disclosure section; the audit accepts the conclusion when both legs
    appear somewhere in the memo."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions

    def _m(kind):
        return CitationMeta(
            scope="constituent", citation_kind=kind, owner_instrument_id="519770",
            asset_class="cn_equity_fund", parent_fund_id="519770",
            constituent_key="300308",
        )

    constituent_cited = {"519770": {"300308": {
        "dddddddddddddddd": _m("data"),
        "eeeeeeeeeeeeeeee": _m("information"),
    }}}
    owners = frozenset({("519770", "300308"), ("000390", "300308")})
    prose = (
        "**519770 交银优择回报灵活配置混合A**\n"
        "- 中际旭创 季报数据已披露 [ref:dddddddddddddddd]\n"
        "- 中际旭创 正常定投 [ref:eeeeeeeeeeeeeeee]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"519770": "519770", "交银优择回报灵活配置混合A": "519770"},
        constituent_aliases={"300308": owners, "中际旭创": owners},
        constituent_cited_map=constituent_cited,
    )
    assert [f for f in findings if f.kind == "uncited_conclusion"] == [], findings


def test_find_uncited_conclusions_constituent_leg_ignores_non_publishable_scope() -> None:
    """A constituent's data leg carried by a non-publishable scope (e.g. a
    malformed `asset_class_macro` citation) must NOT satisfy the dual-leg —
    mirrors the instrument rule, defending against a producer emitting a
    wrong-scope constituent citation."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    constituent_cited = {"519770": {"300308": {
        "dddddddddddddddd": CitationMeta(
            scope="asset_class_macro", citation_kind="data",
            owner_instrument_id="519770", asset_class="cn_equity_fund",
            parent_fund_id="519770", constituent_key="300308",
        ),
        "eeeeeeeeeeeeeeee": CitationMeta(
            scope="constituent", citation_kind="information",
            owner_instrument_id="519770", asset_class="cn_equity_fund",
            parent_fund_id="519770", constituent_key="300308",
        ),
    }}}
    owners = frozenset({("519770", "300308"), ("000390", "300308")})
    prose = (
        "**519770 交银优择回报灵活配置混合A**\n"
        "- 中际旭创 正常定投 [ref:dddddddddddddddd] [ref:eeeeeeeeeeeeeeee]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"519770": "519770", "交银优择回报灵活配置混合A": "519770"},
        constituent_aliases={"300308": owners, "中际旭创": owners},
        constituent_cited_map=constituent_cited,
    )
    assert any(f.kind == "uncited_conclusion" for f in findings), findings
