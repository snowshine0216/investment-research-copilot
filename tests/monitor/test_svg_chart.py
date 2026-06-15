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
    # Geometry (tag attributes incl. the path `d`) carries no more than 2 decimal
    # places. Human-readable text nodes (axis labels, hover tooltips) are exempt —
    # they legitimately show NAV at 4dp — so strip text-node content first.
    import re
    attrs_only = re.sub(r">[^<]*", ">", svg)
    for num in re.findall(r"\d+\.\d+", attrs_only):
        assert len(num.split(".")[1]) <= 2, num


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


def test_chart_carries_size_class():
    # A stable class lets the report CSS cap the rendered size (zoom-out).
    svg = render_nav_chart(_series(60), markers=())
    assert 'class="navchart"' in svg


def test_y_axis_labels_min_and_max_nav():
    # series values are 1.0 .. 1.299 (1.0 + 0.001*299) for n=300
    svg = render_nav_chart(_series(300), markers=())
    assert "<text" in svg
    assert "1.0000" in svg and "1.2990" in svg


def test_x_axis_labels_first_and_last_date():
    svg = render_nav_chart(_series(300), markers=())
    assert "2026-01-01" in svg          # first sample date
    assert "2026-01-20" in svg          # last sample date (i=299 → day 20)


def test_hover_strips_expose_date_and_nav():
    svg = render_nav_chart(_series(300), markers=())
    assert '<rect class="hit"' in svg
    # A hover column's tooltip pairs the date with the NAV at that column.
    import re
    titles = re.findall(r"<title>([^<]+)</title>", svg)
    assert titles and all("·" in t for t in titles)
    assert any("2026-01" in t for t in titles)


def test_hover_strip_count_is_bounded():
    # Dense multi-year series must not emit one strip per sample (file-size guard).
    svg = render_nav_chart(_series(5000), markers=())
    assert svg.count('class="hit"') <= 120
