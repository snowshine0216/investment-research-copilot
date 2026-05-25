from __future__ import annotations

from irc.commands.memo_cmd import _derive_tldr_lines
from irc.memo.picks_table import PickRow


def _pick(iid: str, decision_status: str = "watch_only") -> PickRow:
    return PickRow(
        instrument_id=iid, name_cn=f"{iid}_name", asset_class="x",
        role="r", target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="r",
        decision_status=decision_status,
    )


def test_tldr_banner_actionable_buy_prefix_when_picks_present() -> None:
    """When ≥1 PickRow has decision_status='actionable_buy', TL;DR first
    line is the ✅ banner listing instrument ids."""
    picks = [
        _pick("003318", decision_status="actionable_buy"),
        _pick("519770", decision_status="actionable_buy"),
        _pick("161716", decision_status="blocked"),
    ]
    lines = _derive_tldr_lines(
        gold={"regime": "downtrend", "zone": "normal"},
        alloc={"gold_tilt": "neutral_plus"},
        opportunity={"summary": {"core_dca_count": 0, "small_watch_count": 24, "pause_wait_count": 44}},
        plan={"mode": "build"},
        pick_rows=picks,
    )
    assert lines[0].startswith("✅"), f"expected ✅ banner, got: {lines[0]}"
    assert "003318" in lines[0]
    assert "519770" in lines[0]
    assert "161716" not in lines[0]
    assert "候选可执行" in lines[0]


def test_tldr_banner_no_action_when_zero_actionable() -> None:
    """When zero picks are actionable_buy, TL;DR first line is the ⚪ banner."""
    picks = [
        _pick("161716", decision_status="blocked"),
        _pick("017641", decision_status="watch_only"),
    ]
    lines = _derive_tldr_lines(
        gold={"regime": "downtrend", "zone": "normal"},
        alloc={"gold_tilt": "neutral_plus"},
        opportunity={"summary": {"core_dca_count": 0, "small_watch_count": 0, "pause_wait_count": 2}},
        plan={"mode": "build"},
        pick_rows=picks,
    )
    assert lines[0].startswith("⚪"), f"expected ⚪ banner, got: {lines[0]}"
    assert "无候选可执行" in lines[0]


def test_tldr_banner_no_picks_at_all_still_renders_no_action() -> None:
    """Edge case: empty pick_rows tuple still produces the ⚪ banner."""
    lines = _derive_tldr_lines(
        gold={"regime": "downtrend", "zone": "normal"},
        alloc={"gold_tilt": "neutral_plus"},
        opportunity={"summary": {}},
        plan={"mode": "build"},
        pick_rows=[],
    )
    assert lines[0].startswith("⚪")


def test_tldr_keeps_existing_three_lines_after_banner() -> None:
    """Banner is PREPENDED; the existing 3 lines (gold/mode/opportunity counts)
    follow it."""
    picks = [_pick("003318", decision_status="actionable_buy")]
    lines = _derive_tldr_lines(
        gold={"regime": "downtrend", "zone": "normal"},
        alloc={"gold_tilt": "neutral_plus"},
        opportunity={"summary": {"core_dca_count": 1, "small_watch_count": 2, "pause_wait_count": 3}},
        plan={"mode": "build"},
        pick_rows=picks,
    )
    assert len(lines) == 4
    assert "黄金" in lines[1]
    assert "建仓模式" in lines[2]
    assert "机会面" in lines[3]
