"""AC7: memo §6 风险提示 emits a deterministic 证据缺口 bullet inside
<!-- IRC_EVIDENCE_GAP_BEGIN/END --> markers when ≥1 pick carries
top_holdings_broker_thin."""
from __future__ import annotations

from irc.memo.picks_table import PickRow


def _pick(iid: str, name: str, *, advisory: tuple[str, ...] = ()) -> PickRow:
    return PickRow(
        instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
        role="alpha", target_weight=0.05, composite_score=70.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        advisory_gaps=advisory,
    )


def test_compose_evidence_gap_lines_returns_empty_when_no_qualifying_picks():
    from irc.commands.memo_cmd import _compose_evidence_gap_lines
    rows = [_pick("A", "甲"), _pick("B", "乙")]
    assert _compose_evidence_gap_lines(rows) == ()


def test_compose_evidence_gap_lines_emits_marker_block_when_one_pick_qualifies():
    from irc.commands.memo_cmd import _compose_evidence_gap_lines
    rows = [
        _pick("005827", "易方达蓝筹精选", advisory=("top_holdings_broker_thin",)),
        _pick("510300", "沪深300ETF"),
    ]
    lines = _compose_evidence_gap_lines(rows)
    assert lines
    joined = "\n".join(lines)
    assert "<!-- IRC_EVIDENCE_GAP_BEGIN -->" in joined
    assert "<!-- IRC_EVIDENCE_GAP_END -->" in joined
    assert "证据缺口（Top-5 经纪覆盖不足）" in joined
    assert "005827 易方达蓝筹精选" in joined
    # 510300 must NOT appear (it does not carry the advisory gap).
    assert "510300" not in joined


def test_compose_evidence_gap_lines_sorts_picks_by_instrument_id_ascending():
    from irc.commands.memo_cmd import _compose_evidence_gap_lines
    rows = [
        _pick("510300", "B", advisory=("top_holdings_broker_thin",)),
        _pick("005827", "A", advisory=("top_holdings_broker_thin",)),
    ]
    lines = _compose_evidence_gap_lines(rows)
    joined = "\n".join(lines)
    # 005827 must appear before 510300 (ASCII sort, all-digit ids).
    assert joined.index("005827") < joined.index("510300")


def test_evidence_gap_lines_render_through_skeleton_into_section_6():
    """Integration: a non-empty evidence_gap_lines tuple flows through
    `MemoInputs.risk_notes` (prepended) and renders inside §6."""
    from irc.memo.template import MemoInputs, render_skeleton
    inputs = MemoInputs(
        date_str="2026-05-27", gold_regime="—", gold_zone="—", gold_tilt="—",
        allocation_mode="build", macro_summary="—", top_picks=(),
        risk_notes=(
            "<!-- IRC_EVIDENCE_GAP_BEGIN -->",
            "证据缺口（Top-5 经纪覆盖不足）：005827 易方达蓝筹精选。",
            "<!-- IRC_EVIDENCE_GAP_END -->",
            "其他风险条目。",
        ),
        tldr_lines=(),
    )
    md = render_skeleton(inputs)
    # The marker block + the regular risk note both appear in §6.
    assert "## 6. 风险提示" in md
    assert "<!-- IRC_EVIDENCE_GAP_BEGIN -->" in md
    assert "其他风险条目" in md
