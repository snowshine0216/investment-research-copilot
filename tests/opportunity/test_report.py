from __future__ import annotations

import json as _json

from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.report import (
    _row_to_dict,
    compose_discipline_markdown,
    compose_opportunity_report,
    compose_thesis_cards_yaml,
)
from irc.opportunity.types import (
    DisciplineRow,
    LookthroughTarget,
    OpportunityRow,
    ThesisEvidence,
)


def _row(state="core_dca", **overrides) -> OpportunityRow:
    base = dict(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state=state,
        opportunity_reason="核心宽基指数估值合理。",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def test_opportunity_report_summary_counts_states():
    rows = [
        _row(state="core_dca"), _row(state="core_dca", instrument_id="159919"),
        _row(state="pause_wait", instrument_id="512760"),
        _row(state="exclude", instrument_id="000001", thesis_state="falsified"),
    ]
    report = compose_opportunity_report(rows, date="2026-05-14")
    assert report["date"] == "2026-05-14"
    assert report["summary"]["core_dca_count"] == 2
    assert report["summary"]["pause_wait_count"] == 1
    assert report["summary"]["exclude_count"] == 1
    assert report["summary"]["small_watch_count"] == 0
    assert len(report["rows"]) == 4
    sample = report["rows"][0]
    for key in (
        "instrument_id", "name_cn", "asset_class", "theme",
        "lookthrough_target", "valuation_state", "heat_state",
        "thesis_state", "product_quality_state", "opportunity_state",
        "opportunity_reason", "evidence_gaps",
    ):
        assert key in sample


def test_thesis_cards_yaml_includes_required_fields():
    row = _row()
    pos = PositionContext(0.05, 0.0, 0.30, None, True)
    card = build_thesis_card(row, pos, "core_cn_equity", "宽基底仓。")
    payload = compose_thesis_cards_yaml([card])
    assert "instrument_id: '510300'" in payload or 'instrument_id: "510300"' in payload
    assert "do_not_sell_just_because:" in payload
    assert "drawdown_since_entry >= 0.20" in payload


def test_thesis_cards_yaml_serializes_thesis_evidence():
    """Each thesis_evidence entry must round-trip into YAML as a mapping with
    type/source/url/date/summary keys, per the May-14 spec."""
    evidence = (
        ThesisEvidence(
            type="filing", source="600519",
            url="https://example.com/filing/600519",
            date="2026-04-28",
            summary="600519 营收同比 +12%",
            scope="constituent", citation_kind="data",
            owner_instrument_id="510300",
            parent_fund_id=None, constituent_key="600519",
        ),
        ThesisEvidence(
            type="broker", source="中信证券",
            url="https://example.com/broker/600519",
            date="2026-05-02",
            summary="维持买入",
            scope="constituent", citation_kind="information",
            owner_instrument_id="510300",
            parent_fund_id=None, constituent_key="600519",
        ),
    )
    row = _row(thesis_evidence=evidence)
    pos = PositionContext(0.05, 0.0, 0.30, None, True)
    card = build_thesis_card(row, pos, "core", "x")
    payload = compose_thesis_cards_yaml([card])
    assert "thesis_evidence:" in payload
    assert "type: filing" in payload
    assert "中信证券" in payload
    assert "https://example.com/filing/600519" in payload
    assert "citation_id:" in payload  # Item 002: every evidence carries citation_id.


def test_discipline_markdown_has_chinese_action_sections():
    """Spec integration test 3: Markdown has Chinese actionable sections."""
    rows = [
        DisciplineRow("510300", "宽基", "cn_etf", "broad", "core_dca",
                      "normal_dca", "none", "可定投"),
        DisciplineRow("512760", "半导体", "cn_etf", "semiconductor", "pause_wait",
                      "pause_dca", "review_required", "暂停加仓"),
        DisciplineRow("000001", "主动", "cn_equity_fund", "consumer", "exclude",
                      "do_not_buy", "exit_review", "退出复核"),
    ]
    md = compose_discipline_markdown(rows, date="2026-05-14")
    assert "## 今日可定投" in md
    assert "## 暂停加仓" in md
    assert "## 风险复核" in md
    assert "## 调仓复核" in md
    assert "## 退出复核" in md
    assert "## 关于回撤的说明" in md
    assert "20%" in md


def test_discipline_markdown_empty_categories_render_placeholder():
    md = compose_discipline_markdown([], date="2026-05-14")
    assert "## 今日可定投" in md
    assert "（无）" in md or "(none)" in md


def test_slow_dca_routes_to_jianshu_bucket():
    """Issue 3 fix: slow_dca must appear in 减速定投, not 今日可定投."""
    rows = [
        DisciplineRow("512760", "半导体", "cn_etf", "semiconductor", "small_watch",
                      "slow_dca", "none", "观察仓位"),
    ]
    md = compose_discipline_markdown(rows, date="2026-05-14")
    assert "## 减速定投" in md
    # The instrument must appear under 减速定投, not 今日可定投
    jianshu_section = md.split("## 减速定投")[1].split("##")[0]
    assert "512760" in jianshu_section
    jinkeri_section = md.split("## 今日可定投")[1].split("##")[0]
    assert "512760" not in jinkeri_section


def test_row_to_dict_includes_expected_omissions():
    row = OpportunityRow(
        instrument_id="518880", name_cn="黄金ETF", asset_class="gold", theme=None,
        lookthrough_target=LookthroughTarget(kind="gold", key="gold", display_cn="GOLD"),
        valuation_state="neutral", heat_state="neutral",
        thesis_state="evidence_insufficient", product_quality_state="ok",
        opportunity_state="small_watch", opportunity_reason="r",
        evidence_gaps=("news_stage_skipped",),
        expected_omissions=("constituent_not_applicable",),
    )
    d = _row_to_dict(row)
    assert d["expected_omissions"] == ["constituent_not_applicable"]
    assert d["evidence_gaps"] == ["news_stage_skipped"]


def test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions():
    """JSON round-trip: thesis_evidence appears as a list of dicts with all
    provenance fields including citation_id; contributing_dimensions appears
    as a sorted list; constituent_analyses appears as an empty list (item 003
    populates it later)."""
    ev = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/filing/600519",
        date="2026-04-28", summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    row = _row(
        thesis_evidence=(ev,),
        contributing_dimensions=frozenset({"valuation", "heat"}),
    )
    d = _row_to_dict(row)
    # Round-trip through JSON to confirm serializability.
    loaded = _json.loads(_json.dumps(d, ensure_ascii=False))
    assert "thesis_evidence" in loaded
    assert len(loaded["thesis_evidence"]) == 1
    assert loaded["thesis_evidence"][0]["citation_id"] == ev.citation_id
    assert loaded["thesis_evidence"][0]["owner_instrument_id"] == "510300"
    assert loaded["thesis_evidence"][0]["scope"] == "constituent"
    # contributing_dimensions: sorted list (item 001's frozenset → sorted list)
    assert loaded["contributing_dimensions"] == ["heat", "valuation"]
    # constituent_analyses default-empty until item 003.
    assert loaded["constituent_analyses"] == []


def test_row_to_dict_serializes_fetch_types_attempted():
    """_row_to_dict must emit fetch_types_attempted so render_failure_sections
    can populate 已尝试: in the gapped-target failure block."""
    row = _row(fetch_types_attempted=("filing", "broker", "news"))
    d = _row_to_dict(row)
    loaded = _json.loads(_json.dumps(d, ensure_ascii=False))
    assert "fetch_types_attempted" in loaded
    assert loaded["fetch_types_attempted"] == ["filing", "broker", "news"]


def test_row_to_dict_fetch_types_attempted_empty_default():
    """When no fetch_types_attempted is set, _row_to_dict emits an empty list."""
    row = _row()
    d = _row_to_dict(row)
    loaded = _json.loads(_json.dumps(d, ensure_ascii=False))
    assert loaded["fetch_types_attempted"] == []


# ── Item 003: _card_to_dict defensive citation_id check ──────────────────────

def test_card_to_dict_raises_on_missing_nested_citation_id(monkeypatch) -> None:
    import pytest
    from unittest.mock import patch
    from irc.opportunity.report import _card_to_dict
    from irc.opportunity.types import ConstituentAnalysis, ThesisCard, ThesisEvidence
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519",
    )
    c = ConstituentAnalysis("600519", "贵州茅台", 6.2, (ev,), (), "")
    card = ThesisCard(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None, role="watchlist",
        lookthrough_target="易方达蓝筹精选", entry_reason="",
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        dca_action="pause_dca", risk_action="none",
        falsification_triggers=(), trim_triggers=(),
        do_not_sell_just_because=(), review_cadence="weekly",
        evidence_gaps=(), constituent_analyses=(c,),
    )
    d = _card_to_dict(card)
    # Happy path: citation_id present.
    assert d["constituent_analyses"][0]["evidence"][0]["citation_id"] != ""

    # Now simulate a corrupted dict (manually blank the id).
    with patch("irc.opportunity.report.asdict") as mocked_asdict:
        bad = dict(d)
        bad["constituent_analyses"] = [
            {"evidence": [{"citation_id": ""}]},
        ]
        mocked_asdict.return_value = bad
        with pytest.raises(RuntimeError, match="citation_id"):
            _card_to_dict(card)


