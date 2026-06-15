from __future__ import annotations
from dataclasses import dataclass
from html import escape

# viewBox geometry. The plot is inset to leave gutters for axis labels.
_W, _H = 600.0, 180.0
_LEFT, _RIGHT, _TOP, _BOTTOM = 46.0, 10.0, 10.0, 24.0
_X0, _X1 = _LEFT, _W - _RIGHT
_Y0, _Y1 = _TOP, _H - _BOTTOM            # _Y0 = top (high NAV), _Y1 = bottom (low NAV)


@dataclass(frozen=True)
class EventMarker:
    date: str
    sign: int            # -1 / 0 / +1 → colour
    title: str


def _r(x: float) -> str:
    return f"{round(x, 2)}"


def _fmt_nav(v: float) -> str:
    return f"{v:.4f}"


def _scale(series):
    vals = [v for _, v in series]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(series)

    def xy(i, v):
        x = _X0 + (_X1 - _X0) * (i / max(1, n - 1))
        y = _Y1 - (_Y1 - _Y0) * ((v - lo) / span)
        return x, y

    return xy, lo, hi


def _marker_colour(sign: int) -> str:
    return {1: "#1a7f37", -1: "#cf222e"}.get(sign, "#6e7781")


def _y_axis(lo: float, hi: float) -> str:
    """Horizontal gridlines + NAV value labels at low / mid / high."""
    parts = []
    for frac in (0.0, 0.5, 1.0):
        v = lo + (hi - lo) * frac
        y = _Y1 - (_Y1 - _Y0) * frac
        parts.append(
            f'<line x1="{_r(_X0)}" y1="{_r(y)}" x2="{_r(_X1)}" y2="{_r(y)}" '
            'stroke="#eaeef2" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{_r(_X0 - 4)}" y="{_r(y + 3)}" text-anchor="end" '
            f'font-size="9" fill="#57606a">{_fmt_nav(v)}</text>'
        )
    return "".join(parts)


def _x_axis(series, xy) -> str:
    """Date labels at first / middle / last sample."""
    n = len(series)
    picks = ((0, "start"), (n // 2, "middle"), (n - 1, "end"))
    y = _Y1 + 13
    parts = []
    for idx, anchor in dict((i, a) for i, a in picks).items():
        x, _ = xy(idx, series[idx][1])
        parts.append(
            f'<text x="{_r(x)}" y="{_r(y)}" text-anchor="{anchor}" '
            f'font-size="9" fill="#57606a">{escape(series[idx][0])}</text>'
        )
    return "".join(parts)


def _hit_strips(series, xy) -> str:
    """Invisible full-height columns; native <title> reveals date · NAV on hover."""
    n = len(series)
    cols = min(n, 120)
    col_w = (_X1 - _X0) / cols
    h = _Y1 - _Y0
    parts = []
    for j in range(cols):
        idx = min(n - 1, round((j + 0.5) / cols * (n - 1)))
        d, v = series[idx]
        x = _X0 + j * col_w
        parts.append(
            f'<rect class="hit" x="{_r(x)}" y="{_r(_Y0)}" width="{_r(col_w)}" '
            f'height="{_r(h)}" fill="transparent">'
            f"<title>{escape(d)} · {_fmt_nav(v)}</title></rect>"
        )
    return "".join(parts)


def _build_dots(series, markers, xy) -> str:
    date_to_idx = {d: i for i, (d, _) in enumerate(series)}
    dots = []
    for m in markers:
        idx = date_to_idx.get(m.date)
        if idx is None:
            continue
        x, y = xy(idx, series[idx][1])
        dots.append(
            f'<circle cx="{_r(x)}" cy="{_r(y)}" r="3" fill="{_marker_colour(m.sign)}">'
            f"<title>{escape(m.title)}</title></circle>"
        )
    return "".join(dots)


def render_nav_chart(
    series: tuple[tuple[str, float], ...], *, markers: tuple[EventMarker, ...],
) -> str:
    """PURE byte-stable inline SVG of an acc-NAV series with labelled axes and
    per-point hover detail. No JS; tooltips via SVG <title>; geometry rounded to
    2dp. Hover columns surface date · NAV; markers add causal-event dots."""
    if not series:
        return (
            '<svg class="navchart" viewBox="0 0 600 180" '
            'xmlns="http://www.w3.org/2000/svg"></svg>'
        )
    xy, lo, hi = _scale(series)
    coords = [f"{_r(x)},{_r(y)}" for i, (_, v) in enumerate(series) for x, y in [xy(i, v)]]
    d = "M " + " L ".join(coords)
    return (
        '<svg class="navchart" viewBox="0 0 600 180" xmlns="http://www.w3.org/2000/svg">'
        + _y_axis(lo, hi)
        + f'<path fill="none" stroke="#0969da" stroke-width="1.5" d="{d}"/>'
        + _hit_strips(series, xy)
        + _build_dots(series, markers, xy)
        + _x_axis(series, xy)
        + "</svg>"
    )
