from __future__ import annotations
from irc.schemas.monitor import MonitorConfig, compose_weights, weights_sum_ok
from irc.monitor.profiles import default_weights
from irc.monitor.types import MonitorFund


def _resolve_one(fund, defaults) -> MonitorFund:
    base = default_weights(fund.analysis_profile)
    weights = compose_weights(base, fund.signal_weights)
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
