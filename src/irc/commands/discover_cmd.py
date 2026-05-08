from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.discovery.pipeline import run_discovery
from irc.discovery.universe import enumerate_universe
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route


def _now_iso_date() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _fetch_metadata_metrics(con) -> tuple:
    import pandas as pd

    inst_df = con.execute(
        "SELECT instrument_id, inception_date, expense_ratio, aum FROM instruments"
    ).fetch_df()
    if not inst_df.empty:
        inst_df["inception_years"] = (
            datetime.now(timezone.utc).year
            - pd.to_datetime(inst_df["inception_date"], errors="coerce").dt.year
        )
        inst_df["aum_cny"] = inst_df["aum"]
        inst_df["daily_volume_cny"] = 0.0  # placeholder — conservative (fail-safe until real data)
    else:
        inst_df["inception_years"] = []
        inst_df["aum_cny"] = []
        inst_df["daily_volume_cny"] = []

    metrics = con.execute(
        "SELECT instrument_id, drawdown_3y, tracking_error, "
        "       0.0 AS manager_tenure_years "
        "FROM fund_metrics"
    ).fetch_df()
    if metrics.empty:
        metrics = pd.DataFrame({
            "instrument_id": [], "drawdown_3y": [],
            "tracking_error": [], "manager_tenure_years": [],
        })
    return inst_df, metrics


def run_discover(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    db_path = root / "data" / "local.duckdb"

    con = connect(db_path)
    try:
        ensure_schema(con)
        metadata, metrics = _fetch_metadata_metrics(con)
        ref_pool = tuple(
            r[0] for r in con.execute(
                "SELECT DISTINCT _raw_ref FROM prices LIMIT 200"
            ).fetchall()
        )
    finally:
        con.close()

    universe = enumerate_universe(
        bundle.universe_qdii_us,
        bundle.universe_qdii_hk,
        bundle.universe_cn_funds,
        bundle.universe_gold,
    )
    route = resolve_route("watchlist_reason", bundle.llm)
    df = run_discovery(
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
    )
    out_dir = root / "outputs" / _now_iso_date()
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "discovered_watchlist.csv", df.to_csv(index=False))
    print(f"discover OK: {len(df)} candidates → {out_dir / 'discovered_watchlist.csv'}")
    return 0
