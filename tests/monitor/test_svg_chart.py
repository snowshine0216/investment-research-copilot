from irc.monitor.svg_chart import render_nav_chart, EventMarker


def _series(n):
    return tuple((f"2026-01-{i % 28 + 1:02d}", 1.0 + 0.001 * i) for i in range(n))


def test_chart_is_svg_with_path():
    svg = render_nav_chart(_series(300), markers=())
    assert svg.startswith("<svg") and "<path" in svg


def test_chart_is_byte_stable():
    s = _series(300)
    assert render_nav_chart(s, markers=()) == render_nav_chart(s, markers=())


def test_coordinates_rounded_to_fixed_precision():
    svg = render_nav_chart(_series(50), markers=())
    # No coordinate carries more than 2 decimal places.
    import re
    for num in re.findall(r"\d+\.\d+", svg):
        assert len(num.split(".")[1]) <= 2


def test_event_marker_carries_title():
    m = EventMarker(date="2026-01-10", sign=-1, title="real yields up · Reuters · 2026-01-10")
    svg = render_nav_chart(_series(60), markers=(m,))
    assert "<title>" in svg and "real yields up" in svg


def test_marker_title_is_html_escaped():
    m = EventMarker(date="2026-01-10", sign=1, title="<script>alert(1)</script>")
    svg = render_nav_chart(_series(60), markers=(m,))
    assert "<script>" not in svg and "&lt;script&gt;" in svg


def test_no_javascript_emitted():
    svg = render_nav_chart(_series(60), markers=())
    assert "onclick" not in svg.lower() and "<script" not in svg.lower()
