from __future__ import annotations
import pytest
from dataclasses import FrozenInstanceError

from irc.opportunity.types import (
    LookthroughTarget,
    OpportunityRow,
    ThesisCard,
    ThesisEvidence,
    VALUATION_STATES,
    HEAT_STATES,
    THESIS_STATES,
    PRODUCT_QUALITY_STATES,
    OPPORTUNITY_STATES,
    DCA_ACTIONS,
    RISK_ACTIONS,
)


def test_state_enums_match_spec():
    assert VALUATION_STATES == (
        "cheap", "reasonable_low", "fair", "expensive", "very_expensive", "evidence_insufficient",
    )
    assert HEAT_STATES == (
        "cold", "normal", "crowded", "overheated", "evidence_insufficient",
    )
    assert THESIS_STATES == (
        "intact", "under_pressure", "falsified", "evidence_insufficient",
    )
    assert PRODUCT_QUALITY_STATES == (
        "strong", "acceptable", "weak", "poor", "evidence_insufficient",
    )
    assert OPPORTUNITY_STATES == ("core_dca", "small_watch", "pause_wait", "exclude")
    assert DCA_ACTIONS == (
        "accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy",
    )
    assert RISK_ACTIONS == ("none", "review_required", "trim_review", "exit_review")


def test_lookthrough_target_is_frozen():
    target = LookthroughTarget(
        kind="broad_index",
        key="csi300",
        display_cn="沪深300",
    )
    with pytest.raises(FrozenInstanceError):
        target.kind = "sector"  # type: ignore[misc]


def test_opportunity_row_required_fields():
    row = OpportunityRow(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        opportunity_reason="底层指数估值合理，热度正常，长期逻辑完好。",
        evidence_gaps=(),
    )
    assert row.opportunity_state == "core_dca"


def test_thesis_evidence_is_frozen_dataclass():
    """ThesisEvidence pairs a typed source with a citable URL + date + summary.
    Used inside ThesisCard.thesis_evidence and OpportunityRow.thesis_evidence."""
    ev = ThesisEvidence(
        type="filing",
        source="巨潮资讯",
        url="http://www.cninfo.com.cn/foo",
        date="2026-04-28",
        summary="中芯国际 2026Q1 营收同比 +18%。",
        scope="instrument", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key=None,
    )
    assert ev.type == "filing"
    with pytest.raises(FrozenInstanceError):
        ev.source = "x"  # type: ignore[misc]


def test_thesis_evidence_type_must_be_known_kind():
    """Allowed kinds: filing | broker | news | policy | snapshot."""
    for kind in ("filing", "broker", "news", "policy", "snapshot"):
        ev = ThesisEvidence(
            type=kind, source="s", url="u", date="d", summary="x",
            scope="instrument", citation_kind="data",
            owner_instrument_id="510300",
            parent_fund_id=None, constituent_key=None,
        )
        assert ev.type == kind


def test_thesis_card_defaults_immutable_collections():
    card = ThesisCard(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        role="core_cn_equity",
        lookthrough_target="沪深300",
        entry_reason="核心宽基指数底仓。",
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        dca_action="normal_dca",
        risk_action="none",
        falsification_triggers=(),
        trim_triggers=(),
        do_not_sell_just_because=("drawdown_since_entry >= 0.20",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(),
    )
    assert isinstance(card.falsification_triggers, tuple)
    assert isinstance(card.do_not_sell_just_because, tuple)


def _row(**over):
    base = dict(
        instrument_id="X", name_cn="X", asset_class="gold", theme=None,
        lookthrough_target=LookthroughTarget(kind="gold", key="gold", display_cn="GOLD"),
        valuation_state="neutral", heat_state="neutral", thesis_state="evidence_insufficient",
        product_quality_state="ok", opportunity_state="small_watch", opportunity_reason="r",
        evidence_gaps=(),
    )
    base.update(over)
    return OpportunityRow(**base)


def test_opportunity_row_has_expected_omissions_default_empty():
    r = _row()
    assert r.expected_omissions == ()


def test_opportunity_row_accepts_expected_omissions_kwarg():
    r = _row(expected_omissions=("constituent_not_applicable",))
    assert r.expected_omissions == ("constituent_not_applicable",)


def _evidence_kwargs(**over):
    """Helper: minimal valid kwargs for ThesisEvidence. Override per test."""
    base = dict(
        type="filing",
        source="600519",
        url="https://example.com/foo",
        date="2026-04-28",
        summary="x",
        scope="instrument",
        citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None,
        constituent_key=None,
    )
    base.update(over)
    return base


def test_thesis_evidence_rejects_empty_owner_instrument_id():
    with pytest.raises(ValueError, match="owner_instrument_id"):
        ThesisEvidence(**_evidence_kwargs(owner_instrument_id=""))


def test_thesis_evidence_rejects_invalid_citation_kind():
    with pytest.raises(ValueError, match="citation_kind"):
        ThesisEvidence(**_evidence_kwargs(citation_kind="both"))  # type: ignore[arg-type]


def test_thesis_evidence_rejects_invalid_scope():
    with pytest.raises(ValueError, match="scope"):
        ThesisEvidence(**_evidence_kwargs(scope="random"))  # type: ignore[arg-type]


def test_thesis_evidence_rejects_empty_type_source_date():
    with pytest.raises(ValueError, match="type/source/date"):
        ThesisEvidence(**_evidence_kwargs(type=""))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="type/source/date"):
        ThesisEvidence(**_evidence_kwargs(source=""))
    with pytest.raises(ValueError, match="type/source/date"):
        ThesisEvidence(**_evidence_kwargs(date=""))


