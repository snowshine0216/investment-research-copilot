from __future__ import annotations

from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.types import LookthroughTarget, OpportunityRow


def _row(**overrides) -> OpportunityRow:
    base = dict(
        instrument_id="512760",
        name_cn="国泰CES半导体芯片行业ETF",
        asset_class="cn_etf",
        theme="semiconductor",
        lookthrough_target=LookthroughTarget("sector_theme", "semiconductor", "半导体"),
        valuation_state="reasonable_low",
        heat_state="crowded",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="pause_wait",
        opportunity_reason="估值合理但热度偏高，暂不追高。",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def _pos(weight: float = 0.05, band_high: float = 0.10) -> PositionContext:
    return PositionContext(
        portfolio_weight=weight,
        target_band_low=0.0,
        target_band_high=band_high,
        drawdown_since_entry=None,
        is_holding=True,
    )


def test_card_includes_required_fields():
    card = build_thesis_card(
        row=_row(),
        position=_pos(),
        role="satellite_cn_semiconductor",
        entry_reason="国产替代与周期复苏逻辑。",
    )
    assert card.instrument_id == "512760"
    assert card.theme == "semiconductor"
    assert card.role == "satellite_cn_semiconductor"
    assert card.review_cadence == "weekly_light_monthly_full"


def test_card_falsification_triggers_include_thesis_and_product():
    card = build_thesis_card(row=_row(), position=_pos(), role="x", entry_reason="x")
    assert "theme thesis moves to falsified" in card.falsification_triggers
    assert "product quality moves to poor" in card.falsification_triggers


def test_card_trim_triggers_cover_expensive_crowded_and_overweight():
    card = build_thesis_card(row=_row(), position=_pos(), role="x", entry_reason="x")
    joined = " | ".join(card.trim_triggers)
    assert "expensive" in joined
    assert "crowded" in joined or "overheated" in joined
    assert "weight" in joined or "band" in joined


def test_card_records_do_not_sell_just_because_drawdown():
    card = build_thesis_card(row=_row(), position=_pos(), role="x", entry_reason="x")
    assert any("0.20" in trigger for trigger in card.do_not_sell_just_because)


def test_card_propagates_evidence_gaps():
    row = _row(evidence_gaps=("valuation", "product_quality"))
    card = build_thesis_card(row=row, position=_pos(), role="x", entry_reason="x")
    assert card.evidence_gaps == ("valuation", "product_quality")


def test_card_dca_and_risk_actions_match_state():
    """Cards built from a pause_wait row should not say accelerate_dca."""
    card = build_thesis_card(
        row=_row(opportunity_state="pause_wait"),
        position=_pos(),
        role="x", entry_reason="x",
    )
    assert card.dca_action in ("pause_dca", "slow_dca")
