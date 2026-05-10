from __future__ import annotations

from typing import Any

import pandas as pd

from irc.discovery.hard_filter import apply_hard_filter
from irc.discovery.quality_filter import apply_quality_filter
from irc.discovery.reason_writer import WriteReasonContext, write_reason
from irc.discovery.role_bucket import bucket_by_role
from irc.discovery.universe import UniverseRow
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.inputs import RiskBand
from irc.schemas.overrides import OverridesConfig


_WATCHLIST_COLUMNS = (
    "instrument_id", "ticker", "market", "name_cn", "asset_class", "currency",
    "tracked_index", "venue_required", "role", "reason_text", "cited_refs", "relaxed",
)


_MAX_REFS_PER_INSTRUMENT = 30


def _index_refs_by_instrument(
    pool: tuple[str, ...],
    limit: int = _MAX_REFS_PER_INSTRUMENT,
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for ref in pool:
        parts = ref.split(":", 3)
        if len(parts) != 4:
            continue
        grouped.setdefault(parts[2], []).append(ref)
    return {
        instrument_id: tuple(
            sorted(refs, key=lambda ref: ref.rsplit(":", 1)[-1], reverse=True)[:limit]
        )
        for instrument_id, refs in grouped.items()
    }


def _refs_for_instrument(
    instrument_id: str,
    pool: tuple[str, ...],
    limit: int = _MAX_REFS_PER_INSTRUMENT,
) -> tuple[str, ...]:
    """Filter ref pool to entries about this instrument, most recent first, capped.

    Refs follow the format ``source:topic:instrument_id:date``. Without this
    filter, the LLM prompt would balloon to the full DB ref pool (100k+ entries
    for a real universe), exceeding context limits.

    .. warning::
        This is a single-instrument convenience wrapper that rebuilds the full
        O(N) index on every call.  Callers in a tight loop **must** use
        :func:`_index_refs_by_instrument` directly to avoid O(M·N) behaviour.
    """
    return _index_refs_by_instrument(pool, limit).get(instrument_id, ())


def _default_cfg() -> DiscoveryConfig:
    return DiscoveryConfig.model_validate({
        "hard_filters": {
            "inception_years_min": 0, "cn_fund_aum_cny_min": 0,
            "us_etf_aum_usd_min": 0, "cn_active_expense_ratio_max": 1,
            "cn_passive_expense_ratio_max": 1, "us_etf_expense_ratio_max": 1,
            "etf_daily_volume_cny_min": 0,
        },
        "quality_filters": {"drawdown_3y_buffer": 1.5, "tracking_error_max": 1, "manager_tenure_years_min": 0},
        "role_bucket": {"min_candidates_per_role": 1, "fail_below": 0},
    })


def run_discovery(
    universe: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    metrics: pd.DataFrame,
    risk_band_max_dd_upper: float,
    cfg_overrides: OverridesConfig | None,
    cfg_discovery: DiscoveryConfig | None,
    route: Any,
    peer_summary: str,
    macro_snapshot: str,
    raw_ref_pool: tuple[str, ...],
    excluded_themes: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Compose discovery 5 steps end-to-end. Returns watchlist DataFrame."""
    cfg_d = cfg_discovery or _default_cfg()
    cfg_o = cfg_overrides or OverridesConfig()
    risk = RiskBand.model_validate({
        "max_drawdown": [0.05, risk_band_max_dd_upper],
        "horizon": "long_core_medium_rotation",
    })
    hard = apply_hard_filter(universe, metadata, cfg_d, cfg_o, excluded_themes=excluded_themes)
    quality = apply_quality_filter(hard.passed, metrics, cfg_d, risk)
    bucketed = bucket_by_role(
        quality.passed,
        cfg_d.role_bucket.min_candidates_per_role,
        cfg_d.role_bucket.fail_below,
    )
    refs_by_instrument = _index_refs_by_instrument(raw_ref_pool)
    rows: list[dict[str, Any]] = []
    for role, items in bucketed.buckets.items():
        for r in items:
            ctx = WriteReasonContext(
                role=role,
                peer_summary=peer_summary,
                macro_snapshot=macro_snapshot,
                raw_refs=refs_by_instrument.get(r.instrument_id, ()),
            )
            res = write_reason(r, ctx, route=route)
            if res is None:
                continue
            rows.append({
                "instrument_id": r.instrument_id,
                "ticker": r.ticker,
                "market": r.market,
                "name_cn": r.name_cn,
                "asset_class": r.asset_class,
                "currency": r.currency,
                "tracked_index": r.tracked_index or "",
                "venue_required": ",".join(r.venue_required),
                "role": role,
                "reason_text": res.reason_text,
                "cited_refs": ",".join(res.cited_refs),
                "relaxed": role in bucketed.relaxed_roles,
            })
    if not rows:
        return pd.DataFrame(columns=list(_WATCHLIST_COLUMNS))
    return pd.DataFrame(rows)
