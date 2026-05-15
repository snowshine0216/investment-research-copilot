from __future__ import annotations
import pytest
from dataclasses import FrozenInstanceError

from irc.opportunity.types import (
    LookthroughTarget,
    OpportunityInput,
    OpportunityRow,
    ThesisCard,
    ThesisEvidence,
    DisciplineRow,
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
    )
    assert ev.type == "filing"
    with pytest.raises(FrozenInstanceError):
        ev.source = "x"  # type: ignore[misc]


def test_thesis_evidence_type_must_be_known_kind():
    """Allowed kinds: filing | broker | news | policy | snapshot."""
    for kind in ("filing", "broker", "news", "policy", "snapshot"):
        ev = ThesisEvidence(type=kind, source="s", url="u", date="d", summary="x")
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
