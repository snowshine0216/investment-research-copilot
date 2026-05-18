from __future__ import annotations

from irc.memo.template import MemoInputs, render_skeleton
from irc.commands.memo_cmd import _compose_execution_lines


def _inputs(execution_lines: tuple[str, ...]) -> MemoInputs:
    return MemoInputs(
        date_str="2026-05-18",
        gold_regime="range_bound",
        gold_zone="normal",
        gold_tilt="neutral",
        allocation_mode="build",
        macro_summary="(stub)",
        top_picks=("X1",),
        risk_notes=("stub-risk",),
        tldr_lines=("stub-tldr",),
        picks_table_md="",
        execution_lines=execution_lines,
    )


def test_section7_renders_each_execution_line_as_bullet():
    inputs = _inputs((
        "**X1 测试基金A** | 目标权重 ≤ 5.0% | 建仓方式 dca_normal (default) | 触发 vix_high | 渠道 direct",
        "**X2 测试基金B** | 目标权重 ≤ 3.0% | 建仓方式 small_account_anchor (default) | 触发 weekly_drawdown_4pct | 渠道 direct",
    ))
    out = render_skeleton(inputs)
    assert "测试基金A" in out
    assert "测试基金B" in out
    assert "weekly_drawdown_4pct" in out
    assert "IRC_EXECUTION_LINES_BEGIN" in out
    assert "IRC_EXECUTION_LINES_END" in out
    assert "由AI合成器填充" not in out  # placeholder replaced


def test_section7_falls_back_to_placeholder_when_no_execution_lines():
    out = render_skeleton(_inputs(()))
    assert "由AI合成器填充" in out
    assert "IRC_EXECUTION_LINES_BEGIN" not in out


def test_compose_execution_lines_picks_name_from_opportunity_rows():
    trades = [{
        "target": "000369",
        "target_weight": 0.088,
        "buy_method": "small_account_anchor",
        "granularity": "default",
        "triggers": [{"name": "weekly_drawdown_4pct", "data_field": "...", "comparator": "<=", "threshold": -0.04}],
        "venue_note": "direct match",
    }]
    opp_rows = [{"instrument_id": "000369", "name_cn": "广发全球医疗保健指数人民币(QDII)A"}]
    lines = _compose_execution_lines(trades, opp_rows)
    assert len(lines) == 1
    assert "000369 广发全球医疗保健指数人民币(QDII)A" in lines[0]
    assert "8.8%" in lines[0]
    assert "small_account_anchor" in lines[0]
    assert "weekly_drawdown_4pct" in lines[0]
    assert "direct match" in lines[0]


def test_compose_execution_lines_renders_no_triggers_as_无():
    trades = [{
        "target": "X",
        "target_weight": 0.05,
        "buy_method": "lump_sum",
        "granularity": "default",
        "triggers": [],
        "venue_note": "",
    }]
    lines = _compose_execution_lines(trades, [])
    assert len(lines) == 1
    assert "触发 无" in lines[0]


def test_compose_execution_lines_returns_empty_when_no_trades():
    assert _compose_execution_lines([], []) == ()
