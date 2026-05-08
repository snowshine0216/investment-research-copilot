from __future__ import annotations

from typing import Any

import pandas as pd

from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.macro_fit import MacroFitContext, score_macro_fit
from irc.scoring.factors.quality import score_quality
from irc.scoring.factors.risk import score_risk
from irc.scoring.factors.thesis_news import score_thesis_news
from irc.scoring.factors.valuation_cost import score_valuation_cost
from irc.scoring.instrument_score import compose_score

_REQUIRED = (
    "expense_ratio", "drawdown_3y", "vol_1y", "downside_capture",
    "aum_stability_pct", "manager_tenure_years", "holdings_concentration_top10",
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _completeness(metric_row: dict, required: tuple[str, ...]) -> float:
    present = sum(1 for k in required if not _is_missing(metric_row.get(k)))
    return present / len(required)


def _get(m: dict, key: str, default: float) -> float:
    """Return m[key] when present and finite enough to parse; otherwise return default."""
    val = m.get(key)
    if _is_missing(val):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def run_scoring(
    watchlist: pd.DataFrame,
    metrics: pd.DataFrame,
    news_summaries: dict[str, tuple[str, ...]],
    regime_summary: str,
    route: Any,
    cfg_scoring: ScoringConfig,
) -> dict[str, list[dict[str, Any]]]:
    """End-to-end scoring for each instrument in the watchlist."""
    by_id = metrics.set_index("instrument_id").to_dict("index") if not metrics.empty else {}
    out: list[dict[str, Any]] = []
    for r in watchlist.itertuples(index=False):
        m = by_id.get(r.instrument_id, {})
        completeness = _completeness(m, _REQUIRED)
        refs = tuple(r.cited_refs.split(",")) if isinstance(getattr(r, "cited_refs", None), str) else ()
        v = score_valuation_cost(
            expense_ratio=_get(m, "expense_ratio", 0.01),
            premium_discount_pct=_get(m, "premium_discount_pct", 0.0),
            raw_refs=refs,
        )
        rk = score_risk(
            drawdown_3y=_get(m, "drawdown_3y", 0.20),
            vol_1y=_get(m, "vol_1y", 0.20),
            downside_capture=_get(m, "downside_capture", 1.0),
            raw_refs=refs,
        )
        q = score_quality(
            aum_stability_pct=_get(m, "aum_stability_pct", 0.10),
            manager_tenure_years=_get(m, "manager_tenure_years", 3.0),
            holdings_concentration_top10=_get(m, "holdings_concentration_top10", 0.30),
            raw_refs=refs,
        )
        mf = score_macro_fit(
            MacroFitContext(
                regime_summary=regime_summary,
                instrument_profile=(
                    f"{r.instrument_id} {r.name_cn} {r.asset_class} "
                    f"tracking {getattr(r, 'tracked_index', '')}"
                ),
                raw_refs=refs,
            ),
            route=route,
        )
        tn = score_thesis_news(
            news_summaries=news_summaries.get(r.instrument_id, ()),
            raw_refs=refs,
        )
        score_obj = compose_score(
            instrument_id=r.instrument_id,
            factors={"valuation_cost": v, "risk": rk, "quality": q, "macro_fit": mf, "thesis_news": tn},
            data_completeness=completeness,
            cfg=cfg_scoring,
        )
        out.append({
            "instrument_id": score_obj.instrument_id,
            "composite_score": score_obj.composite_score,
            "action": score_obj.action,
            "conviction": score_obj.conviction,
            "factor_breakdown": score_obj.factor_breakdown,
            "data_completeness": score_obj.data_completeness,
            "weights_version": score_obj.weights_version,
        })
    return {"scores": out}
