# src/irc/scoring/news_summaries.py
"""Theme→asset-class plumbing for the `thesis_news` scoring factor.

Pure module: no I/O, no logging, no module-level mutable state. The mapping
table is immutable (`MappingProxyType`). See ADR 0007 for the locked design.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

import pandas as pd

from irc.research.theme_research import ThemeReport


# Locked by ADR 0007 §2. Keys are the seven real asset_class values present
# in config/universe/*.yaml. Values are tuples of theme names sorted ASC for
# determinism (regression-tested in tests/scoring/test_news_summaries.py).
THEMES_BY_ASSET_CLASS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "cn_bond_fund": ("cn_monetary",),
    "cn_equity_fund": ("cn_equity_property_policy", "cn_monetary", "holdings_sector"),
    "cn_etf": ("cn_equity_property_policy", "cn_monetary", "holdings_sector"),
    "gold": ("geopolitics", "gold_drivers", "us_monetary"),
    "hk_etf": (
        "cn_equity_property_policy", "cn_monetary", "geopolitics", "holdings_sector",
    ),
    "qdii_global": ("geopolitics", "us_fiscal_politics", "us_monetary"),
    "us_etf": ("geopolitics", "us_fiscal_politics", "us_monetary"),
})


def themes_for_instrument(asset_class: str) -> tuple[str, ...]:
    """Return the sorted theme tuple mapped to a given asset_class.

    Unknown asset_class returns the empty tuple (silent fallback, per ADR 0007
    §2). The empty tuple feeds the existing neutral-50 invariant in
    `score_thesis_news`.
    """
    return THEMES_BY_ASSET_CLASS.get(asset_class, ())


def _summary_for_theme(theme: str, reports: Mapping[str, ThemeReport]) -> str:
    """Return the prose body for a theme, or '' if absent/failed/empty.

    Pure: no I/O. Failed reports (non-empty `failure_reason`) and empty
    `report_md` both return '' so the caller can filter them out uniformly.
    """
    report = reports.get(theme)
    if report is None:
        return ""
    if report.failure_reason:
        return ""
    return report.report_md or ""


def build_news_summaries(
    reports: Mapping[str, ThemeReport],
    watchlist: pd.DataFrame,
) -> dict[str, tuple[str, ...]]:
    """Build the `news_summaries` dict consumed by `run_scoring`.

    For every watchlist row, look up the row's asset_class, expand to its
    mapped themes (sorted ASC), and fetch each theme's `report_md` from
    `reports`. Failed or empty reports are skipped silently. The
    per-instrument value is a tuple of summary strings whose order matches
    the sorted theme-name order returned by `themes_for_instrument`.

    Pure function: no filesystem reads, no logging, no mutation.
    """
    if watchlist.empty:
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for row in watchlist.itertuples(index=False):
        iid = str(getattr(row, "instrument_id", ""))
        if not iid:
            continue
        asset_class = str(getattr(row, "asset_class", "") or "")
        themes = themes_for_instrument(asset_class)
        summaries = tuple(
            s for s in (_summary_for_theme(t, reports) for t in themes) if s
        )
        out[iid] = summaries
    return out
