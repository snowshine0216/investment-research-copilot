from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.scoring.pipeline import run_scoring


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _macro_summary(con) -> str:
    rows = con.execute(
        "SELECT series_id, value FROM macro_series WHERE date >= "
        "(SELECT MAX(date) - INTERVAL '7 days' FROM macro_series)"
    ).fetchall()
    return "; ".join(f"{r[0]}={r[1]:.3f}" for r in rows[:6]) or "macro snapshot unavailable"


def run_score(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()

    watchlist_path = root / "outputs" / today / "discovered_watchlist.csv"
    if not watchlist_path.exists():
        outputs = sorted((root / "outputs").glob("*/discovered_watchlist.csv"))
        if not outputs:
            print("ERROR: no discovered_watchlist.csv found; run `irc discover` first.")
            return 2
        watchlist_path = outputs[-1]

    watchlist = pd.read_csv(watchlist_path)

    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        regime = _macro_summary(con)
    finally:
        con.close()

    # Metrics from DB is a placeholder; full metrics join comes in Plan 3.
    metrics = pd.DataFrame(columns=[
        "instrument_id", "expense_ratio", "drawdown_3y", "vol_1y",
        "downside_capture", "aum_stability_pct", "manager_tenure_years",
        "holdings_concentration_top10",
    ])

    route = resolve_route("scoring_rationale", bundle.llm)
    out = run_scoring(
        watchlist=watchlist,
        metrics=metrics,
        news_summaries={},
        regime_summary=regime,
        route=route,
        cfg_scoring=bundle.scoring,
    )

    out_path = root / "outputs" / today / "scoring.json"
    atomic_write_text(out_path, json.dumps(out, ensure_ascii=False, indent=2))
    print(f"score OK: {len(out['scores'])} instruments → {out_path}")
    return 0
