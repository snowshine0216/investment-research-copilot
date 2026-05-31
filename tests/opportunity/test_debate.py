from __future__ import annotations
from unittest.mock import patch, MagicMock

from irc.opportunity.debate import (
    DefenseResult,
    FalsificationResult,
    run_defend,
    run_falsify,
)


def _row(iid="X1", name_cn="测试基金", thesis_state="intact",
         opportunity_reason="长期逻辑完整", evidence_summaries=("证据A", "证据B")):
    from irc.fundamentals.types import ThesisEvidence
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    evidence = tuple(
        ThesisEvidence(
            type="filing", source="src", url=f"https://x/{iid}/{i}", date="2024-04-15",
            summary=s, scope="instrument", citation_kind="data",
            owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
            holding_weight_pct=None,
        )
        for i, s in enumerate(evidence_summaries)
    )
    return OpportunityRow(
        instrument_id=iid, name_cn=name_cn, asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget("active_fund", f"fund_{iid}", name_cn, iid),
        valuation_state="fair", heat_state="normal", thesis_state=thesis_state,
        product_quality_state="acceptable", opportunity_state="core_dca",
        opportunity_reason=opportunity_reason, evidence_gaps=(),
        thesis_evidence=evidence,
    )


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_parses_arguments(mock_chat):
    mock_chat.return_value = MagicMock(text='{"arguments": ["盈利持续", "估值合理"]}')
    out = run_defend(_row(), route=MagicMock())
    assert isinstance(out, DefenseResult)
    assert out.arguments == ("盈利持续", "估值合理")


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_invalid_json_returns_empty(mock_chat):
    mock_chat.return_value = MagicMock(text="not json")
    assert run_defend(_row(), route=MagicMock()).arguments == ()


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_raises_returns_empty(mock_chat):
    mock_chat.side_effect = RuntimeError("boom")
    assert run_defend(_row(), route=MagicMock()).arguments == ()


@patch("irc.opportunity.debate.call_chat")
def test_run_falsify_parses_conditions(mock_chat):
    mock_chat.return_value = MagicMock(text='{"conditions": ["盈利转负"]}')
    out = run_falsify(_row(), route=MagicMock())
    assert isinstance(out, FalsificationResult)
    assert out.conditions == ("盈利转负",)


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_sanitizes_newlines_and_caps(mock_chat):
    long = "a" * 400
    mock_chat.return_value = MagicMock(text='{"arguments": ["line1\\nline2", "%s"]}' % long)
    out = run_defend(_row(), route=MagicMock())
    assert "\n" not in out.arguments[0]
    assert len(out.arguments[1]) == 300


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_caps_item_count(mock_chat):
    items = ", ".join(['"x"'] * 20)
    mock_chat.return_value = MagicMock(text='{"arguments": [%s]}' % items)
    assert len(run_defend(_row(), route=MagicMock()).arguments) <= 10


from irc.opportunity.debate import ThesisDebate, pair_debate, run_debates


def test_pair_debate_is_pure():
    row = _row(iid="P1", thesis_state="intact")
    d = DefenseResult(arguments=("a",))
    f = FalsificationResult(conditions=("c",))
    debate = pair_debate(row, d, f)
    assert isinstance(debate, ThesisDebate)
    assert debate.instrument_id == "P1"
    assert debate.thesis_state == "intact"
    assert debate.defense == d
    assert debate.falsification == f


@patch("irc.opportunity.debate.call_chat")
def test_run_debates_calls_both_halves_per_row(mock_chat):
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')
    rows = [_row(iid="R1"), _row(iid="R2")]
    debates = run_debates(rows, routes=(MagicMock(), MagicMock()))
    # 2 rows × (defend + falsify) = 4 calls.
    assert mock_chat.call_count == 4
    assert len(debates) == 2
    assert {d.instrument_id for d in debates} == {"R1", "R2"}


@patch("irc.opportunity.debate.call_chat")
def test_run_debates_isolates_per_row_failure(mock_chat):
    # First row's defend raises; the run must still produce 2 debates.
    calls = {"n": 0}

    def _side(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("row1 defend down")
        return MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')

    mock_chat.side_effect = _side
    debates = run_debates([_row(iid="R1"), _row(iid="R2")], routes=(MagicMock(), MagicMock()))
    assert len(debates) == 2
    # R1's defense degraded to empty, falsify still ran.
    r1 = next(d for d in debates if d.instrument_id == "R1")
    assert r1.defense.arguments == ()
