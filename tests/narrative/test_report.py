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
from irc.narrative.report_appendix import (
    _insufficient_middle,
    _insufficient_refresh_line,
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


# --- Task 6: AC6/AC7 — product-quality drivers next to 质量 ---

def _report_pm(iid: str, pm: ProductMetrics, *, quality="weak") -> NarrativeFundReport:
    base = _report(iid)
    return replace(base, product_quality_state=quality, product_metrics=pm)


def test_report_md_renders_product_drivers() -> None:
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=0.002)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "质量=weak" in block
    assert "费率=0.005" in block
    assert "规模=" in block       # aum formatted, not None
    assert "任职=7.0" in block
    assert "跟踪误差=0.002" in block


def test_report_md_none_metric_renders_em_dash() -> None:
    pm = ProductMetrics(expense_ratio=None, aum_cny=None,
                        manager_tenure_years=7.0, tracking_error=None)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "费率=—" in block
    assert "规模=—" in block
    assert "任职=7.0" in block


def test_report_md_metadata_floored_weak_shows_all_em_dash() -> None:
    pm = ProductMetrics()  # all None — the metadata-thin floor case (RD-2)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "质量=weak" in block
    assert "费率=— 规模=— 任职=—" in block  # visibly floored, not real signal


def test_report_md_genuine_weak_shows_real_numbers() -> None:
    pm = ProductMetrics(expense_ratio=0.02, aum_cny=1.0e7, manager_tenure_years=1.0)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    # All gating metrics are real (no em-dash on the drivers line up to 任职=)
    drivers_line = block.split("质量=weak")[1].split("\n")[0]
    assert "费率=—" not in drivers_line
    assert "规模=—" not in drivers_line
    assert "任职=—" not in drivers_line


def test_report_md_no_product_metrics_renders_em_dash_drivers() -> None:
    md = render_report_md("算力金属", (_report("A"),))  # product_metrics is None
    block = md.split("## A ")[1]
    assert "费率=—" in block  # None bundle → all em-dash, never crashes


# --- Task 1 (004): 产品驱动 on its own line ---

def test_report_md_product_drivers_on_own_line() -> None:
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=0.002)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    # 产品驱动 must be a standalone bullet, NOT riding the 子状态 line.
    drivers_lines = [ln for ln in block.splitlines() if ln.startswith("- 产品驱动:")]
    assert len(drivers_lines) == 1
    assert "费率=0.005" in drivers_lines[0]
    substate_lines = [ln for ln in block.splitlines() if ln.startswith("- 子状态:")]
    assert len(substate_lines) == 1
    assert "产品驱动" not in substate_lines[0]  # decoupled (grill Q2)


# --- Task 2 (004): insufficient helpers ---

def _report_insufficient(iid: str, *, gaps=("missing_product_metadata",),
                         evidence: tuple[ThesisEvidence, ...] = (),
                         pm: ProductMetrics | None = None) -> NarrativeFundReport:
    """An insufficient row that — like the _report_from_card path — carries REAL
    sub-state verdicts (not all evidence_insufficient), to prove field-level
    suppression (grill Q1)."""
    base = _report(iid, level="insufficient", evidence=evidence)
    return replace(
        base,
        risk_rationale="evidence_gaps present — risk cannot be assessed",
        risk_drivers=("evidence_gaps",),
        evidence_gaps=gaps,
        product_metrics=pm,
    )


def test_insufficient_refresh_line_names_gap_and_analyze() -> None:
    r = _report_insufficient("A", gaps=("missing_valuation_data", "missing_product_metadata"))
    line = _insufficient_refresh_line("算力金属", r)
    assert line.startswith("- ⚠️ 证据不足 / insufficient")
    assert "missing_valuation_data" in line
    assert "missing_product_metadata" in line
    assert "uv run irc narrative 算力金属 --analyze" in line


def test_insufficient_refresh_line_falls_back_to_rationale_then_literal() -> None:
    r_no_gaps = replace(_report_insufficient("A"), evidence_gaps=(),
                        risk_rationale="some why")
    assert "some why" in _insufficient_refresh_line("算力金属", r_no_gaps)
    r_empty = replace(_report_insufficient("A"), evidence_gaps=(), risk_rationale="")
    assert "evidence_insufficient" in _insufficient_refresh_line("算力金属", r_empty)


