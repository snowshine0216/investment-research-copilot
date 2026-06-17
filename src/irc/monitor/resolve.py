from __future__ import annotations
from irc.schemas.monitor import MonitorConfig, compose_weights, weights_sum_ok
from irc.monitor.profiles import default_weights, eligible_factors
from irc.monitor.types import MonitorFund


def _validate_override(fund_id: str, profile: str, weights: dict[str, float]) -> None:
    """Govern the per-fund signal_weights override (ADR 0018 D2): an override may
    only reweight factors the profile can structurally fill, and never go negative —
    so weight can never be spent on a profile-ineligible factor (silent dead weight)."""
    extra = sorted(set(weights) - set(eligible_factors(profile)))
    if extra:
        raise ValueError(
            f"{fund_id}: signal_weights override keys {extra} are not eligible for "
            f"profile '{profile}' (eligible: {sorted(eligible_factors(profile))})"
        )
    negative = sorted(k for k, w in weights.items() if w < 0)
    if negative:
        raise ValueError(f"{fund_id}: signal_weights override has negative weights {negative}")


def _resolve_one(fund, defaults) -> MonitorFund:
    base = default_weights(fund.analysis_profile)
    weights = compose_weights(base, fund.signal_weights)
    _validate_override(fund.id, fund.analysis_profile, weights)
    if not weights_sum_ok(weights):
        raise ValueError(
            f"effective signal_weights for {fund.id} sum to {sum(weights.values())}, not 1.0"
        )
    bands = fund.signal_bands or defaults.signal_bands
    min_conf = fund.minimum_confidence if fund.minimum_confidence is not None else defaults.minimum_confidence
    return MonitorFund(
        id=fund.id, name_cn=fund.name_cn, market=fund.market,
        analysis_profile=fund.analysis_profile, themes=tuple(fund.themes),
        constituent_news=fund.constituent_news, weights=weights,
        bands=dict(bands), minimum_confidence=min_conf,
    )


def resolve_funds(cfg: MonitorConfig) -> tuple[MonitorFund, ...]:
    """Pure: MonitorConfig → ordered MonitorFund tuple with effective weights."""
    return tuple(_resolve_one(f, cfg.defaults) for f in cfg.funds)
