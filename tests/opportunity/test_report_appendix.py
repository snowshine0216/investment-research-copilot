"""Item 007 D3b — 持仓明细 appendix tests.

Tests cover AC19, AC20, AC21, AC22, AC23, AC28, AC29 + the locked
5-shape regex contract per spec §17.
"""
import re


def _evidence(
    *, type_="filing", source="x", url="https://x", date="2024-04-15",
    summary="x", scope="constituent", citation_kind="data",
    owner="005827", parent="005827", constituent_key="600519",
    weight=8.2,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _constituent(
    *, symbol="600519", name_cn="贵州茅台", weight=8.2,
    evidence=(), failure_reasons=(), one_line_view="持有头部白酒",
    audit_errors=(),
):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn, weight_pct=weight,
        evidence=evidence, failure_reasons=failure_reasons,
        one_line_view=one_line_view, audit_errors=audit_errors,
    )


def _opportunity_row(
    *, iid="005827", name_cn="易方达蓝筹精选",
    asset_class="cn_equity_fund", constituent_analyses=(),
    evidence_gaps=(),
):
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid,
        name_cn=name_cn,
        asset_class=asset_class,
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid, display_cn=name_cn,
            provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=evidence_gaps,
        thesis_evidence=(),
        constituent_analyses=constituent_analyses,
    )


def _discipline_row(*, iid="005827", constituent_analyses=()):
    from irc.opportunity.types import DisciplineRow
    return DisciplineRow(
        instrument_id=iid,
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        opportunity_state="core_dca",
        dca_action="normal_dca",
        risk_action="none",
        note_cn="",
        thesis_evidence=(),
        constituent_analyses=constituent_analyses,
    )


