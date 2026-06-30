"""EDGE + pure parse: monitor heat (crowding) restriction leg via AkShare.

`ak.fund_purchase_em()` returns ONE market-wide table (申购状态 + 日累计限定金额 per
fund). A single call per `irc monitor` run yields the restriction status for all
monitor ids — no per-fund fetch. The one network effect (`fetch_purchase_table`)
NEVER raises: any failure → None → every per-fund parse yields None → honest
`heat_no_data` (spec §5.3). Parsing is pure and column-name-tolerant: an
unexpected shape degrades to None, NEVER a wrong bool (spec §10).

CN endpoint stays DIRECT (no IRC_HTTPS_PROXY) per the project http-proxy rule.
AUM-Δ leg is deferred this slice — `heat_inputs_for` always returns aum_delta_pct=None.
"""
from __future__ import annotations

import logging

import pandas as pd

_log = logging.getLogger(__name__)

# Restriction rule (spec §5.1): restricted when 申购状态 ∉ _OPEN_STATUSES OR
# 日累计限定金额 < _RESTRICTION_CAP_THRESHOLD.
_RESTRICTION_CAP_THRESHOLD: float = 1e8
_OPEN_STATUSES: frozenset[str] = frozenset({"开放申购"})

# Column names from the live-confirmed fund_purchase_em schema. Parsing tolerates
# absence (degrade to None) so a future akshare rename can't produce a wrong bool.
_CODE_COL: str = "基金代码"
_STATUS_COL: str = "申购状态"
_CAP_COL: str = "日累计限定金额"


def _norm_code(value: object) -> str:
    """6-digit zero-padded fund code, tolerant of int/str/whitespace."""
    return str(value).strip().zfill(6)


def _row_for(table: pd.DataFrame, fund_id: str) -> pd.Series | None:
    """Pure: the single row whose code matches fund_id, else None."""
    if _CODE_COL not in table.columns:
        return None
    target = _norm_code(fund_id)
    codes = table[_CODE_COL].map(_norm_code)
    matched = table[codes == target]
    if matched.empty:
        return None
    return matched.iloc[0]


def _cap_below_threshold(row: pd.Series) -> bool:
    """Pure: True only when the cap is numeric AND < threshold. Missing/unparseable
    cap → False (cap leg can't fire; the status leg still decides)."""
    if _CAP_COL not in row.index:
        return False
    try:
        cap = float(row[_CAP_COL])
    except (TypeError, ValueError):
        return False
    if pd.isna(cap):
        return False
    return cap < _RESTRICTION_CAP_THRESHOLD


def parse_purchase_status(table: pd.DataFrame | None, fund_id: str) -> bool | None:
    """Pure: restricted=True when 申购状态 ∉ {开放申购} OR 日累计限定金额 < 1e8.
    Fund absent / missing code or status column / empty|None table → None
    (→ heat_no_data, surfaced — never a fabricated bool)."""
    if not isinstance(table, pd.DataFrame) or table.empty:
        return None
    row = _row_for(table, fund_id)
    if row is None or _STATUS_COL not in row.index:
        return None
    status = str(row[_STATUS_COL]).strip()
    restricted_by_status = status not in _OPEN_STATUSES
    return restricted_by_status or _cap_below_threshold(row)


def purchase_tag_for(fund_id: str, *, purchase_table: pd.DataFrame | None) -> str | None:
    """PURE (spec §9): '限购 ¥{cap}/日' when cap-restricted; '限购' when status-
    restricted only; None when open OR data unavailable. Never '可申购'."""
    if not isinstance(purchase_table, pd.DataFrame) or purchase_table.empty:
        return None
    row = _row_for(purchase_table, fund_id)
    if row is None or _STATUS_COL not in row.index:
        return None
    if _cap_below_threshold(row):
        try:
            cap = float(row[_CAP_COL])
        except (TypeError, ValueError):
            cap = None
        if cap is not None and not pd.isna(cap):
            cap_int = int(cap) if cap == int(cap) else cap
            return f"限购 ¥{cap_int}/日"
    status = str(row[_STATUS_COL]).strip()
    restricted_by_status = status not in _OPEN_STATUSES
    if restricted_by_status:
        return "限购"
    return None


def heat_inputs_for(
    fund_id: str, *, purchase_table: pd.DataFrame | None
) -> tuple[bool | None, float | None]:
    """Pure: (restricted, aum_delta_pct). aum_delta_pct is always None this slice
    (no per-fund live QoQ source — AUM-Δ leg deferred, spec §5)."""
    return parse_purchase_status(purchase_table, fund_id), None


def _has_required_columns(table: pd.DataFrame) -> bool:
    """True iff both required columns (_CODE_COL, _STATUS_COL) are in the table."""
    return _CODE_COL in table.columns and _STATUS_COL in table.columns


def fetch_purchase_table(fetch=None) -> pd.DataFrame | None:
    """EDGE: ONE network call per run → the market-wide purchase table, or None on
    ANY failure (never raises — spec §5.3). `fetch` is injectable for tests; the
    default lazy-imports akshare (house pattern: no module-top akshare). CN endpoint
    is DIRECT (no IRC_HTTPS_PROXY).

    Schema-drift observability (spec §10): if required columns are missing after a
    valid non-empty fetch, logs a structured WARNING and returns None — unambiguous
    vs. empty/fetch-fail cases, which also log."""
    if fetch is None:
        import akshare as ak  # local import — house pattern, avoids akshare at module load
        fetch = ak.fund_purchase_em
    try:
        table = fetch()
    except Exception:  # noqa: BLE001 — degrade to None, never crash the brief
        _log.warning("fetch_purchase_table: ak.fund_purchase_em() failed", exc_info=True)
        return None
    if not isinstance(table, pd.DataFrame) or table.empty:
        _log.warning("fetch_purchase_table: empty/invalid purchase table")
        return None
    if not _has_required_columns(table):
        missing = [c for c in (_CODE_COL, _STATUS_COL) if c not in table.columns]
        _log.warning(
            "fetch_purchase_table: fund_purchase_em schema drift — missing columns: %s",
            missing,
        )
        return None
    return table
