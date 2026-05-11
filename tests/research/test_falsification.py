from __future__ import annotations
from unittest.mock import patch, MagicMock
from irc.research.falsification import generate_falsification, FalsificationResult


@patch("irc.research.falsification.call_chat")
def test_falsification_returns_list(mock_chat):
    mock_chat.return_value = MagicMock(
        text='{"conditions": ["Fed hikes 50bps", "DXY breaks 115"]}',
        prompt_tokens=50, completion_tokens=20,
    )
    out = generate_falsification(thesis_summary="Gold should outperform", route=MagicMock())
    assert isinstance(out, FalsificationResult)
    assert "Fed hikes 50bps" in out.conditions
    assert len(out.conditions) == 2


@patch("irc.research.falsification.call_chat")
def test_falsification_invalid_json_returns_empty(mock_chat):
    mock_chat.return_value = MagicMock(text="not json", prompt_tokens=5, completion_tokens=2)
    out = generate_falsification(thesis_summary="x", route=MagicMock())
    assert out.conditions == ()
