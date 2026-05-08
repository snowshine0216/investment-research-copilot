from __future__ import annotations

from dataclasses import dataclass

from irc.discovery.universe import UniverseRow


def _is_core_gold(r: UniverseRow) -> bool:
    return r.asset_class == "gold"


def _is_core_us(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and (r.tracked_index or "").lower() in ("s&p 500", "msci usa")


def _is_core_cn(r: UniverseRow) -> bool:
    return r.asset_class in ("cn_etf", "cn_equity_fund") and (r.tracked_index or "").startswith(("沪深", "中证"))


def _is_satellite_us_tech(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and "nasdaq" in (r.tracked_index or "").lower()


def _is_satellite_cn_growth(r: UniverseRow) -> bool:
    return r.asset_class == "cn_equity_fund"


def _is_defensive_cn_bond(r: UniverseRow) -> bool:
    return r.asset_class == "cn_bond_fund"


def _is_defensive_us_bond(r: UniverseRow) -> bool:
    return r.asset_class == "us_etf" and "bond" in (r.tracked_index or "").lower()


def _is_hedge_low_corr(r: UniverseRow) -> bool:
    return r.asset_class == "hk_etf" and "dividend" in (r.tracked_index or "").lower()


ROLE_RULES: tuple[tuple[str, object], ...] = (
    ("core_gold_hedge", _is_core_gold),
    ("core_us_equity", _is_core_us),
    ("core_cn_equity", _is_core_cn),
    ("satellite_us_tech", _is_satellite_us_tech),
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
            if pred(r):  # type: ignore[operator]
                buckets[role].append(r)
                break
    relaxed: list[str] = []
    failed: list[str] = []
    for role in buckets:
        n = len(buckets[role])
        if n == 0:
            failed.append(role)
        elif n < min_per_role:
            relaxed.append(role)
    return RoleBucketResult(
        buckets={k: tuple(v) for k, v in buckets.items()},
        relaxed_roles=tuple(relaxed),
        failed_roles=tuple(failed),
    )
