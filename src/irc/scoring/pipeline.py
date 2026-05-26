from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES

from irc.decision.completeness import (
    completeness_ratio,
    is_missing,
    missing_required_fields,
)
from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.macro_fit import MacroFitContext, score_macro_fit
from irc.scoring.factors.quality import score_quality
from irc.scoring.factors.risk import score_risk
from irc.scoring.factors.thesis_news import score_thesis_news
from irc.scoring.factors.valuation_cost import score_valuation_cost
from irc.scoring.instrument_score import compose_score

_log = logging.getLogger(__name__)


def _sanitize(text: str, max_len: int = 200) -> str:
    """Strip control characters and truncate external-sourced strings before LLM use."""
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in (" ", "\t"))
    return cleaned[:max_len]


def _get(m: dict, key: str, default: float) -> float:
    """Return m[key] when present and finite enough to parse; otherwise return default."""
    val = m.get(key)
    if is_missing(val):
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
    qdii_premium_resolver: Callable[[str, str, str], float | None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """End-to-end scoring for each instrument in the watchlist."""
    by_id = metrics.set_index("instrument_id").to_dict("index") if not metrics.empty else {}

    # Pre-batch all macro_fit LLM calls in parallel (avoid N×30s sequential wait)
    rows = list(watchlist.itertuples(index=False))
    macro_contexts: dict[str, MacroFitContext] = {}
    for r in rows:
        refs = tuple(r.cited_refs.split(",")) if isinstance(getattr(r, "cited_refs", None), str) else ()
        macro_contexts[r.instrument_id] = MacroFitContext(
            regime_summary=regime_summary,
            instrument_profile=_sanitize(
                f"{r.instrument_id} {r.name_cn} {r.asset_class} "
                f"tracking {getattr(r, 'tracked_index', '')}"
            ),
            raw_refs=refs,
        )

    macro_results: dict[str, Any] = {}
    if rows:
        with ThreadPoolExecutor(max_workers=min(len(rows), 8)) as pool:
            futures = {
                pool.submit(score_macro_fit, ctx, route): iid
                for iid, ctx in macro_contexts.items()
            }
            for future in as_completed(futures):
                iid = futures[future]
                try:
                    macro_results[iid] = future.result()
                except Exception:
                    _log.warning("macro_fit failed for %s — using neutral 50", iid)
                    macro_results[iid] = score_macro_fit(
                        MacroFitContext(regime_summary="", instrument_profile="", raw_refs=()), route=None  # type: ignore
                    )

    out: list[dict[str, Any]] = []
    for r in rows:
        m = by_id.get(r.instrument_id, {})
        asset_class = getattr(r, "asset_class", None)
        market = getattr(r, "market", None)
        completeness = completeness_ratio(m, asset_class=asset_class, market=market)
        missing_data = list(missing_required_fields(m, asset_class=asset_class, market=market))
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
        mf = macro_results.get(r.instrument_id, score_macro_fit(
            MacroFitContext(regime_summary="", instrument_profile="", raw_refs=()), route=None  # type: ignore
        ))
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
        score_row: dict[str, Any] = {
            "instrument_id": score_obj.instrument_id,
            "composite_score": score_obj.composite_score,
            "action": score_obj.action,
            "conviction": score_obj.conviction,
            "factor_breakdown": score_obj.factor_breakdown,
            "data_completeness": score_obj.data_completeness,
            "missing_data": missing_data,
            "weights_version": score_obj.weights_version,
        }
        if qdii_premium_resolver is not None and str(asset_class or "") in _QDII_ASSET_CLASSES:
            row_market = str(market or "")
            row_asset_class = str(asset_class or "")
            premium = qdii_premium_resolver(
                row_asset_class, row_market, str(r.instrument_id)
            )
            if premium is not None:
                score_row["qdii_premium_pct"] = premium
        out.append(score_row)
    return {"scores": out}
