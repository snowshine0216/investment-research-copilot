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
    assert "触发条件为纪律性执行阈值" in out
    assert "不构成对标的价格走势的预测或判断" in out
    assert "QDII标的执行前须查阅二级市场溢价/折价" in out


def test_section7_falls_back_to_placeholder_when_no_execution_lines():
    out = render_skeleton(_inputs(()))
    assert "由AI合成器填充" in out
    assert "IRC_EXECUTION_LINES_BEGIN" not in out


def test_section5_title_discloses_observation_rows():
    out = render_skeleton(_inputs(()))
    assert "## 5. 精选标的（含观察标的）" in out


def test_compose_execution_lines_picks_name_from_opportunity_rows():
    trades = [{
        "target": "000369",
        "target_weight": 0.088,
        "buy_method": "small_account_anchor",
        "granularity": "default",
        "triggers": [{
            "name": "weekly_drawdown_4pct",
            "data_field": "instrument.weekly_return",
            "comparator": "<=",
            "threshold": -0.04,
        }],
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


def test_compose_execution_lines_suspends_trade_without_opportunity_row():
    """Production memo output must not give actionable triggers to a trade
    target missing from opportunity_report.json."""
    trades = [{
        "target": "017641",
        "target_weight": 0.0667,
        "buy_method": "small_account_anchor",
        "granularity": "default",
        "triggers": [{
            "name": "vix_high",
            "data_field": "macro.vix",
            "comparator": ">",
            "threshold": 25.0,
        }],
        "venue_note": "direct match",
    }]
    lines = _compose_execution_lines(
        trades, [],
        extra_names={"017641": "摩根标普500指数(QDII)人民币A"},
        require_opportunity_row=True,
    )
    assert len(lines) == 1
    assert "017641 摩根标普500指数(QDII)人民币A" in lines[0]
    assert "暂缓执行·待机会数据补充" in lines[0]
    assert "vix_high" not in lines[0]


def test_compose_execution_lines_removes_proxy_from_suspended_trade():
    trades = [{
        "target": "000297",
        "target_weight": 0.035,
        "buy_method": "small_account_anchor",
        "granularity": "default",
        "triggers": [],
        "venue_note": "venue mismatch; proxy via 000297 (鹏华可转债债券A) [cn_bond_fund]",
    }]
    lines = _compose_execution_lines(
        trades, [],
        extra_names={"000297": "鹏华可转债债券A"},
        require_opportunity_row=True,
    )
    assert "暂缓执行·待机会数据补充" in lines[0]
    assert "proxy via" not in lines[0]
    assert "无可用代理渠道" in lines[0]


def test_compose_execution_lines_renders_trigger_data_field_comparator_threshold():
    """Audit P4 — render each trigger as `name (data_field comparator threshold)`
    so the bare code is not the only thing executors see."""
    trades = [{
        "target": "cmb_paper_gold",
        "target_weight": 0.2,
        "buy_method": "gold_anchor_plus_band",
        "granularity": "default",
        "triggers": [
            {"name": "real_yield_low", "data_field": "macro.real_yield_10y_tips",
             "comparator": "<=", "threshold": 0.0},
            {"name": "weekly_drawdown_4pct", "data_field": "instrument.weekly_return",
             "comparator": "<=", "threshold": -0.04},
        ],
        "venue_note": "venue mismatch",
    }]
    lines = _compose_execution_lines(trades, [])
    assert len(lines) == 1
    # data_field, comparator, and threshold all visible per trigger:
    assert "macro.real_yield_10y_tips <= 0.0" in lines[0]
    assert "instrument.weekly_return <= -0.04" in lines[0]


def test_compose_execution_lines_emits_or_semantics_header_when_multiple_triggers():
    """Audit P4 — clarify trigger logic (OR vs AND). Triggers in trade_plan
    are independent — 满足任一 should fire — so render with an explicit
    '满足任一' (any-of) marker."""
    trades = [{
        "target": "X",
        "target_weight": 0.05,
        "buy_method": "dca_normal",
        "granularity": "default",
        "triggers": [
            {"name": "vix_high", "data_field": "macro.vix",
             "comparator": ">", "threshold": 25.0},
            {"name": "weekly_drawdown_4pct", "data_field": "instrument.weekly_return",
             "comparator": "<=", "threshold": -0.04},
        ],
        "venue_note": "",
    }]
    lines = _compose_execution_lines(trades, [])
    assert "满足任一" in lines[0]


def test_compose_execution_lines_no_or_marker_for_single_trigger():
    """With one trigger, the 满足任一 marker is misleading — omit it."""
    trades = [{
        "target": "X",
        "target_weight": 0.05,
        "buy_method": "dca_normal",
        "granularity": "default",
        "triggers": [
            {"name": "vix_high", "data_field": "macro.vix",
             "comparator": ">", "threshold": 25.0},
        ],
        "venue_note": "",
    }]
    lines = _compose_execution_lines(trades, [])
    assert "满足任一" not in lines[0]
    assert "vix_high (macro.vix > 25.0)" in lines[0]


def test_compose_execution_lines_threshold_missing_does_not_render_literal_None():
    """Latent bug from review: a yaml trigger with no ``threshold`` key
    would render as ``... <= None`` and surface the Python literal to the
    auditor. Missing threshold must use a human-readable placeholder."""
    trades = [{
        "target": "X",
        "target_weight": 0.05,
        "buy_method": "dca_normal",
        "granularity": "default",
        "triggers": [
            {"name": "vix_high", "data_field": "macro.vix", "comparator": ">"},
        ],
        "venue_note": "",
    }]
    lines = _compose_execution_lines(trades, [])
    assert "None" not in lines[0]
    assert "（未设阈值）" in lines[0]


def test_compose_execution_lines_threshold_string_value_renders_verbatim():
    """Triggers can carry categorical (string) thresholds — render them
    without trying to format as float."""
    trades = [{
        "target": "X",
        "target_weight": 0.05,
        "buy_method": "dca_normal",
        "granularity": "default",
        "triggers": [
            {"name": "valuation_cheap", "data_field": "valuation_state",
             "comparator": "==", "threshold": "cheap"},
        ],
        "venue_note": "",
    }]
    lines = _compose_execution_lines(trades, [])
    assert "valuation_state == cheap" in lines[0]


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
