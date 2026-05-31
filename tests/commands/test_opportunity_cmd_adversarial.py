"""Item 005 — --adversarial bull/bear debate (advisory file)."""
from __future__ import annotations

import json
import re
from unittest.mock import MagicMock, patch

from irc.opportunity.discipline import PositionContext


def _row(iid, name_cn="x", opportunity_state="core_dca", evidence_gaps=()):
    """Mirrors tests/commands/test_opportunity_cmd_h3_invariant.py::_row."""
    from irc.fundamentals.types import ThesisEvidence
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    if not evidence_gaps:
        ev = (
            ThesisEvidence(
                type="filing", source="src", url=f"https://x/{iid}/d", date="2024-04-15",
                summary="data leg", scope="instrument", citation_kind="data",
                owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
            ThesisEvidence(
                type="filing", source="src", url=f"https://x/{iid}/i", date="2024-04-16",
                summary="info leg", scope="instrument", citation_kind="information",
                owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
        )
    else:
        ev = ()
    return OpportunityRow(
        instrument_id=iid, name_cn=name_cn, asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget("active_fund", f"fund_{iid}", name_cn, iid),
        valuation_state="evidence_insufficient", heat_state="evidence_insufficient",
        thesis_state="intact", product_quality_state="evidence_insufficient",
        opportunity_state=opportunity_state, opportunity_reason="r",
        evidence_gaps=evidence_gaps, thesis_evidence=ev,
    )


def _position():
    return PositionContext(
        portfolio_weight=None, target_band_low=None, target_band_high=None,
        drawdown_since_entry=None, is_holding=False,
    )


def _read_report(tmp_path):
    return json.loads((tmp_path / "opportunity_report.json").read_text(encoding="utf-8"))


_CANONICAL = {
    "opportunity_report.json", "thesis_cards.yaml", "discipline_report.md", "rejections.json",
}


@patch("irc.commands.opportunity_cmd.run_debates")
def test_flag_off_writes_no_debate_and_no_llm_call(mock_debates, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=None,
    )
    assert not (tmp_path / "thesis_debate.md").exists()
    mock_debates.assert_not_called()
    written = {p.name for p in tmp_path.glob("*") if p.is_file()}
    assert _CANONICAL.issubset(written)


def test_flag_off_byte_identical_default_call(tmp_path):
    # Default (no debate_route kwarg) must behave exactly like today.
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
    )
    assert not (tmp_path / "thesis_debate.md").exists()


@patch("irc.opportunity.debate.call_chat")
def test_flag_on_writes_debate_and_runs_both_halves(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')
    pub = [_row("A"), _row("B")]
    gapped = _row("G", evidence_gaps=("qdii_information_unavailable",))
    _write_opportunity_outputs(
        kept_rows=pub + [gapped],
        positions={"A": _position(), "B": _position(), "G": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    md = (tmp_path / "thesis_debate.md").read_text(encoding="utf-8")
    assert "### A x" in md and "### B x" in md
    assert "### G" not in md  # gapped rows get no debate
    # 2 publishable rows × (defend + falsify) = 4 calls.
    assert mock_chat.call_count == 4


@patch("irc.opportunity.debate.call_chat")
def test_debate_file_not_a_canonical_artifact(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    assert "thesis_debate.md" not in _CANONICAL
    assert (tmp_path / "thesis_debate.md").exists()


@patch("irc.opportunity.debate.call_chat")
def test_per_row_failure_renders_placeholder_and_keeps_canonical(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.side_effect = RuntimeError("llm down")
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    md = (tmp_path / "thesis_debate.md").read_text(encoding="utf-8")
    assert "（本行未能生成辩论）" in md
    # Canonical artifacts still written despite LLM failure.
    assert (tmp_path / "opportunity_report.json").exists()
    assert (tmp_path / "thesis_cards.yaml").exists()


@patch("irc.opportunity.debate.call_chat")
def test_canonical_artifacts_byte_identical_with_vs_without_flag(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')

    off = tmp_path / "off"
    on = tmp_path / "on"
    for d in (off, on):
        d.mkdir()

    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=off, today="2026-05-23",
    )
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=on, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    for name in _CANONICAL:
        assert (off / name).read_bytes() == (on / name).read_bytes(), name
    # The ON dir additionally has the advisory file; the OFF dir does not.
    assert (on / "thesis_debate.md").exists()
    assert not (off / "thesis_debate.md").exists()


@patch("irc.opportunity.debate.call_chat")
def test_debate_file_introduces_no_citation_id(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(
        text='{"arguments": ["see [ref:abc] prose"], "conditions": ["c"]}'
    )
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    md = (tmp_path / "thesis_debate.md").read_text(encoding="utf-8")
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", md)