def test_insufficient_middle_has_product_drivers_and_refresh_no_substate() -> None:
    pm = ProductMetrics(expense_ratio=0.005)
    mid = _insufficient_middle("算力金属", _report_insufficient("A", pm=pm))
    text = "\n".join(mid)
    assert "- 产品驱动: " in text
    assert "费率=0.005" in text
    assert "⚠️ 证据不足 / insufficient" in text
    assert "子状态" not in text     # no sub-state line
    assert "机会 / dca / 风险" not in text  # no triad


# --- Task 3 (004): per-row branch tests (AC1-AC5, AC9) ---

_FORBIDDEN_INSUFFICIENT_TOKENS = (
    # action triad
    "机会 / dca / 风险", "small_watch", "pause_wait", "slow_dca", "do_not_buy",
    "trim_review", "review_required",
    # triggers + cadence markers
    "证伪触发", "减仓触发", "复核节奏",
    # sub-state line marker + sub-state verdict tokens (grill Q1/Q6)
    "子状态",
    "expensive", "very_expensive", "overheated", "crowded", "under_pressure",
    "falsified", "weak", "poor", "intact", "cheap", "acceptable",
    "evidence_insufficient",
)


def test_insufficient_row_suppresses_triad_and_substates() -> None:
    r = _report_insufficient("A")  # carries real verdicts via _report (very_expensive/overheated/intact)
    md = render_report_md("算力金属", (r,))
    block = md.split("## A ")[1]
    assert "机会 / dca / 风险" not in block
    assert "子状态" not in block
    for tok in ("small_watch", "slow_dca", "trim_review",
                "very_expensive", "overheated", "intact", "acceptable"):
        assert tok not in block, f"forbidden verdict token leaked: {tok}"


def test_insufficient_block_forbidden_tokens_locked() -> None:
    """Locked grep — the enforcement mechanism (grill Q6, mirrors
    failure_renderer.py criterion 18). No triad/trigger/cadence/sub-state-verdict
    token survives on an insufficient block."""
    r = _report_insufficient("A")
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    for tok in _FORBIDDEN_INSUFFICIENT_TOKENS:
        assert tok not in block, f"forbidden token survived insufficient block: {tok}"


def test_insufficient_row_suppresses_triggers_and_cadence() -> None:
    block = render_report_md("算力金属", (_report_insufficient("A"),)).split("## A ")[1]
    assert "证伪触发" not in block
    assert "减仓触发" not in block
    assert "复核节奏" not in block


def test_insufficient_row_renders_refresh_line() -> None:
    r = _report_insufficient("A", gaps=("missing_product_metadata",))
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    assert "⚠️ 证据不足 / insufficient" in block
    assert "missing_product_metadata" in block
    assert "uv run irc narrative 算力金属 --analyze" in block


def test_insufficient_row_keeps_gap_facts_and_product_drivers_line() -> None:
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8)
    r = _report_insufficient("A", pm=pm)
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    assert "position_risk_level: **insufficient**" in block
    assert "主因 / drivers: evidence_gaps" in block
    assert "说明: evidence_gaps present — risk cannot be assessed" in block
    drivers_lines = [ln for ln in block.splitlines() if ln.startswith("- 产品驱动:")]
    assert len(drivers_lines) == 1
    assert "费率=0.005" in drivers_lines[0]


def test_insufficient_row_keeps_partial_evidence_and_refs_resolve() -> None:
    r = _report_insufficient("A", evidence=_multi("A"))
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    assert "证据明细" in block  # footnote table still renders
    inline_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", block))
    assert inline_ids, "partial evidence should still render inline refs"
    for cid in inline_ids:
        footnote = [ln for ln in block.splitlines() if ln.startswith(f"[ref:{cid}]")]
        assert len(footnote) == 1, f"{cid} resolved {len(footnote)} times"


def test_mixed_report_branches_per_row() -> None:
    suff = _report("S", evidence=(_evidence("S"),))            # elevated → full
    insf = _report_insufficient("I", gaps=("missing_product_metadata",))
    md = render_report_md("算力金属", (insf, suff))
    insf_block = md.split("## I ")[1].split("## S ")[0]
    suff_block = md.split("## S ")[1]
    # insufficient: suppressed
    assert "机会 / dca / 风险" not in insf_block
    assert "⚠️ 证据不足 / insufficient" in insf_block
    # sufficient: full triad + cadence + triggers
    assert "机会 / dca / 风险:" in suff_block
    assert "复核节奏" in suff_block
    assert "证伪触发" in suff_block
    assert "⚠️ 证据不足" not in suff_block


