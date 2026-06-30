from __future__ import annotations
from irc.monitor.render_timeline import BiasTimeline, bias_timeline_html


def _tl():
    return BiasTimeline(
        run_dates=("2026-06-28", "2026-06-29", "2026-06-30"),
        rows=(
            ("519069", (("ADD_BIAS", "1"), ("NEUTRAL", "3"), ("NEUTRAL", "3"))),
            ("008986", (("REDUCE_BIAS", "1"), ("REDUCE_BIAS", "3"), ("ADD_BIAS", "3"))),
        ),
    )


def test_timeline_renders_one_cell_per_run_date():
    html = bias_timeline_html(_tl())
    assert html.count("2026-06-28") >= 1
    assert "519069" in html and "008986" in html


def test_timeline_marks_engine_boundary():
    html = bias_timeline_html(_tl())
    # v1->v3 boundary marked where engine tag changes ("1" -> "3")
    assert "engine-boundary" in html or "引擎切换" in html


def test_timeline_uses_badge_classes():
    html = bias_timeline_html(_tl())
    assert "add_bias" in html and "reduce_bias" in html and "neutral" in html


def test_timeline_empty_renders_nothing():
    assert bias_timeline_html(BiasTimeline(run_dates=(), rows=())) == ""


def test_timeline_byte_stable():
    assert bias_timeline_html(_tl()) == bias_timeline_html(_tl())


def test_timeline_no_script_no_remote():
    html = bias_timeline_html(_tl())
    assert "<script" not in html.lower() and "http" not in html
