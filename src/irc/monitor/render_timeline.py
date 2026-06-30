"""PURE Comp 3b: bias-history timeline grid. Frozen BiasTimeline (built at the
edge from forward_ledger.jsonl) → colored HTML grid; the v1→v3 engine boundary is
marked where a fund's engine tag changes between adjacent run dates. No JS, no
remote refs. Byte-stable.

Absent (fund, date) cells carry bias=None (no-data sentinel) and render with
class "no-data" + label " " — visually distinct from a real NEUTRAL cell."""
from __future__ import annotations
from dataclasses import dataclass
from html import escape

# one (bias | None, engine) pair per run date, ordered oldest→newest
# bias is None for absent cells (no-data sentinel, distinct from NEUTRAL)
_Cell = tuple[str | None, str]


@dataclass(frozen=True)
class BiasTimeline:
    run_dates: tuple[str, ...]
    rows: tuple[tuple[str, tuple[_Cell, ...]], ...]   # (fund_id, cells)


def _cell_html(prev_eng: str | None, cell: _Cell) -> str:
    bias, eng = cell
    if bias is None:
        # no-data sentinel: muted blank cell, no engine-boundary marking
        return '<td class="tl-cell no-data"> </td>'
    cls = bias.lower()
    boundary = " engine-boundary" if prev_eng is not None and eng != prev_eng else ""
    label = {"ADD_BIAS": "+", "REDUCE_BIAS": "−", "NEUTRAL": "·"}.get(bias, "?")
    return f'<td class="tl-cell {cls}{boundary}">{label}</td>'


def _row_html(fund_id: str, cells: tuple[_Cell, ...]) -> str:
    out = []
    prev_eng: str | None = None
    for cell in cells:
        out.append(_cell_html(prev_eng, cell))
        prev_eng = cell[1]
    return f"<tr><td>{escape(fund_id)}</td>{''.join(out)}</tr>"


def bias_timeline_html(timeline: BiasTimeline) -> str:
    if not timeline.run_dates or not timeline.rows:
        return ""
    head = "<tr><th>基金</th>" + "".join(
        f"<th>{escape(d)}</th>" for d in timeline.run_dates) + "</tr>"
    body = "".join(_row_html(fid, cells) for fid, cells in timeline.rows)
    note = '<p class="muted">引擎切换以边框标记 (engine-boundary)</p>'
    return ('<section class="timeline"><h2>方向性倾向历史</h2>'
            f'<table class="timeline-table">{head}{body}</table>{note}</section>')
