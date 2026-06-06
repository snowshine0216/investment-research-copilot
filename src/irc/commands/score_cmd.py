from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from irc.config_loader import load_repo_configs
from irc.data.akshare_client import fetch_qdii_premium_pct
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.research.persistence import load_theme_reports
from irc.scoring.metrics_loader import load_scoring_metrics
from irc.scoring.news_summaries import build_news_summaries
from irc.scoring.pipeline import run_scoring
from irc.scoring.qdii_premium import qdii_premium_for_row


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _macro_summary(con) -> str:
    rows = con.execute(
        "SELECT series_id, value FROM macro_series WHERE date >= "
        "(SELECT MAX(date) - INTERVAL '7 days' FROM macro_series)"
    ).fetchall()
    return "; ".join(f"{r[0]}={r[1]:.3f}" for r in rows[:6]) or "macro snapshot unavailable"


def run_score(repo_root: str) -> int:  # noqa: PLR0912 (complexity driven by DB + enrichment)
    import logging as _logging
    from datetime import datetime, timezone, timedelta
    from irc.llm.cost_tracker import CostEntry, append_cost
    from irc.spend.record_run import record_command_run
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

    def _resolve_qdii_premium(
        asset_class: str, market: str, symbol: str
    ) -> float | None:
        return qdii_premium_for_row(
            asset_class=asset_class,
            market=market,
            fetcher=fetch_qdii_premium_pct,
            symbol=symbol,
        )

    news_summaries = build_news_summaries(
        reports=load_theme_reports(root),
        watchlist=watchlist,
    )
    populated = sum(1 for v in news_summaries.values() if v)
    print(f"news coverage: {populated}/{len(news_summaries)} instruments")

    _today_date = datetime.now(timezone(timedelta(hours=8))).date()
    history: list[CostEntry] = []
    try:
        out, llm_responses = run_scoring(
            watchlist=watchlist,
            metrics=metrics,
            news_summaries=news_summaries,
            regime_summary=regime,
            route=route,
            cfg_scoring=bundle.scoring,
            qdii_premium_resolver=_resolve_qdii_premium,
        )
        _ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
        for resp in llm_responses:
            history = append_cost(history, CostEntry(
                task=route.task, provider=route.provider, model=route.model,
                prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
                latency_ms=getattr(resp, "latency_ms", 0), ts=_ts,
            ))

        # Enrich each score entry with asset_class, role, and tracked_index
        # from the watchlist (allocation needs them for per-class grouping
        # and intra-index dedupe — see 2026-05-19-adversarial-fixes item 008).
        _meta_cols = ["instrument_id", "asset_class", "role", "tracked_index"]
        _have_meta = {"asset_class", "role"}.issubset(watchlist.columns)
        watchlist_meta = (
            watchlist[[c for c in _meta_cols if c in watchlist.columns]].drop_duplicates("instrument_id")
            if _have_meta
            else pd.DataFrame(columns=_meta_cols)
        )
        meta_by_id = watchlist_meta.set_index("instrument_id").to_dict("index")
        for entry in out["scores"]:
            m = meta_by_id.get(entry["instrument_id"], {})
            entry.setdefault("asset_class", m.get("asset_class", "unknown"))
            entry.setdefault("role", m.get("role", ""))
            entry.setdefault("tracked_index", m.get("tracked_index") or "")

        out_path = root / "outputs" / today / "scoring.json"
        atomic_write_text(out_path, json.dumps(out, ensure_ascii=False, indent=2))
        print(f"score OK: {len(out['scores'])} instruments → {out_path}")
        return 0
    finally:
        try:
            record_command_run(
                repo_root=root, history=history, search_units={}, today=_today_date,
            )
        except Exception:
            _logging.getLogger(__name__).warning("spend recorder failed", exc_info=True)
