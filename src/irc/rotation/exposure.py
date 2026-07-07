"""PURE: holdings × stock→board map → fund×board exposure matrix (spec §5/§6, D7).

exposure_pct(fund, board) = Σ top-10 holding weight_pct mapped to that board.
Unmapped stocks reduce coverage and are surfaced in diagnostics — never silently
dropped (AC6). No I/O.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from irc.narrative.schemas import Holding
from irc.rotation.types import ExposureRow

Fund = tuple[str, str, tuple[Holding, ...], str | None]


def build_exposure(
    funds: Iterable[Fund],
    stock_to_board: Mapping[str, str],
) -> tuple[tuple[ExposureRow, ...], dict]:
    rows: list[ExposureRow] = []
    all_syms: set[str] = set()
    mapped_syms: set[str] = set()
    unmapped: set[str] = set()
    for fund_id, name_cn, holdings, as_of in funds:
        by_board: dict[str, list[Holding]] = {}
        for h in holdings:
            all_syms.add(h.symbol)
            board = stock_to_board.get(h.symbol)
            if board is None:
                unmapped.add(h.symbol)
                continue
            mapped_syms.add(h.symbol)
            by_board.setdefault(board, []).append(h)
        for board, hs in by_board.items():
            rows.append(ExposureRow(
                fund_id=fund_id, name_cn=name_cn, board_code=board,
                exposure_pct=round(sum(h.weight_pct for h in hs), 4),
                matched_symbols=tuple(sorted(h.symbol for h in hs)),
                holdings_as_of=as_of))
    total = len(all_syms)
    diag = {
        "total_holding_syms": total,
        "mapped_syms": len(mapped_syms),
        "unmapped_syms": tuple(sorted(unmapped)),
        "coverage_pct": round(100.0 * len(mapped_syms) / total, 4) if total else 0.0,
    }
    return tuple(rows), diag
