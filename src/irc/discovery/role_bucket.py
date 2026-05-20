from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from irc.discovery.universe import UniverseRow
from irc.schemas._types import SECTOR_THEMES


# Whitelist of broad-market CN indices. Sector indices like "中证军工" share
# the "中证" prefix but must NOT bucket as core — themed instruments are
# explicitly excluded above via the `theme is not None` short-circuit.
_BROAD_CN_INDICES = frozenset({
    "沪深300", "上证50",
    "中证A500", "中证500", "中证1000", "中证全指",
    "创业板指", "创业板50", "科创50",
})

THEMED_CN_ROLE_BY_THEME: dict[str, str] = {
    theme: f"satellite_cn_{theme}"
    for theme in SECTOR_THEMES
}


def _is_core_gold(r: UniverseRow) -> bool:
    return r.asset_class == "gold"


# Broad-market US trackers. Substring match (lowercased) so the predicate
# accepts variants like "S&P 500 Index" or "MSCI USA IMI" without requiring
# an exhaustive index-name enum. Sector / factor ETFs (Nasdaq, sector SPDRs,
# small-cap factor) are excluded — guarded by explicit tests.
_BROAD_US_INDEX_FRAGMENTS: tuple[str, ...] = (
    "s&p 500",
    "msci usa",
    "russell 1000",
    "russell 3000",
    "crsp us total market",
)


def _is_core_us(r: UniverseRow) -> bool:
    if r.asset_class != "us_etf":
        return False
    idx = (r.tracked_index or "").lower()
    return any(fragment in idx for fragment in _BROAD_US_INDEX_FRAGMENTS)


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


_THEMED_CN_ROLE_RULES = tuple(
    (role, _theme_pred(theme))
    for theme, role in THEMED_CN_ROLE_BY_THEME.items()
)


def _is_satellite_cn_growth(r: UniverseRow) -> bool:
    """Active equity funds with no sector or factor tilt — broad alpha plays
    (张坤/谢治宇/朱少醒-style whole-market managers). Themed active funds
    bucket into their sector role, not here."""
    return r.asset_class == "cn_equity_fund" and r.theme is None


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
    *_THEMED_CN_ROLE_RULES,
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
