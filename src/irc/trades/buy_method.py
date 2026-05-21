from __future__ import annotations
from typing import Literal


Mode = Literal["build", "hybrid", "steady_state"]
MODE_BUILD: Mode = "build"


_DEFAULTS_STEADY: dict[str, str] = {
    "gold":           "gold_anchor_plus_band",
    "cn_equity_fund": "dca_monthly",
    "cn_bond_fund":   "lump_sum",
    "cn_etf":         "scaled_in_3",
    "hk_etf":         "scaled_in_4",
    "us_etf":         "lump_sum",
    "qdii_global":    "scaled_in_4",
    "cash":           "lump_sum",
}


def default_buy_method(asset_class: str, mode: Mode) -> str:
    """Return the default buy_method for an (asset_class, mode) pair."""
    if asset_class == "gold":
        return "gold_anchor_plus_band"
    if mode == "build":
        return "small_account_anchor"
    return _DEFAULTS_STEADY.get(asset_class, "dca_weekly")