# ── Item 007 D3a — _render_section nested thesis_evidence bullets ─────────────

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


def _discipline_row(
    *, iid="005827", thesis_evidence=(), constituent_analyses=(),
    dca_action="normal_dca", risk_action="none",
    opportunity_state="core_dca",
):
    from irc.opportunity.types import DisciplineRow
    return DisciplineRow(
        instrument_id=iid,
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        opportunity_state=opportunity_state,
        dca_action=dca_action,
        risk_action=risk_action,
        note_cn="",
        thesis_evidence=thesis_evidence,
        constituent_analyses=constituent_analyses,
    )


def test_render_section_emits_top_3_nested_bullets() -> None:
    """AC12 — 5 evidence entries → exactly 3 nested bullets via select_citations."""
    from irc.opportunity.report import _render_section
    evs = tuple(
        _evidence(date=f"2024-04-{d:02d}", url=f"https://x/{d}",
                  citation_kind="data" if d % 2 == 0 else "information",
                  scope="constituent",
                  constituent_key=f"60051{d}")
        for d in range(1, 6)
    )
    row = _discipline_row(thesis_evidence=evs)
    out = _render_section("今日可定投", [row])
    # Three nested `  - [ref:...]` bullets.
    nested = re.findall(r"^  - \[ref:[0-9a-f]{16}\] ", out, re.MULTILINE)
    assert len(nested) == 3