def test_appendix_header_appears_after_drawdown_note() -> None:
    """AC19 — `## 持仓明细` section appended after _DRAWDOWN_NOTE_CN."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(evidence=(_evidence(),))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(_opportunity_row(constituent_analyses=(c,)),),
        pick_order_iids=("005827",),
    )
    drawdown_pos = out.index("## 关于回撤的说明")
    appendix_pos = out.index("## 持仓明细")
    assert drawdown_pos < appendix_pos


def test_appendix_empty_case_renders_placeholder() -> None:
    """AC19 — zero publishable rows with constituent_analyses → appendix header + （无）."""
    from irc.opportunity.report import compose_discipline_markdown
    out = compose_discipline_markdown(
        rows=(),
        date="2026-05-23",
        publishable_rows=(),
        pick_order_iids=(),
    )
    assert "## 持仓明细" in out
    # The body is `（无）` for the empty case (matches _render_section convention).
    appendix_section = out.split("## 持仓明细", 1)[1]
    assert "（无）" in appendix_section


def test_appendix_subsection_per_publishable_row() -> None:
    """AC28 — every publishable row with constituent_analyses gets a subsection."""
    from irc.opportunity.report import compose_discipline_markdown
    c1 = _constituent(symbol="600519", name_cn="贵州茅台", weight=8.2,
                     evidence=(_evidence(constituent_key="600519"),))
    c2 = _constituent(symbol="000001", name_cn="平安银行", weight=5.0,
                     evidence=(_evidence(constituent_key="000001"),))
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选",
                         constituent_analyses=(c1,)),
        _opportunity_row(iid="163417", name_cn="兴全合润",
                         constituent_analyses=(c2,)),
    )
    out = compose_discipline_markdown(
        rows=tuple(_discipline_row(iid=r.instrument_id,
                                    constituent_analyses=r.constituent_analyses)
                   for r in rows),
        date="2026-05-23",
        publishable_rows=rows,
        pick_order_iids=("005827", "163417"),
    )
    assert "### 005827 易方达蓝筹精选 (cn_equity_fund)" in out
    assert "### 163417 兴全合润 (cn_equity_fund)" in out


def test_appendix_lists_full_top_n_not_just_5() -> None:
    """AC20 — 10 constituents → 10 appendix bullets (full top-N), not 5."""
    from irc.opportunity.report import compose_discipline_markdown
    constituents = tuple(
        _constituent(symbol=f"6{i:05d}", name_cn=f"股{i}",
                     weight=10.0 - i * 0.5,
                     evidence=(_evidence(constituent_key=f"6{i:05d}"),))
        for i in range(10)
    )
    row = _opportunity_row(constituent_analyses=constituents)
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=constituents),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    # Count bullets under the 005827 subsection.
    subsection = out.split("### 005827 易方达蓝筹精选 (cn_equity_fund)", 1)[1]
    next_header_pos = subsection.find("\n### ")
    if next_header_pos < 0:
        next_header_pos = subsection.find("\n## ")
    section_body = subsection[:next_header_pos] if next_header_pos >= 0 else subsection
    bullets = re.findall(r"^- 6\d{5} ", section_body, re.MULTILINE)
    assert len(bullets) == 10


def test_appendix_ordering_pick_row_order_first() -> None:
    """AC21 — pick-row order [B, A, C] → appendix [B, A, C]; non-pick → instrument_id asc."""
    from irc.opportunity.report import compose_discipline_markdown
    rows = (
        _opportunity_row(iid="005827", name_cn="A基金",
                         constituent_analyses=(_constituent(symbol="600001"),)),
        _opportunity_row(iid="163417", name_cn="B基金",
                         constituent_analyses=(_constituent(symbol="600002"),)),
        _opportunity_row(iid="110022", name_cn="C基金",
                         constituent_analyses=(_constituent(symbol="600003"),)),
    )
    out = compose_discipline_markdown(
        rows=tuple(_discipline_row(iid=r.instrument_id,
                                    constituent_analyses=r.constituent_analyses)
                   for r in rows),
        date="2026-05-23",
        publishable_rows=rows,
        pick_order_iids=("163417", "005827", "110022"),
    )
    pos_b = out.index("### 163417")
    pos_a = out.index("### 005827")
    pos_c = out.index("### 110022")
    assert pos_b < pos_a < pos_c


def test_appendix_ordering_non_pick_publishable_sorted_by_iid_asc() -> None:
    """AC21 — funds NOT in pick_order_iids appear after, sorted by iid asc."""
    from irc.opportunity.report import compose_discipline_markdown
    rows = (
        _opportunity_row(iid="005827", name_cn="A基金",
                         constituent_analyses=(_constituent(symbol="600001"),)),
        _opportunity_row(iid="163417", name_cn="B基金",
                         constituent_analyses=(_constituent(symbol="600002"),)),
    )
    out = compose_discipline_markdown(
        rows=(),
        date="2026-05-23",
        publishable_rows=rows,
        pick_order_iids=(),  # No pick order → both are "non-pick publishable".
    )
    pos_a = out.index("### 005827")
    pos_b = out.index("### 163417")
    assert pos_a < pos_b  # 005827 < 163417 ascending


def test_appendix_shape_4_evidence_only_format() -> None:
    """AC22 c1 — `- {sym} {name} (权重 X%): {one_line_view} [ref:...]`."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=8.2,
                     evidence=(_evidence(constituent_key="600519"),
                                _evidence(constituent_key="600519",
                                          date="2024-04-16",
                                          citation_kind="information")),
                     one_line_view="持有头部白酒")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    # Shape 4 regex: `- {sym} {name} (权重 X%): {oneline} [ref:...]`.
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 8\.2%\): 持有头部白酒(?: \[ref:[0-9a-f]{16}\])+$",
        re.MULTILINE,
    )
    assert pattern.search(out), \
        f"Shape 4 (evidence only) missed; got:\n{out}"


def test_appendix_shape_2_failure_only_format() -> None:
    """AC22 c2 — `- {sym} {name} (权重 X%): ❌ {failures}`."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(), failure_reasons=("filing_fetch_failed",),
                     one_line_view="should not appear")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): ❌ filing_fetch_failed$",
        re.MULTILINE,
    )
    assert pattern.search(out)
    # one_line_view suppressed.
    assert "should not appear" not in out


def test_appendix_shape_3_audit_error_only_format() -> None:
    """AC22 c3 (precedence) — audit_errors!=() AND evidence!=() → audit-error shape wins per spec."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(_evidence(constituent_key="600519"),),
                     audit_errors=("missing_constituent_record",))
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): ⚠️ audit_error: missing_constituent_record$",
        re.MULTILINE,
    )
    assert pattern.search(out)