# --- Task 4 (004): determinism + golden + .json unchanged (AC6, AC7, AC8) ---

def test_insufficient_row_render_is_deterministic() -> None:
    r = _report_insufficient("A", evidence=_multi("A"),
                              pm=ProductMetrics(expense_ratio=0.005))
    reports = (r,)
    assert render_report_md("算力金属", reports) == render_report_md("算力金属", reports)


def test_sufficient_row_block_byte_identical_golden() -> None:
    """AC6: a sufficient (elevated) row's middle block is byte-identical to the
    pre-004 shape — full triad, 子状态, 产品驱动, cadence, both triggers."""
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=0.002)
    r = replace(_report("A", level="elevated"), product_metrics=pm)
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    expected_middle = (
        "- 仓位风险等级 / position_risk_level: **elevated**\n"
        "- 主因 / drivers: valuation_state\n"
        "- 说明: elevated — very_expensive valuation\n"
        "- 机会 / dca / 风险: small_watch ｜ slow_dca ｜ trim_review\n"
        "- 子状态: 估值=very_expensive 热度=overheated 逻辑=intact 质量=acceptable\n"
        "- 产品驱动: 费率=0.005 规模=500000000.0 任职=7.0 跟踪误差=0.002\n"
        "- 复核节奏 / review_cadence: weekly_light_monthly_full\n"
        "- 证伪触发: theme thesis moves to falsified\n"
        "- 减仓触发: valuation_state in [expensive, very_expensive]\n"
    )
    assert expected_middle in block


def test_insufficient_row_json_still_carries_conclusions() -> None:
    """AC7: .md suppression is display-only; .json keeps the full real values."""
    r = _report_insufficient("A", gaps=("missing_product_metadata",))
    fund = json.loads(render_report_json("算力金属", (r,)))["funds"][0]
    assert fund["opportunity_state"] == "small_watch"
    assert fund["dca_action"] == "slow_dca"
    assert fund["risk_action"] == "trim_review"
    assert fund["valuation_state"] == "very_expensive"
    assert fund["thesis_state"] == "intact"
    assert fund["review_cadence"] == "weekly_light_monthly_full"
    assert fund["falsification_triggers"] == ["theme thesis moves to falsified"]
    assert fund["evidence_gaps"] == ["missing_product_metadata"]


# --- Task 7: AC8 — .json stays full source of truth (additive) ---

def test_report_json_includes_product_metrics_and_constituents() -> None:
    ev = _evidence("601899")
    ca = ConstituentAnalysis(
        symbol="601899", name_cn="紫金矿业", weight_pct=8.5,
        evidence=(ev,), failure_reasons=(), one_line_view="紫金 +20%", audit_errors=(),
    )
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=None)
    r = replace(_report("A", evidence=(ev,)), constituent_analyses=(ca,), product_metrics=pm)
    doc = json.loads(render_report_json("算力金属", (r,)))
    fund = doc["funds"][0]
    # additive — every existing key still present (round-trip AC8)
    assert fund["thesis_evidence"][0]["citation_id"] == ev.citation_id
    assert fund["product_metrics"]["expense_ratio"] == 0.005
    assert fund["product_metrics"]["tracking_error"] is None
    assert fund["constituent_analyses"][0]["symbol"] == "601899"
    assert fund["constituent_analyses"][0]["one_line_view"] == "紫金 +20%"


def test_report_json_two_calls_byte_identical() -> None:
    ev = _evidence("A")
    pm = ProductMetrics(expense_ratio=0.005)
    r = replace(_report("A", evidence=(ev,)), product_metrics=pm)
    assert render_report_json("算力金属", (r,)) == render_report_json("算力金属", (r,))


# ── FIX 1 — AC8 gap: .json evidence dict must include summary + url ──────────

