from __future__ import annotations
from irc.memo.template import MemoInputs, render_skeleton


def _inputs() -> MemoInputs:
    return MemoInputs(
        date_str="2026-05-08", gold_regime="bull", gold_zone="normal",
        gold_tilt="overweight", allocation_mode="hybrid",
        macro_summary="通胀高企，实际利率走低", top_picks=["518880", "006075"],
        risk_notes=["美联储加息风险"], tldr_lines=["黄金超配，美股均配"],
    )


def test_render_contains_7_sections():
    md = render_skeleton(_inputs())
    assert md.count("## ") == 7


def test_render_contains_date():
    md = render_skeleton(_inputs())
    assert "2026-05-08" in md


def test_render_skeleton_includes_global_compliance_statement_before_tldr():
    md = render_skeleton(_inputs())
    assert "【合规声明】" in md
    assert "不构成任何形式的投资建议或收益承诺" in md
    assert md.index("【合规声明】") < md.index("## 1. TL;DR")


def test_render_top_picks_listed():
    md = render_skeleton(_inputs())
    assert "518880" in md
    assert "006075" in md


def test_render_skeleton_inlines_picks_table_md_and_no_placeholder():
    inputs = MemoInputs(
        date_str="2026-05-16",
        gold_regime="range_bound",
        gold_zone="pause",
        gold_tilt="neutral_minus",
        allocation_mode="build",
        macro_summary="实际利率维持高位，黄金区间震荡。",
        top_picks=("dummy",),
        risk_notes=("利率风险",),
        tldr_lines=("黄金保持现状", "权益分批"),
        picks_table_md="| 代码 | 名称 |\n|---|---|\n| 518880 | 华安黄金ETF |",
    )
    md = render_skeleton(inputs)
    assert "## 5. 精选标的" in md
    assert "| 518880 | 华安黄金ETF |" in md
    assert "（待填写）" not in md
    assert "由AI合成器填充" in md  # section 7 still LLM-driven


def test_render_execution_section_is_premium_unaware():
    """AC10: _render_execution_section takes pre-prefixed strings verbatim
    and emits them. No premium-awareness inside template.py — FP 'effects
    at edges'."""
    from irc.memo.template import _render_execution_section

    lines = (
        "⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜**159501 X** | ...",
        "**513690 Y** | ...",
    )
    rendered = _render_execution_section(lines)
    # Both lines emit as-is, each wrapped with `- ` bullet prefix.
    assert "- ⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜**159501 X**" in rendered
    assert "- **513690 Y**" in rendered
    # template.py never reads premium/blocking — it can't have changed.
    assert "qdii_premium_pct" not in rendered
