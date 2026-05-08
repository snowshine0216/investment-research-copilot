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


def test_render_top_picks_listed():
    md = render_skeleton(_inputs())
    assert "518880" in md
    assert "006075" in md
