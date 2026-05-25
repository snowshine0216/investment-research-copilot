from __future__ import annotations

from irc.opportunity.states import compose_opportunity_state


def test_pause_wait_reason_avoids_directional_wait_for_pullback_language() -> None:
    state, reason = compose_opportunity_state(
        valuation="expensive",
        heat="crowded",
        thesis="intact",
        product_quality="acceptable",
    )
    assert state == "pause_wait"
    assert "等待回落" not in reason
    assert "如估值或热度回到规则阈值内再评估" in reason
