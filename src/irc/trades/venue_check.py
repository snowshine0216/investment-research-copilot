from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.universe import UniverseConfig, Instrument


@dataclass(frozen=True)
class VenueCheckResult:
    compatible: bool
    proxy_id: str | None
    note: str


# Cross-asset-class substitution for proxy lookup. The target's asset_class
# maps to the set of asset_classes whose instruments may serve as proxies.
# Equity-style ETFs (cn_etf, us_etf, hk_etf) can be proxied by off-exchange
# index funds (cn_equity_fund) when the tracked_index matches. Bonds, gold,
# and active funds proxy only within their own class.
_PROXY_ASSET_CLASS_SUBSTITUTIONS: dict[str, frozenset[str]] = {
    "cn_etf": frozenset({"cn_etf", "cn_equity_fund"}),
    "us_etf": frozenset({"us_etf", "cn_equity_fund"}),
    "hk_etf": frozenset({"hk_etf", "cn_equity_fund"}),
}


def _allowed_proxy_classes(target_class: str) -> frozenset[str]:
    return _PROXY_ASSET_CLASS_SUBSTITUTIONS.get(target_class, frozenset({target_class}))


def _find(universe: UniverseConfig, iid: str) -> Instrument | None:
    for i in universe.instruments:
        if i.instrument_id == iid:
            return i
    return None


def _proxy_for(
    target: Instrument, universe: UniverseConfig, available_venues: set[str],
) -> Instrument | None:
    """Find a proxy: same tracked_index, venue compatible with user, asset_class
    in the documented substitution set for the target's class.

    Cross-asset-class substitution is gated on a non-empty target tracked_index:
    we never silently substitute an active/unindexed fund.
    """
    target_index = (target.tracked_index or "").strip()
    allowed_classes = _allowed_proxy_classes(target.asset_class)
    cross_class = len(allowed_classes) > 1
    # When the rule allows cross-class substitution, the target itself MUST
    # be index-tracked — otherwise we have no benchmark to match on.
    if cross_class and not target_index:
        allowed_classes = frozenset({target.asset_class})
    for i in universe.instruments:
        if i.instrument_id == target.instrument_id:
            continue
        if i.asset_class not in allowed_classes:
            continue
        if (i.tracked_index or "").strip() != target_index:
            continue
        if not i.venue_required or set(i.venue_required) & available_venues:
            return i
    return None


def check_venue(
    instrument_id: str, available_venues: list[str], universe: UniverseConfig,
) -> VenueCheckResult:
    target = _find(universe, instrument_id)
    if target is None:
        return VenueCheckResult(compatible=False, proxy_id=None,
                                note=f"instrument {instrument_id} not in universe")
    if set(target.venue_required) & set(available_venues):
        return VenueCheckResult(compatible=True, proxy_id=None, note="direct match")
    proxy = _proxy_for(target, universe, set(available_venues))
    if proxy is not None:
        return VenueCheckResult(
            compatible=False, proxy_id=proxy.instrument_id,
            note=f"venue mismatch; proxy via {proxy.instrument_id} ({proxy.name_cn})",
        )
    return VenueCheckResult(compatible=False, proxy_id=None,
                            note="venue mismatch and no proxy available; consider opening new account")
