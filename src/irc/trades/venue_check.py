from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.universe import UniverseConfig, Instrument


@dataclass(frozen=True)
class VenueCheckResult:
    compatible: bool
    proxy_id: str | None
    note: str


def _find(universe: UniverseConfig, iid: str) -> Instrument | None:
    for i in universe.instruments:
        if i.instrument_id == iid:
            return i
    return None


def _proxy_for(
    target: Instrument, universe: UniverseConfig, available_venues: set[str],
) -> Instrument | None:
    """Find a proxy: same asset_class + tracked_index, venue compatible with user."""
    for i in universe.instruments:
        if i.instrument_id == target.instrument_id:
            continue
        if i.asset_class != target.asset_class:
            continue
        if (i.tracked_index or "").strip() != (target.tracked_index or "").strip():
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