def test_render_section_empty_thesis_evidence_no_bullets() -> None:
    """AC14 — empty thesis_evidence → no nested bullets, no `（无）` placeholder."""
    from irc.opportunity.report import _render_section
    row = _discipline_row(thesis_evidence=())
    out = _render_section("今日可定投", [row])
    # No `  - [ref:` lines.
    assert "  - [ref:" not in out
    # No `（无）` line either (that's the empty-section placeholder, not empty-bullets).
    parent_line = next((l for l in out.split("\n") if l.startswith("- **005827")), "")
    assert parent_line  # parent line still rendered
    # Body has no bullet lines beyond the parent.
    bullets_under = [l for l in out.split("\n")
                     if l.startswith("  - ")]
    assert bullets_under == []


def test_render_section_nested_bullet_format() -> None:
    """Locked format: `  - [ref:{cid}] {type} · {source} · {date}` (no summary, no url)."""
    from irc.opportunity.report import _render_section
    ev = _evidence(type_="filing", source="akshare:filing:600519",
                   date="2024-04-15")
    row = _discipline_row(thesis_evidence=(ev,))
    out = _render_section("今日可定投", [row])
    nested = re.search(r"^  - \[ref:[0-9a-f]{16}\] filing · akshare:filing:600519 · 2024-04-15$",
                       out, re.MULTILINE)
    assert nested is not None, f"locked format missed; got:\n{out}"
