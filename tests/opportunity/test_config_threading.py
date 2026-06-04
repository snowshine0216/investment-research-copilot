from __future__ import annotations

from unittest.mock import MagicMock, patch

from irc.opportunity.inputs_build import _build_input
from irc.fundamentals.provider import AkShareProvider
from irc.schemas.valuation import ActiveFundLookthroughConfig


def test_lookthrough_cfg_reaches_populate_inputs() -> None:
    """The config value threaded into _build_input must arrive at
    populate_inputs as the lookthrough_cfg kwarg — no global lookup (§6.2)."""
    score_row = {"instrument_id": "012345", "asset_class": "cn_equity_fund", "role": ""}
    con = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = True
    con.execute.return_value.fetchdf.return_value = fake_df
    cfg = ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.42)

    with patch("irc.opportunity.inputs_build.populate_inputs") as mock_pop:
        _build_input(
            score_row, None, None, None, 0.0, set(), con,
            provider=AkShareProvider(), lookthrough_cfg=cfg,
        )
    _, kwargs = mock_pop.call_args
    assert kwargs["lookthrough_cfg"] is cfg


def test_build_input_default_lookthrough_cfg_is_disabled() -> None:
    """Existing callers that omit lookthrough_cfg get a disabled config."""
    score_row = {"instrument_id": "012345", "asset_class": "cn_equity_fund", "role": ""}
    con = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = True
    con.execute.return_value.fetchdf.return_value = fake_df

    with patch("irc.opportunity.inputs_build.populate_inputs") as mock_pop:
        _build_input(
            score_row, None, None, None, 0.0, set(), con, provider=AkShareProvider(),
        )
    _, kwargs = mock_pop.call_args
    assert kwargs["lookthrough_cfg"].enabled is False