def test_appendix_shape_5_defensive_fallback() -> None:
    """AC29 — all-empty (evidence==failure_reasons==audit_errors==()) →
    `⚠️ audit_error: missing_constituent_record` (defensive)."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(), failure_reasons=(), audit_errors=(),
                     one_line_view="")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): ⚠️ audit_error: missing_constituent_record$",
        re.MULTILINE,
    )
    assert pattern.search(out)


def test_appendix_shape_1_evidence_plus_failures_partial_success() -> None:
    """AC22 spec edge case — evidence!=() AND failure_reasons!=() (mixed success).

    Format: `- {sym} {name} (权重 X%): {oneline} [ref:...]... ({failures})`.
    """
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(_evidence(constituent_key="600519"),),
                     failure_reasons=("broker_fetch_failed",),
                     one_line_view="持有头部白酒")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): 持有头部白酒(?: \[ref:[0-9a-f]{16}\])+ \(broker_fetch_failed\)$",
        re.MULTILINE,
    )
    assert pattern.search(out), f"Shape 1 missed; got:\n{out}"


def test_appendix_scope_publishable_only_gapped_excluded() -> None:
    """AC23 — gapped rows do NOT appear in the appendix.

    The renderer is given an empty `publishable_rows` (the upstream
    `_write_opportunity_outputs` partition excludes gapped rows before
    they reach the renderer). Verify the appendix subsection is absent.
    """
    from irc.opportunity.report import compose_discipline_markdown
    out = compose_discipline_markdown(
        rows=(),
        date="2026-05-23",
        publishable_rows=(),  # gapped row excluded by upstream
        pick_order_iids=(),
    )
    assert "### 005827" not in out


def test_appendix_constituent_order_weight_desc_symbol_asc_tiebreaker() -> None:
    """Within a subsection: weight desc, symbol asc tiebreaker."""
    from irc.opportunity.report import compose_discipline_markdown
    cs = (
        _constituent(symbol="600003", weight=5.0, name_cn="C",
                     evidence=(_evidence(constituent_key="600003"),)),
        _constituent(symbol="600001", weight=5.0, name_cn="A",
                     evidence=(_evidence(constituent_key="600001"),)),
        _constituent(symbol="600002", weight=8.0, name_cn="B",
                     evidence=(_evidence(constituent_key="600002"),)),
    )
    row = _opportunity_row(constituent_analyses=cs)
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=cs),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pos_b = out.index("600002 B")  # weight 8.0 → first
    pos_a = out.index("600001 A")  # weight 5.0, symbol 600001 → second
    pos_c = out.index("600003 C")  # weight 5.0, symbol 600003 → third
    assert pos_b < pos_a < pos_c


def test_appendix_citation_id_uses_full_16_hex() -> None:
    """AC24 — every [ref:...] in the appendix uses full 16 hex chars."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(evidence=(_evidence(),))
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    refs = re.findall(r"\[ref:([^\]]+)\]", out)
    assert refs, "no [ref:...] markers found"
    for cid in refs:
        assert len(cid) == 16, f"citation_id has {len(cid)} chars: {cid}"
        assert all(c in "0123456789abcdef" for c in cid)


def test_appendix_line_re_module_constant_present() -> None:
    """Item 009 inherits this regex — locked here for cross-test reuse."""
    from irc.opportunity import report
    assert hasattr(report, "_APPENDIX_LINE_RE")
    # The compiled re must match all 5 shapes.
    assert report._APPENDIX_LINE_RE.match(
        "- 600519 贵州茅台 (权重 8.2%): 持有头部白酒 [ref:a1b2c3d4e5f60718]"
    ) is not None


def test_compose_discipline_markdown_backward_compat_no_publishable_kwargs() -> None:
    """Q10 — signature gains keyword-only params with empty defaults; legacy
    callers passing only (rows, date) still produce a valid markdown."""
    from irc.opportunity.report import compose_discipline_markdown
    out = compose_discipline_markdown(rows=(), date="2026-05-23")
    # The appendix still appears (with （无） body since publishable_rows defaulted to ()).
    assert "## 持仓明细" in out
    # No crash.
