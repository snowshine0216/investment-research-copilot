"""PURE Comp 3c: compact inline-SVG diverging contribution bars per factor inside a
fund card. Market factors vs news factors are visually distinguished (news bars use
a hatch fill) so the overlay is obvious. Geometry rounded to 2dp; byte-stable. No
JS, no remote refs.

Non-finite contributions (NaN, ±inf) are treated as zero-width bars so the SVG
output is always well-formed (Finding D)."""
from __future__ import annotations
import math
from html import escape
from irc.monitor.signal import _FAMILY_OF
from irc.monitor.types import FactorContribution

_W, _ROW_H, _PAD = 260.0, 16.0, 4.0
_MID = _W / 2.0
_HALF = _MID - _PAD
_GREEN, _RED = "#1a7f37", "#cf222e"
_HATCH = ('<defs><pattern id="hatch" width="4" height="4" '
          'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
          '<line x1="0" y1="0" x2="0" y2="4" stroke="#8c959f" stroke-width="1"/>'
          '</pattern></defs>')


def _r(x: float) -> str:
    return f"{x:.2f}"


def _bar(c: FactorContribution, y: float) -> str:
    is_news = _FAMILY_OF.get(c.name) == "news"
    # Guard non-finite values — treat as zero contribution (Finding D)
    contrib = c.contribution if math.isfinite(c.contribution) else 0.0
    mag = min(abs(contrib), 1.0) * _HALF
    if contrib >= 0:
        x, w, colour = _MID, mag, _GREEN
    else:
        x, w, colour = _MID - mag, mag, _RED
    cls = ' class="news-bar"' if is_news else ""
    fill = 'url(#hatch)' if is_news else colour
    rect = (f'<rect{cls} x="{_r(x)}" y="{_r(y)}" width="{_r(w)}" '
            f'height="{_r(_ROW_H - 4)}" fill="{fill}" stroke="{colour}"/>')
    label = f'<text x="2" y="{_r(y + _ROW_H - 6)}" font-size="10">{escape(c.name)}</text>'
    return label + rect


def contribution_bars_svg(contributions: tuple[FactorContribution, ...]) -> str:
    n = len(contributions)
    height = max(_ROW_H, n * _ROW_H)
    bars = "".join(_bar(c, i * _ROW_H + 2) for i, c in enumerate(contributions))
    axis = f'<line x1="{_r(_MID)}" y1="0" x2="{_r(_MID)}" y2="{_r(height)}" stroke="#d0d7de"/>'
    return (f'<svg class="contrib" viewBox="0 0 {_r(_W)} {_r(height)}" '
            f'xmlns="http://www.w3.org/2000/svg">{_HATCH}{axis}{bars}</svg>')
