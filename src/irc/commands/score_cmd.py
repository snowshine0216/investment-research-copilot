from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.scoring.metrics_loader import load_scoring_metrics
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

    watchlist = pd.read_csv(watchlist_path, dtype={"instrument_id": str, "ticker": str})

    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        regime = _macro_summary(con)
        metrics = load_scoring_metrics(con, watchlist["instrument_id"].astype(str).tolist())
    finally:
        con.close()

    route = resolve_route("scoring_rationale", bundle.llm)
    out = run_scoring(
        watchlist=watchlist,
        metrics=metrics,
        news_summaries={},
        regime_summary=regime,
        route=route,
        cfg_scoring=bundle.scoring,
    )

    # Enrich each score entry with asset_class and role from the watchlist
    # (allocation pipeline needs these fields for per-class grouping)
    watchlist_meta = (
        watchlist[["instrument_id", "asset_class", "role"]].drop_duplicates("instrument_id")
        if {"asset_class", "role"}.issubset(watchlist.columns)
        else pd.DataFrame(columns=["instrument_id", "asset_class", "role"])
    )
    meta_by_id = watchlist_meta.set_index("instrument_id").to_dict("index")
    for entry in out["scores"]:
        m = meta_by_id.get(entry["instrument_id"], {})
        entry.setdefault("asset_class", m.get("asset_class", "unknown"))
        entry.setdefault("role", m.get("role", ""))

    out_path = root / "outputs" / today / "scoring.json"
    atomic_write_text(out_path, json.dumps(out, ensure_ascii=False, indent=2))
    print(f"score OK: {len(out['scores'])} instruments → {out_path}")
    return 0
