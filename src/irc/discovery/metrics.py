from __future__ import annotations

import pandas as pd


DISCOVERY_METRIC_COLUMNS = (
    "instrument_id",
    "drawdown_3y",
    "tracking_error",
    "manager_tenure_years",
)


def empty_discovery_metrics() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DISCOVERY_METRIC_COLUMNS))


def max_drawdown(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    positive = clean[clean > 0]
    if positive.empty:
        return 0.0
    drawdowns = positive / positive.cummax() - 1.0
    return float(abs(drawdowns.min()))


def derive_discovery_metrics(
    values: pd.DataFrame,
    value_col: str,
    manager_tenure_by_id: dict[str, float | None],
) -> pd.DataFrame:
    if values.empty or value_col not in values.columns:
        return empty_discovery_metrics()
    rows = [
        {
            "instrument_id": str(instrument_id),
            "drawdown_3y": max_drawdown(group[value_col]),
            "tracking_error": 0.0,  # STUB(plan-3): compute rolling std of returns minus benchmark
            "manager_tenure_years": _tenure_or_zero(manager_tenure_by_id.get(str(instrument_id))),
        }
        for instrument_id, group in values.groupby("instrument_id", sort=False)
    ]
    if not rows:
        return empty_discovery_metrics()
    return pd.DataFrame(rows, columns=list(DISCOVERY_METRIC_COLUMNS))


def merge_discovery_metrics(primary: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    primary_metrics = _dedupe_metrics(primary)
    fallback_metrics = _dedupe_metrics(fallback)
    if primary_metrics.empty:
        return fallback_metrics
    if fallback_metrics.empty:
        return primary_metrics
    ordered_ids = tuple(dict.fromkeys([
        *primary_metrics["instrument_id"].tolist(),
        *fallback_metrics["instrument_id"].tolist(),
    ]))
    combined = (
        primary_metrics.set_index("instrument_id")
        .combine_first(fallback_metrics.set_index("instrument_id"))
        .reindex(ordered_ids)
        .reset_index()
    )
    return combined.loc[:, list(DISCOVERY_METRIC_COLUMNS)]


def _dedupe_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    return _with_metric_columns(metrics).drop_duplicates("instrument_id", keep="first")


def _with_metric_columns(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return empty_discovery_metrics()
    return metrics.assign(
        **{
            col: pd.NA
            for col in DISCOVERY_METRIC_COLUMNS
            if col not in metrics.columns
        }
    ).loc[:, list(DISCOVERY_METRIC_COLUMNS)]


def _tenure_or_zero(value: float | None) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)
