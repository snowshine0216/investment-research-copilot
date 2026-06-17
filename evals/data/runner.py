from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.data.metrics import freshness_per_source, completeness_per_field


_PRICE_FRESHNESS_TH = {"warn_above": 2, "fail_above": 7}

# Only (source, table) pairs the live pipeline actually writes are graded.
# prices/nav_history come from akshare (cn_on_exchange; US is QDII-proxy now),
# macro_series comes from openbb. (openbb, prices) is dead 2023 seed data with
# no live writer — grading its freshness is a permanent false FAIL, so it is
# deliberately excluded. Keep this in sync with ingest_cmd's writers.
MAINTAINED_FRESHNESS_PAIRS = frozenset({
    ("akshare", "prices"),
    ("akshare", "nav_history"),
    ("openbb", "macro_series"),
})


def build_freshness_metrics(
    per_source: list[tuple[str, dict[str, int]]],
) -> list[MetricReport]:
    """PURE: per-source freshness ages → MetricReports, restricted to the
    (source, table) pairs the pipeline maintains."""
    metrics: list[MetricReport] = []
    for source, fresh in per_source:
        for tbl, age in fresh.items():
            if (source, tbl) not in MAINTAINED_FRESHNESS_PAIRS:
                continue
            metrics.append(MetricReport(
                name=f"freshness_{source}_{tbl}_days", value=float(age),
                status=classify_status(age, _PRICE_FRESHNESS_TH, "lower_is_better"),
                n_observations=1, threshold=_PRICE_FRESHNESS_TH,
            ))
    return metrics


def run(repo_root: Path) -> int:
    con = connect(repo_root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        ob_freshness = freshness_per_source(con, source="openbb")
        ak_freshness = freshness_per_source(con, source="akshare")
        completeness = completeness_per_field(con, table="prices")
    finally:
        con.close()
    metrics: list[MetricReport] = build_freshness_metrics(
        [("openbb", ob_freshness), ("akshare", ak_freshness)]
    )
    avg_completeness = sum(completeness.values()) / max(len(completeness), 1)
    metrics.append(MetricReport(
        name="prices_completeness_avg", value=avg_completeness,
        status=classify_status(avg_completeness, {"warn_below": 0.95, "fail_below": 0.85},
                                 "higher_is_better"),
        n_observations=len(completeness),
        threshold={"warn_below": 0.95, "fail_below": 0.85},
    ))
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="data",
        ran_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        based_on=[str(repo_root / "data" / "local.duckdb")],
        metrics=metrics,
        overall=overall,
    )
    out_dir = repo_root / "outputs" / datetime.now(timezone(timedelta(hours=8))).date().isoformat() / "evals" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    print(f"data eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)
