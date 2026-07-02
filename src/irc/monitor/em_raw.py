"""Pure parse: raw EastMoney JSON → the monitor industry leg's frame shapes.

Slotted into the existing injectable `fetch` params of industry_valuation
(fetch_board_pe_frame → fetch_industry_pe; fetch_stock_info_frame →
fetch_stock_industry_map) so the pure parsers / per-day 3-outcome caches are
UNCHANGED. em_raw owns its raw-JSON parsing — NO akshare wrappers here — so
upstream response-shape drift (F4 missing 市盈率 column, F5 dlmkts/dsc keys)
can't recur silently. These parsers are PURE (no I/O, no network); the edge
fetchers (requests, IRC_CN_PROXY routing) come in Task 5.
"""
from __future__ import annotations

import pandas as pd


def _diff_rows(payload: dict) -> list[dict]:
    """Pure: clist/get payload → list of board-row dicts. `data.diff` may be a
    list or a dict-of-index (both observed shapes). `data: null` / missing →
    []."""
    diff = (payload.get("data") or {}).get("diff") if isinstance(payload, dict) else None
    if isinstance(diff, dict):
        return list(diff.values())
    return list(diff) if isinstance(diff, list) else []


def parse_clist_boards(payload: dict) -> pd.DataFrame:
    """Pure: clist/get board payload → frame with 板块名称 (f14) + 市盈率 (f9),
    the columns the existing parse_industry_pe expects. Empty/null → empty frame."""
    rows = _diff_rows(payload)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        {"板块名称": [r.get("f14") for r in rows],
         "市盈率": [r.get("f9") for r in rows]})


def parse_stock_info(payload: dict) -> pd.DataFrame:
    """Pure: stock/get payload → (item,value) long frame. A 行业 row (f127) is
    emitted iff f127 is truthy. data:null / non-dict → empty frame (→ TRANSIENT
    via _is_blank_info_frame). A well-formed data with no f127 → item/value
    frame WITHOUT a 行业 row (→ DEAD), preserving the existing 3-outcome
    contract. Ignores dlmkts/dsc drift keys (F5) — only `data` is read."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return pd.DataFrame()
    items: list[tuple[str, object]] = [("代码", data.get("f57")), ("名称", data.get("f58"))]
    if data.get("f127"):
        items.append(("行业", data.get("f127")))
    return pd.DataFrame({"item": [i for i, _ in items], "value": [v for _, v in items]})
