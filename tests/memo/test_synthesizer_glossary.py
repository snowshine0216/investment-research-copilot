from __future__ import annotations

from unittest.mock import patch

from irc.memo.synthesizer import synthesize_memo


def test_synthesize_memo_user_prompt_includes_cost_grade_glossary() -> None:
    """The synthesizer must prime the LLM with a glossary that distinguishes
    the price-percentile bucket (carried in 状态=A/B/C/D) from the cost_grade
    factor score. Without this glossary the LLM collapses both into one
    "valuation" axis — exactly the 2026-05-18 audit finding on 000105
    ("estimated cheap" narrative vs cost_grade=85). The check below makes
    sure future prompt edits don't silently drop the disambiguation.
    """
    captured: dict[str, object] = {}

    def fake_call_chat(route, messages, temperature):
        captured["messages"] = messages
        # Return a minimal ChatResponse-shaped object.
        class _R:
            text = "stub"
            prompt_tokens = 0
            completion_tokens = 0
        return _R()

    with patch("irc.memo.synthesizer.call_chat", side_effect=fake_call_chat):
        synthesize_memo(skeleton="# stub", raw_ref_pool=["ref-1"], route=None)  # type: ignore[arg-type]

    msgs = captured["messages"]
    user_msg = next(m for m in msgs if m["role"] == "user")["content"]
    assert "cost_grade" in user_msg
    assert "字段说明" in user_msg
    # The glossary must explicitly call out that cost_grade and 状态's
    # valuation bucket are independent — that's the load-bearing claim.
    assert "独立" in user_msg or "不等于" in user_msg
