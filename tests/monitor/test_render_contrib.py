from __future__ import annotations
import re
from irc.monitor.render_contrib import contribution_bars_svg
from irc.monitor.types import FactorContribution


def _contribs():
    return (
        FactorContribution("trend", .5, .8, .40, 1.0, True, ""),
        FactorContribution("flow", .2, -.5, -.10, 1.0, True, ""),
        FactorContribution("macro_tilt", .3, 1.0, .30, 1.0, True, ""),
    )


def test_contrib_bars_is_svg():
    svg = contribution_bars_svg(_contribs())
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_contrib_bars_distinguish_news_visually():
    svg = contribution_bars_svg(_contribs())
    # news bars carry a distinct marker (hatch pattern id or muted opacity class)
    assert "news-bar" in svg or "url(#hatch)" in svg


def test_contrib_bars_diverging_colors():
    svg = contribution_bars_svg(_contribs())
    assert "#1a7f37" in svg and "#cf222e" in svg


def test_contrib_bars_geometry_rounded_2dp():
    svg = contribution_bars_svg(_contribs())
    # no coordinate has > 2 decimal places
    assert not re.search(r"\d+\.\d{3,}", svg)


def test_contrib_bars_byte_stable():
    assert contribution_bars_svg(_contribs()) == contribution_bars_svg(_contribs())


def test_contrib_bars_empty():
    svg = contribution_bars_svg(())
    assert svg.startswith("<svg") and "</svg>" in svg


def test_contrib_bars_no_script():
    assert "<script" not in contribution_bars_svg(_contribs()).lower()
