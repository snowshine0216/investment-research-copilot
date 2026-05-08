from __future__ import annotations

from unittest.mock import MagicMock, patch

from irc.discovery.universe import UniverseRow
from irc.discovery.reason_writer import ReasonResult, WriteReasonContext, write_reason


def _ctx() -> WriteReasonContext:
    return WriteReasonContext(
        role="core_us_equity",
        peer_summary="VTI/VOO are broad-market US ETF passive proxies",
        macro_snapshot="Real yield ~1.65%, DXY ~104",
        raw_refs=("openbb:prices:VTI:2026-05-07", "openbb:macro_series:DGS10:2026-05-06"),
    )


def _row() -> UniverseRow:
    return UniverseRow(
        instrument_id="VTI", ticker="VTI", market="cn_off_exchange",
        name_cn="易方达标普500", asset_class="us_etf", currency="cny",
        tracked_index="S&P 500", venue_required=(),
    )


@patch("irc.discovery.reason_writer.call_chat")
def test_write_reason_returns_3_sentences_plus_risk(mock_chat) -> None:
    mock_chat.return_value = MagicMock(
        text=(
            "Tracks S&P 500 (openbb:prices:VTI:2026-05-07). "
            "Low expense ratio. Solid AUM. Risk: USD strength can compress returns."
        ),
        prompt_tokens=120, completion_tokens=40,
    )
    res = write_reason(_row(), _ctx(), route=MagicMock(), max_retries=0)
    assert isinstance(res, ReasonResult)
    assert "Risk:" in res.reason_text
    assert len(res.cited_refs) >= 1


@patch("irc.discovery.reason_writer.call_chat")
def test_write_reason_drops_when_no_raw_ref_cited(mock_chat) -> None:
    mock_chat.return_value = MagicMock(
        text="A fine ETF. Risk: none.", prompt_tokens=10, completion_tokens=5,
    )
    res = write_reason(_row(), _ctx(), route=MagicMock(), max_retries=0)
    assert res is None  # no citation → dropped