def test_thesis_evidence_accepts_none_for_fund_level_optional_fields():
    """parent_fund_id and constituent_key may be None for fund-level evidence."""
    ev = ThesisEvidence(**_evidence_kwargs(parent_fund_id=None, constituent_key=None))
    assert ev.parent_fund_id is None
    assert ev.constituent_key is None


def test_citation_id_is_deterministic_for_identical_preimage():
    """Same inputs → same 16-hex citation_id. Content-addressed invariant."""
    kwargs = _evidence_kwargs()
    a = ThesisEvidence(**kwargs)
    b = ThesisEvidence(**kwargs)
    assert a.citation_id == b.citation_id
    assert len(a.citation_id) == 16
    assert all(c in "0123456789abcdef" for c in a.citation_id)


def test_citation_id_differs_across_owner_instruments():
    """Same type/source/date/url but different owner_instrument_id → different id."""
    a = ThesisEvidence(**_evidence_kwargs(owner_instrument_id="510300"))
    b = ThesisEvidence(**_evidence_kwargs(owner_instrument_id="163417"))
    assert a.citation_id != b.citation_id


def test_citation_id_differs_across_constituents_under_same_fund():
    """Same type/source/date/url/owner_instrument_id but different constituent_key → different id."""
    a = ThesisEvidence(**_evidence_kwargs(
        scope="constituent", owner_instrument_id="005827",
        parent_fund_id="005827", constituent_key="600519",
    ))
    b = ThesisEvidence(**_evidence_kwargs(
        scope="constituent", owner_instrument_id="005827",
        parent_fund_id="005827", constituent_key="000858",
    ))
    assert a.citation_id != b.citation_id


from irc.opportunity.types import CitationMeta, CitedMap, ConstituentCitedMap  # noqa: E402


def test_citation_meta_is_frozen_dataclass():
    m = CitationMeta(
        scope="instrument",
        citation_kind="data",
        owner_instrument_id="510300",
        asset_class="cn_etf",
        parent_fund_id=None,
        constituent_key=None,
    )
    assert m.asset_class == "cn_etf"
    with pytest.raises(FrozenInstanceError):
        m.asset_class = "x"  # type: ignore[misc]


def test_cited_map_type_alias_is_importable():
    """CitedMap / ConstituentCitedMap are type aliases — import smoke test."""
    assert CitedMap is not None
    assert ConstituentCitedMap is not None


def test_discipline_row_has_new_evidence_fields_with_empty_defaults():
    """DisciplineRow gains thesis_evidence, constituent_analyses, evidence_gaps,
    fetch_types_attempted (all defaulted to empty tuples so existing test
    constructors still work)."""
    from irc.opportunity.types import DisciplineRow as _DR
    r = _DR(
        instrument_id="510300", name_cn="x", asset_class="cn_etf", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
    )
    assert r.thesis_evidence == ()
    assert r.constituent_analyses == ()
    assert r.evidence_gaps == ()
    assert r.fetch_types_attempted == ()


def test_discipline_row_accepts_evidence_gaps_kwarg():
    from irc.opportunity.types import DisciplineRow as _DR
    r = _DR(
        instrument_id="510300", name_cn="x", asset_class="cn_etf", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        evidence_gaps=("holdings_fetch_failed",),
        fetch_types_attempted=("filing", "broker", "news"),
    )
    assert r.evidence_gaps == ("holdings_fetch_failed",)
    assert r.fetch_types_attempted == ("filing", "broker", "news")


def test_opportunity_row_has_fetch_types_attempted_with_empty_default():
    """OpportunityRow gains fetch_types_attempted (tuple[str, ...] = ()) so that
    _row_to_dict can serialize it and render_failure_sections can render 已尝试:."""
    from irc.opportunity.types import LookthroughTarget
    row = OpportunityRow(
        instrument_id="510300", name_cn="x", asset_class="cn_etf", theme=None,
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=(),
    )
    assert row.fetch_types_attempted == ()


def test_opportunity_row_accepts_fetch_types_attempted_kwarg():
    """OpportunityRow.fetch_types_attempted can be set to a non-empty tuple."""
    from irc.opportunity.types import LookthroughTarget
    row = OpportunityRow(
        instrument_id="510300", name_cn="x", asset_class="cn_etf", theme=None,
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=(),
        fetch_types_attempted=("filing", "broker"),
    )
    assert row.fetch_types_attempted == ("filing", "broker")


def test_citation_id_uses_summary_fallback_when_url_empty():
    """When url='', summary[:64] is mixed into the preimage so two empty-URL
    filings with different content but same source/date/instrument get distinct ids."""
    a = ThesisEvidence(**_evidence_kwargs(url="", summary="FY24-Q3 营收 +12%"))
    b = ThesisEvidence(**_evidence_kwargs(url="", summary="FY24-Q4 营收 -5%"))
    assert a.citation_id != b.citation_id


# ── Item 003: LookthroughTarget.provider_symbol tests ────────────────────────

def test_lookthrough_target_provider_symbol_default_empty() -> None:
    t = LookthroughTarget("broad_index", "csi300", "沪深300")
    assert t.provider_symbol == ""


def test_lookthrough_target_provider_symbol_explicit() -> None:
    t = LookthroughTarget(
        kind="active_fund", key="fund_005827",
        display_cn="易方达蓝筹精选", provider_symbol="005827",
    )
    assert t.provider_symbol == "005827"
