"""EDGE runner for `irc eval monitor_forward`. Reads forward_ledger.jsonl +
nav_history.jsonl, calls the pure cores, writes StageReport + details.json sibling.
No network, no LLM, no spend gate. rc 0 PASS / 1 WARN / 2 FAIL."""
from __future__ import annotations
import json
import logging
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals._shared.missing_input import (
    EVAL_RC_FAIL, EVAL_RC_PASS, EVAL_RC_WARN,
    missing_input_report, write_missing_input_report,
)
from evals._shared.report_paths import report_dir, write_report
from evals._shared.report_schema import StageReport
from evals._shared.status import worst_status
from irc.io_utils import atomic_write_text
from irc.monitor.eval.constants import FORWARD_H
from irc.monitor.eval.forward_score import score_forward
from irc.monitor.eval.nav_history import parse_nav_history_lines, latest_per_nav_date
from evals.monitor_forward.metrics import build_metric_reports

_log = logging.getLogger(__name__)
_TZ = timezone(timedelta(hours=8))
_STAGE = "monitor_forward"


def _today() -> str:
    return datetime.now(_TZ).date().isoformat()


def _read_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _nav_by_fund(text: str) -> dict[str, list[dict]]:
    rows = latest_per_nav_date(parse_nav_history_lines(text))
    by_fund: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_fund[r.fund_id].append({"fund_id": r.fund_id, "nav_date": r.nav_date,
                                   "nav_acc": r.nav_acc})
    return by_fund


def run(repo_root: Path) -> int:
    ledger_path = repo_root / "data" / "monitor" / "forward_ledger.jsonl"
    nav_path = repo_root / "data" / "monitor" / "nav_history.jsonl"
    today = _today()
    if not ledger_path.is_file():
        write_missing_input_report(repo_root, missing_input_report(
            stage=_STAGE,
            reason="data/monitor/forward_ledger.jsonl missing — producer never ran",
            based_on_path=str(ledger_path)), date_str=today)
        print(f"{_STAGE} eval: FAIL (no forward_ledger.jsonl)")
        return EVAL_RC_FAIL
    if not nav_path.is_file():
        write_missing_input_report(repo_root, missing_input_report(
            stage=_STAGE,
            reason="data/monitor/nav_history.jsonl missing — run the backfill",
            based_on_path=str(nav_path)), date_str=today)
        print(f"{_STAGE} eval: FAIL (no nav_history.jsonl)")
        return EVAL_RC_FAIL

    raw_lines = _read_lines(ledger_path)
    ledger: list[dict] = []
    for ln in raw_lines:
        try:
            ledger.append(json.loads(ln))
        except json.JSONDecodeError:
            _log.warning("skipping malformed forward_ledger line: %r", ln[:80])
    if raw_lines and not ledger:
        write_missing_input_report(repo_root, missing_input_report(
            stage=_STAGE,
            reason="forward_ledger.jsonl had lines but all were unparseable",
            based_on_path=str(ledger_path)), date_str=today)
        print(f"{_STAGE} eval: FAIL (all ledger lines malformed)")
        return EVAL_RC_FAIL
    nav_by_fund = _nav_by_fund(nav_path.read_text(encoding="utf-8"))
    try:
        forward_rows, _excl = score_forward(ledger, nav_by_fund, h=FORWARD_H, today=today)
    except ValueError as exc:
        write_missing_input_report(repo_root, missing_input_report(
            stage=_STAGE,
            reason=f"score_forward scorer-invariant violated: {exc}",
            based_on_path=str(ledger_path)), date_str=today)
        print(f"{_STAGE} eval: FAIL (scorer invariant: {exc})")
        return EVAL_RC_FAIL

    _log.info("monitor_forward forward exclusions: %s", _excl)
    reports, details = build_metric_reports(
        forward_rows=forward_rows, retro_points=[], seed=20260616)
    details["forward_excluded"] = _excl

    # write details.json sibling, then point each MetricReport at the repo-relative path
    out_dir = report_dir(repo_root, _STAGE, today)
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "details.json",
                      json.dumps(details, ensure_ascii=False, indent=2))
    rel = f"outputs/{today}/evals/{_STAGE}/details.json"
    reports = [replace(m, details_ref=rel) for m in reports]

    overall = worst_status([m.status for m in reports])
    report = StageReport(stage=_STAGE, ran_at=datetime.now(_TZ).isoformat(),
                         based_on=[str(ledger_path), str(nav_path)],
                         metrics=reports, overall=overall)
    write_report(repo_root, report, artifact_date=today)
    print(f"{_STAGE} eval: {overall}")
    return {"PASS": EVAL_RC_PASS, "WARN": EVAL_RC_WARN}.get(overall, EVAL_RC_FAIL)
