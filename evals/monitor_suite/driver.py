"""Shared EDGE helpers for the two live LLM-suite runners (M1 §3.3).
drive_case is the ONLY effectful function (calls the injected gateway `call`);
cost_entry_from and build_stage_report are pure. Keeps each runner < 200 lines."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from evals._shared.report_schema import MetricReport, StageReport
from evals._shared.status import classify_status, worst_status
from irc.llm.cost_tracker import CostEntry
from irc.llm._types import ChatResponse
from irc.monitor.json_extract import extract_json

_log = logging.getLogger(__name__)
_TZ = timezone(timedelta(hours=8))


def _ts() -> str:
    return datetime.now(_TZ).isoformat()


def cost_entry_from(task: str, provider: str, model: str, resp: ChatResponse) -> CostEntry:
    """Pure: one ChatResponse → one CostEntry (mirrors impacts.py:74)."""
    return CostEntry(
        task=task, provider=provider, model=model,
        prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
        latency_ms=getattr(resp, "latency_ms", 0), ts=_ts(),
    )


def drive_case(
    *, task: str, messages: list[dict], route, call, provider: str, model: str,
) -> tuple[dict, CostEntry | None, bool]:
    """EDGE: one real gateway call for one case. Returns (parsed_output, cost, ok).
    Transport error → ({}, None, False) (no billed call, §5). Parse error →
    ({}, cost, False) (the call WAS billed). The scorer treats {} as a
    category failure, so a degraded case never crashes the run (AC13).
    All swallowed errors are logged with exc_info (Finding 7)."""
    try:
        resp = call(task, messages, route, temperature=0, max_tokens=2048)
    except Exception:  # noqa: BLE001 — degrade per-case, never crash the suite
        _log.warning("drive_case transport error for task=%s; degrading case", task,
                     exc_info=True)
        return {}, None, False
    if resp is None or not hasattr(resp, "prompt_tokens"):
        return {}, None, False
    cost = cost_entry_from(task, provider, model, resp)
    try:
        return extract_json(resp.text), cost, True
    except Exception:  # noqa: BLE001 — unparseable output → category failure
        _log.warning("drive_case parse error for task=%s; degrading case", task,
                     exc_info=True)
        return {}, cost, False


def build_case_details(cases, outputs) -> list[dict]:
    """Pure: per-case diagnostic rows so a metric FAIL is explainable from the
    artifact — which case (index + category), its expected band, and the RAW model
    output. The aggregate StageReport only carries metric fractions; without this a
    FAIL (e.g. magnitude_band_pass=0.667) can't be traced to a case without re-running.
    Inputs (evidence_pool/messages_seed) are intentionally not echoed."""
    return [
        {"index": i, "category": c.get("category"),
         "expected": c.get("expected", {}), "output": o}
        for i, (c, o) in enumerate(zip(cases, outputs))
    ]


def build_stage_report(
    *, stage: str, named_values, n: int, based_on: list[str],
) -> StageReport:
    """Pure: [(name, value, threshold, direction)] → StageReport.
    overall = worst metric status."""
    metrics = [
        MetricReport(name=name, value=value,
                     status=classify_status(value, threshold, direction),
                     n_observations=n, threshold=threshold)
        for (name, value, threshold, direction) in named_values
    ]
    overall = worst_status([m.status for m in metrics])
    return StageReport(stage=stage, ran_at=_ts(), based_on=based_on,
                       metrics=metrics, overall=overall)
