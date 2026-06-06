from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.raw_ref import ref_index_from_duckdb
from irc.discovery.metrics import (
    DISCOVERY_METRIC_COLUMNS,
    derive_discovery_metrics,
    empty_discovery_metrics,
    merge_discovery_metrics,
)
from irc.discovery.pipeline import run_discovery_with_diagnostics
from irc.discovery.universe import enumerate_universe
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route

_log = logging.getLogger(__name__)


def _now_iso_date() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _metadata_with_derived_fields(
    inst_df: pd.DataFrame,
    volume_df: pd.DataFrame,
) -> pd.DataFrame:
    if inst_df.empty:
        return pd.DataFrame(columns=[
            "instrument_id", "inception_date", "expense_ratio", "aum",
            "manager_tenure_years", "inception_years", "aum_cny", "daily_volume_cny",
        ])
    metadata = inst_df.assign(
        inception_years=(
            datetime.now(timezone.utc).year
            - pd.to_datetime(inst_df["inception_date"], errors="coerce").dt.year
        ),
        aum_cny=inst_df["aum"],
    )
    if volume_df.empty:
        _log.warning("No volume data available — daily_volume_cny set to 0.0 (placeholder). Discovered watchlist will be empty if hard filter is active.")
        return metadata.assign(daily_volume_cny=0.0)
    with_volume = metadata.merge(volume_df, on="instrument_id", how="left")
    return with_volume.assign(daily_volume_cny=with_volume["daily_volume_cny"].fillna(0.0))


def _manager_tenure_by_id(metadata: pd.DataFrame) -> dict[str, float | None]:
    if metadata.empty or "manager_tenure_years" not in metadata.columns:
        return {}
    return {
        str(r.instrument_id): None if pd.isna(r.manager_tenure_years) else float(r.manager_tenure_years)
        for r in metadata.itertuples(index=False)
    }


def _latest_fund_metrics(metrics: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return empty_discovery_metrics()
    latest = (
        metrics.assign(as_of_date=pd.to_datetime(metrics["as_of_date"], errors="coerce"))
        .sort_values(["instrument_id", "as_of_date"])
        .drop_duplicates("instrument_id", keep="last")
    )
    tenure = metadata.loc[:, ["instrument_id", "manager_tenure_years"]]
    with_tenure = latest.merge(tenure, on="instrument_id", how="left")
    return with_tenure.assign(
        manager_tenure_years=with_tenure["manager_tenure_years"].fillna(0.0)  # placeholder — conservative (fail-safe until real data)
    ).loc[:, list(DISCOVERY_METRIC_COLUMNS)]


def _derive_db_metrics(con, manager_tenure_by_id: dict[str, float | None]) -> pd.DataFrame:
    price_values = con.execute(
        "SELECT instrument_id, date, close FROM prices"
        " WHERE date >= CURRENT_DATE - INTERVAL '3 years'"
    ).fetch_df()
    nav_values = con.execute(
        "SELECT instrument_id, date, COALESCE(nav_acc, nav) AS nav_value FROM nav_history"
        " WHERE date >= CURRENT_DATE - INTERVAL '3 years'"
    ).fetch_df()
    return merge_discovery_metrics(
        derive_discovery_metrics(price_values, "close", manager_tenure_by_id),
        derive_discovery_metrics(nav_values, "nav_value", manager_tenure_by_id),
    )


def _fetch_metadata_metrics(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    inst_df = con.execute(
        "SELECT instrument_id, inception_date, expense_ratio, aum, manager_tenure_years "
        "FROM instruments"
    ).fetch_df()
    volume_df = con.execute(
        "SELECT instrument_id, AVG(close * volume) FILTER (WHERE volume IS NOT NULL) AS daily_volume_cny "
        "FROM prices GROUP BY instrument_id"
    ).fetch_df()
    metadata = _metadata_with_derived_fields(inst_df, volume_df)
    stored_metrics = con.execute(
        "SELECT instrument_id, as_of_date, drawdown_3y, tracking_error FROM fund_metrics"
    ).fetch_df()
    metrics = _latest_fund_metrics(stored_metrics, metadata)
    derived = _derive_db_metrics(con, _manager_tenure_by_id(metadata))
    return metadata, merge_discovery_metrics(metrics, derived)


def run_discover(repo_root: str) -> int:
    import logging as _logging
    from datetime import datetime, timezone, timedelta
    from irc.spend.record_run import record_command_run
    from irc.commands.spend_cmd import preflight_gate

    root = Path(repo_root)
    _today_date = datetime.now(timezone(timedelta(hours=8))).date()

    gate_rc = preflight_gate(str(root), "run", stages=("discover",))
    if gate_rc != 0:
        return gate_rc

    bundle = load_repo_configs(root)
    db_path = root / "data" / "local.duckdb"

    con = connect(db_path)
    try:
        ensure_schema(con)
        metadata, metrics = _fetch_metadata_metrics(con)
        ref_pool = tuple(ref_index_from_duckdb(con))
    finally:
        con.close()

    universe = enumerate_universe(
        bundle.universe_qdii_us,
        bundle.universe_qdii_hk,
        bundle.universe_cn_funds,
        bundle.universe_gold,
    )
    route = resolve_route("watchlist_reason", bundle.llm)
    cost_entries: list = []
    try:
        result = run_discovery_with_diagnostics(
            universe=universe,
            metadata=metadata,
            metrics=metrics,
            risk_band_max_dd_upper=bundle.preferences.risk_band.max_drawdown[1],
            cfg_overrides=bundle.overrides,
            cfg_discovery=bundle.discovery,
            route=route,
            peer_summary="See universe peers in same role bucket.",
            macro_snapshot="See macro_series in DuckDB.",
            raw_ref_pool=ref_pool,
            excluded_themes=tuple(bundle.preferences.constraints.exclude_themes),
        )
        cost_entries = result.cost_entries
        out_dir = root / "outputs" / _now_iso_date()
        out_dir.mkdir(parents=True, exist_ok=True)
        watchlist_path = out_dir / "discovered_watchlist.csv"
        diagnostics_path = out_dir / "discovery_diagnostics.csv"
        rejections_path = out_dir / "discovery_rejections.csv"
        atomic_write_text(watchlist_path, result.watchlist.to_csv(index=False))
        atomic_write_text(diagnostics_path, result.diagnostics.to_csv(index=False))
        atomic_write_text(rejections_path, result.rejections.to_csv(index=False))
        print(f"discover OK: {len(result.watchlist)} candidates → {watchlist_path}")
        print(f"diagnostics OK: {len(result.diagnostics)} rows → {diagnostics_path}")
        print(f"rejections OK: {len(result.rejections)} rows → {rejections_path}")
        return 0
    finally:
        try:
            record_command_run(
                repo_root=root, history=cost_entries, search_units={}, today=_today_date,
            )
        except Exception:
            _logging.getLogger(__name__).warning("spend recorder failed", exc_info=True)