def test_report_json_evidence_dict_includes_summary_and_url() -> None:
    """FIX 1: _evidence_dict must carry summary + url (additive; existing keys kept)."""
    ev = ThesisEvidence(
        type="broker", source="CICC", url="http://cicc.com/r1",
        date="2026-03-15",
        summary="CICC 增持: AI算力扩张加速",
        scope="instrument", citation_kind="information",
        owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
    )
    doc = json.loads(render_report_json("算力金属", (_report("A", evidence=(ev,)),)))
    ev_d = doc["funds"][0]["thesis_evidence"][0]
    # new keys
    assert ev_d["summary"] == "CICC 增持: AI算力扩张加速"
    assert ev_d["url"] == "http://cicc.com/r1"
    # existing keys untouched
    assert ev_d["citation_id"] == ev.citation_id
    assert ev_d["type"] == "broker"
    assert ev_d["source"] == "CICC"
    assert ev_d["date"] == "2026-03-15"
    assert ev_d["scope"] == "instrument"
    assert ev_d["citation_kind"] == "information"


def test_report_json_constituent_evidence_dict_includes_summary_and_url() -> None:
    """FIX 1: constituent evidence dict in .json also carries summary + url."""
    ev = ThesisEvidence(
        type="filing", source="cninfo", url="http://cninfo.com/f1",
        date="2026-03-31",
        summary="601899 Q1 filing",
        scope="constituent", citation_kind="data",
        owner_instrument_id="A", parent_fund_id="A", constituent_key="601899",
    )
    ca = ConstituentAnalysis(
        symbol="601899", name_cn="紫金矿业", weight_pct=8.5,
        evidence=(ev,), failure_reasons=(), one_line_view="紫金 +20%", audit_errors=(),
    )
    r = replace(_report("A", evidence=(ev,)), constituent_analyses=(ca,))
    doc = json.loads(render_report_json("算力金属", (r,)))
    c_ev_d = doc["funds"][0]["constituent_analyses"][0]["evidence"][0]
    assert c_ev_d["summary"] == "601899 Q1 filing"
    assert c_ev_d["url"] == "http://cninfo.com/f1"
    assert c_ev_d["citation_id"] == ev.citation_id


# ── FIX 2 — dangling constituent footnote refs ────────────────────────────────

