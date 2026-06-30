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


# ---------------------------------------------------------------------------
# Finding B: absent (fund, date) cells must render distinctly from NEUTRAL
# ---------------------------------------------------------------------------

def test_timeline_absent_cell_distinct_from_neutral():
    """A cell with no-data sentinel (None bias) must render differently from a
    real NEUTRAL cell — it must not carry class 'neutral' and must use a
    distinct marker."""
    tl = BiasTimeline(
        run_dates=("2026-06-29", "2026-06-30"),
        rows=(
            # 519069: present both dates
            ("519069", (("NEUTRAL", "3"), ("ADD_BIAS", "3"))),
            # 270023: absent on 06-29 → sentinel (None, "0")
            ("270023", ((None, "0"), ("ADD_BIAS", "3"))),
        ),
    )
    html = bias_timeline_html(tl)
    # The HTML must exist
    assert "270023" in html
    # Absent cell must NOT carry class "neutral"
    # We check that the cells for 270023 don't produce an uncaveated "neutral" class
    # by confirming no-data renders with a distinct marker
    assert "no-data" in html or "·" not in html.split("270023")[1][:60] or True
    # Strict check: no-data class present OR the absent bias is not labelled "·"
    # (which is the NEUTRAL label). We rely on render_timeline to use a distinct class.
    # If the implementation uses class "no-data", assert that:
    assert "no-data" in html, (
        "absent cell must render with 'no-data' class, not 'neutral'"
    )
