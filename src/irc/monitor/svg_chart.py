from __future__ import annotations
from dataclasses import dataclass
from html import escape

_W, _H, _PAD = 600.0, 180.0, 20.0


@dataclass(frozen=True)
class EventMarker:
    date: str
    sign: int            # -1 / 0 / +1 → colour
    title: str


def _r(x: float) -> str:
    return f"{round(x, 2)}"


def _scale(series):
    vals = [v for _, v in series]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(series)

    def xy(i, v):
        x = _PAD + (_W - 2 * _PAD) * (i / max(1, n - 1))
        y = _H - _PAD - (_H - 2 * _PAD) * ((v - lo) / span)
        return x, y

    return xy


def _marker_colour(sign: int) -> str:
    return {1: "#1a7f37", -1: "#cf222e"}.get(sign, "#6e7781")


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
    """PURE byte-stable inline SVG of an acc-NAV series with causal-event markers.
    No JS; tooltips via SVG <title>; coordinates rounded to 2dp."""
    if not series:
        return '<svg viewBox="0 0 600 180" xmlns="http://www.w3.org/2000/svg"></svg>'
    xy = _scale(series)
    coords = [
        f"{_r(x)},{_r(y)}"
        for i, (_, v) in enumerate(series)
        for x, y in [xy(i, v)]
    ]
    d = "M " + " L ".join(coords)
    dots = _build_dots(series, markers, xy)
    return (
        '<svg viewBox="0 0 600 180" xmlns="http://www.w3.org/2000/svg">'
        f'<path fill="none" stroke="#0969da" stroke-width="1.5" d="{d}"/>'
        + dots
        + "</svg>"
    )