def _ev_with_id(iid: str, src: str) -> ThesisEvidence:
    """Helper producing a ThesisEvidence whose citation_id is determined by its args."""
    return ThesisEvidence(
        type="news", source=src, url=f"http://{src}.com",
        date="2026-04-01", summary=f"headline from {src}",
        scope="instrument", citation_kind="information",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def test_constituent_only_footnote_resolves_even_when_absent_from_thesis_evidence() -> None:
    """FIX 2: a constituent-evidence ref NOT in r.thesis_evidence must still appear
    under 証拠明细."""
    # Thesis-level evidence: one citation from "srcA"
    ev_thesis = _ev_with_id("A", "srcA")
    # Constituent-level evidence: different citation from "srcB" — NOT in thesis_evidence
    ev_const = _ev_with_id("A", "srcB")
    assert ev_thesis.citation_id != ev_const.citation_id, "test setup: must be distinct"
    ca = ConstituentAnalysis(
        symbol="601899", name_cn="紫金矿业", weight_pct=8.5,
        evidence=(ev_const,), failure_reasons=(), one_line_view="prose", audit_errors=(),
    )
    r = replace(_report("A", evidence=(ev_thesis,)), constituent_analyses=(ca,))
    md = render_report_md("算力金属", (r,))
    block = md.split("## A ")[1]
    # The constituent inline ref must appear as a footnote line
    assert f"[ref:{ev_const.citation_id}]" in block, "constituent ref missing from appendix inline"
    footnote_lines = [ln for ln in block.splitlines() if ln.startswith(f"[ref:{ev_const.citation_id}]")]
    assert len(footnote_lines) == 1, f"expected 1 footnote for constituent citation, got {len(footnote_lines)}"


# ── FIX 3 — deterministic dedup ──────────────────────────────────────────────

def test_footnote_dedup_deterministic_regardless_of_input_order() -> None:
    """FIX 3: two evidence records sharing a citation_id (citation_kind differs —
    citation_kind is NOT in the hash preimage per ADR 0001) in swapped input orders
    must produce byte-identical footnote sections."""
    # citation_id preimage excludes citation_kind, so "data" vs "information"
    # with identical other fields → same citation_id, different objects.
    ev_data = ThesisEvidence(
        type="filing", source="cninfo", url="http://cninfo.com/x",
        date="2026-03-31", summary="shared filing preimage",
        scope="instrument", citation_kind="data",
        owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
    )
    ev_info = ThesisEvidence(
        type="filing", source="cninfo", url="http://cninfo.com/x",
        date="2026-03-31", summary="shared filing preimage",
        scope="instrument", citation_kind="information",
        owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
    )
    assert ev_data.citation_id == ev_info.citation_id, (
        "test setup: citation_kind excluded from preimage → same citation_id"
    )
    # Also add a distinct anchor so the report has ≥2 footnotes
    ev_other = _ev_with_id("A", "srcZ")
    order_a = (ev_data, ev_other)    # data first
    order_b = (ev_info, ev_other)    # info first (same citation_id, different object)
    r_a = _report("A", evidence=order_a)
    r_b = _report("A", evidence=order_b)
    md_a = render_report_md("算力金属", (r_a,))
    md_b = render_report_md("算力金属", (r_b,))

    def _footnote_section(md: str) -> str:
        marker = "### 证据明细"
        if marker in md:
            return md.split(marker)[1]
        return ""

    assert _footnote_section(md_a) == _footnote_section(md_b), (
        "footnote sections differ by input order — non-deterministic dedup"
    )


# ── FIX 4 — M2 weak-floor legend ─────────────────────────────────────────────

def test_report_md_weak_fund_has_floor_legend() -> None:
    """FIX 4: a report with product_quality_state='weak' must include a legend
    referencing the F-1 floor and the 产品驱动 drivers."""
    pm = ProductMetrics()  # all None — metadata-thin floor
    r = replace(_report("A"), product_quality_state="weak", product_metrics=pm)
    md = render_report_md("算力金属", (r,))
    # Legend must be present and reference the structural floor / F-1
    assert "F-1" in md or "aum_stability_pct" in md or "floor" in md.lower() or "结构性下限" in md
    # Legend must reference 产品驱动 (the driver metrics)
    assert "产品驱动" in md


def test_report_md_no_weak_fund_no_floor_legend_required() -> None:
    """FIX 4: when NO fund is weak the legend is either absent or harmless (we accept
    both renderings — the spec says 'at least one weak → legend present'; absence when
    none-weak is permissible)."""
    r = replace(_report("A"), product_quality_state="acceptable")
    md = render_report_md("算力金属", (r,))
    # This is a soft check — just confirm the report renders without error.
    assert "## A " in md


# ── FIX 5 — markdown safety of summary ───────────────────────────────────────

def test_summary_with_newline_renders_single_line_in_bullet() -> None:
    """FIX 5: a summary containing \\n must not break the inline bullet or footnote."""
    ev = ThesisEvidence(
        type="news", source="xinhua", url="http://xinhua.cn/1",
        date="2026-04-01", summary="line1\nline2",
        scope="instrument", citation_kind="information",
        owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
    )
    md = render_report_md("算力金属", (_report("A", evidence=(ev,)),))
    # The inline bullet and any footnote line that contain this citation_id
    # must not embed a raw newline within the same bullet/footnote line.
    for line in md.splitlines():
        if f"[ref:{ev.citation_id}]" in line:
            assert "\n" not in line  # trivially true once splitlines() is used
            assert "line1" in line and "line2" in line, (
                "both parts of the summary must appear on ONE line"
            )


def test_empty_summary_produces_no_trailing_separator() -> None:
    """FIX 5: when summary is empty/blank, no trailing ' · ' separator in bullet/footnote."""
    ev = ThesisEvidence(
        type="filing", source="cninfo", url="",
        date="2026-03-31", summary="",
        scope="instrument", citation_kind="data",
        owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
    )
    md = render_report_md("算力金属", (_report("A", evidence=(ev,)),))
    for line in md.splitlines():
        if f"[ref:{ev.citation_id}]" in line:
            # No trailing separator: line must not end with " · " or "· "
            assert not line.rstrip().endswith("·"), f"trailing · in: {line!r}"
            assert not line.rstrip().endswith("· "), f"trailing '· ' in: {line!r}"
