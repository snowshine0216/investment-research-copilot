from __future__ import annotations

from unittest.mock import MagicMock, patch

from irc.scoring.factors.macro_fit import MacroFitContext, score_macro_fit


def _ctx() -> MacroFitContext:
    return MacroFitContext(
        regime_summary="Real yield 1.65%, DXY 104, mild risk-on",
        instrument_profile="VTI: broad US equity, beta ~1, USD-denominated",
        raw_refs=("openbb:macro_series:DGS10:2026-05-06",),
    )


@patch("irc.scoring.factors.macro_fit.call_chat")
def test_macro_fit_parses_score(mock_chat) -> None:
    mock_chat.return_value = MagicMock(
        text='{"score": 72, "rationale": "rates stable, USD steady"}',
        prompt_tokens=20, completion_tokens=10,
    )
    s, resp = score_macro_fit(_ctx(), route=MagicMock())
    assert s.score == 72
    assert resp is not None  # ChatResponse returned for usage tracking
    assert resp.prompt_tokens == 20


@patch("irc.scoring.factors.macro_fit.call_chat")
def test_macro_fit_invalid_json_returns_neutral(mock_chat) -> None:
    mock_chat.return_value = MagicMock(
        text="not json", prompt_tokens=5, completion_tokens=2,
    )
    s, resp = score_macro_fit(_ctx(), route=MagicMock())
    assert s.score == 50  # neutral fallback
    assert "fallback" in s.components
    # resp still returned (billed call even though JSON was bad)
    assert resp is not None


def test_macro_fit_no_route_returns_neutral_no_response() -> None:
    s, resp = score_macro_fit(_ctx(), route=None)
    assert s.score == 50
    assert resp is None
