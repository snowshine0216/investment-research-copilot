from __future__ import annotations

import dataclasses

from irc.opportunity.types import OpportunityInput


def test_consensus_upside_pct_field_exists_and_defaults_none() -> None:
    inp = OpportunityInput(
        instrument_id="600519",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
    )
    assert inp.consensus_upside_pct is None


def test_consensus_upside_pct_is_float_or_none_field() -> None:
    fields = {f.name: f for f in dataclasses.fields(OpportunityInput)}
    assert "consensus_upside_pct" in fields
    # Ratio units (median/close - 1) per ADR 0009 / CONTEXT.md "Valuation inputs".
    assert "float" in str(fields["consensus_upside_pct"].type)
