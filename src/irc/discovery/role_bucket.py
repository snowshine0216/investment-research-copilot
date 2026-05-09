from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from irc.discovery.universe import UniverseRow


# Whitelist of broad-market CN indices. Sector indices like "中证军工" share
# the "中证" prefix but must NOT bucket as core — themed instruments are
# explicitly excluded above via the `theme is not None` short-circuit.
_BROAD_CN_INDICES = frozenset({
    "沪深300", "上证50",
    "中证A500", "中证500", "中证1000", "中证全指",
    "创业板指", "创业板50", "科创50",
})


def _is_core_gold(r: UniverseRow) -> bool:
    return r.asset_class == "gold"


def _is_core_us(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and (r.tracked_index or "").lower() in ("s&p 500", "msci usa")


def _is_core_cn(r: UniverseRow) -> bool:
    """Broad-market CN equity. theme=broad always counts; theme=None falls
    back to the explicit broad-index whitelist; any other theme (sector or
    factor) is excluded so it can route to the right satellite bucket."""
    if r.asset_class not in ("cn_etf", "cn_equity_fund"):
        return False
    if r.theme == "broad":
        return True
    if r.theme is not None:
        return False
    return (r.tracked_index or "") in _BROAD_CN_INDICES


def _is_satellite_us_tech(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and "nasdaq" in (r.tracked_index or "").lower()


def _is_satellite_cn_dividend(r: UniverseRow) -> bool:
    return r.asset_class in ("cn_etf", "cn_equity_fund") and r.theme == "dividend"


def _theme_pred(target: str) -> Callable[[UniverseRow], bool]:
    """Build a sector-theme predicate that accepts both ETFs and active funds.
    A holding's exposure (semiconductor, healthcare, etc.) is the same whether
    delivered passively via a 中证半导体 ETF or actively via a sector-focused
    mutual fund — both bucket together so the LLM can compare them head-to-head."""
    def _pred(r: UniverseRow) -> bool:
        return r.asset_class in ("cn_etf", "cn_equity_fund") and r.theme == target
    return _pred


_is_satellite_cn_tech = _theme_pred("tech")
_is_satellite_cn_semiconductor = _theme_pred("semiconductor")
_is_satellite_cn_defense = _theme_pred("defense")
_is_satellite_cn_healthcare = _theme_pred("healthcare")
_is_satellite_cn_new_energy = _theme_pred("new_energy")
_is_satellite_cn_consumer = _theme_pred("consumer")
_is_satellite_cn_finance = _theme_pred("finance")
_is_satellite_cn_metals = _theme_pred("metals")
_is_satellite_cn_real_estate = _theme_pred("real_estate")
_is_satellite_cn_soe = _theme_pred("soe")


def _is_satellite_cn_growth(r: UniverseRow) -> bool:
    """Active equity funds with no sector or factor tilt — broad alpha plays
    (张坤/谢治宇/朱少醒-style whole-market managers). Themed active funds
    bucket into their sector role, not here."""
    return r.asset_class == "cn_equity_fund" and r.theme in (None, "broad")


def _is_defensive_cn_bond(r: UniverseRow) -> bool:
    return r.asset_class == "cn_bond_fund"


def _is_defensive_us_bond(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and "bond" in (r.tracked_index or "").lower()


def _is_hedge_low_corr(r: UniverseRow) -> bool:
    return r.asset_class == "hk_etf" and "dividend" in (r.tracked_index or "").lower()


# First-match-wins. Order matters where predicates overlap:
# - core_cn_equity comes BEFORE sector buckets so theme=broad wins when set
# - sector themes come BEFORE satellite_cn_growth so themed active funds
#   bucket by theme rather than fall into the broad-active catchall
ROLE_RULES: tuple[tuple[str, Callable[[UniverseRow], bool]], ...] = (
    ("core_gold_hedge", _is_core_gold),
    ("core_us_equity", _is_core_us),
    ("core_cn_equity", _is_core_cn),
    ("satellite_us_tech", _is_satellite_us_tech),
    ("satellite_cn_dividend", _is_satellite_cn_dividend),
    ("satellite_cn_tech", _is_satellite_cn_tech),
    ("satellite_cn_semiconductor", _is_satellite_cn_semiconductor),
    ("satellite_cn_defense", _is_satellite_cn_defense),
    ("satellite_cn_healthcare", _is_satellite_cn_healthcare),
    ("satellite_cn_new_energy", _is_satellite_cn_new_energy),
    ("satellite_cn_consumer", _is_satellite_cn_consumer),
    ("satellite_cn_finance", _is_satellite_cn_finance),
    ("satellite_cn_metals", _is_satellite_cn_metals),
    ("satellite_cn_real_estate", _is_satellite_cn_real_estate),
    ("satellite_cn_soe", _is_satellite_cn_soe),
    ("satellite_cn_growth", _is_satellite_cn_growth),
    ("defensive_cn_bond", _is_defensive_cn_bond),
    ("defensive_us_bond", _is_defensive_us_bond),
    ("hedge_low_correlation", _is_hedge_low_corr),
)


@dataclass(frozen=True)
class RoleBucketResult:
    buckets: dict[str, tuple[UniverseRow, ...]]
    relaxed_roles: tuple[str, ...]
    failed_roles: tuple[str, ...]


def bucket_by_role(
    rows: tuple[UniverseRow, ...],
    min_per_role: int,
    fail_below: int,
) -> RoleBucketResult:
    """Step 4 of Discovery. First-match-wins role assignment."""
    buckets: dict[str, list[UniverseRow]] = {role: [] for role, _ in ROLE_RULES}
    for r in rows:
        for role, pred in ROLE_RULES:
            if pred(r):
                buckets[role].append(r)
                break
    relaxed: list[str] = []
    failed: list[str] = []
    for role in buckets:
        n = len(buckets[role])
        if n == 0 or n < fail_below:
            failed.append(role)
        elif n < min_per_role:
            relaxed.append(role)
    return RoleBucketResult(
        buckets={k: tuple(v) for k, v in buckets.items()},
        relaxed_roles=tuple(relaxed),
        failed_roles=tuple(failed),
    )
