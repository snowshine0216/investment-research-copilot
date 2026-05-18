from __future__ import annotations
import pandas as pd


def candidates_per_role(watchlist: pd.DataFrame) -> dict[str, int]:
    return watchlist.groupby("role").size().to_dict()


def filter_integrity(
    watchlist: pd.DataFrame,
    required_cols: tuple[str, ...] = ("instrument_id", "ticker", "role"),
) -> float:
    """Fraction of rows where all required columns are non-null.

    Default matches the producer's actual CSV contract
    (src/irc/discovery/pipeline.py _WATCHLIST_COLUMNS).
    """
    if watchlist.empty:
        return 1.0
    cols = [c for c in required_cols if c in watchlist.columns]
    if not cols:
        return 1.0
    has_all = watchlist[cols].notna().all(axis=1)
    return float(has_all.mean())


def dedup(watchlist: pd.DataFrame, key_col: str = "ticker") -> float:
    """Fraction of unique values in the key column."""
    if watchlist.empty or key_col not in watchlist.columns:
        return 1.0
    return watchlist[key_col].nunique() / len(watchlist)


def llm_reason_grounding(watchlist: pd.DataFrame) -> float:
    if watchlist.empty:
        return 1.0
    has_ref = (watchlist["cited_refs"].fillna("").str.len() > 0)
    return float(has_ref.mean())
