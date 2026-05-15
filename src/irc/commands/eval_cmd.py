from __future__ import annotations
from pathlib import Path
from typing import Callable
import importlib


def _get_runner(stage: str) -> Callable[[Path], int]:
    runners: dict[str, str] = {
        "data":         "evals.data.runner",
        "news":         "evals.news.runner",
        "research":     "evals.research.runner",
        "discovery":    "evals.discovery.runner",
        "scoring":      "evals.scoring.runner",
        "gold_score":   "evals.gold_score.runner",
        "allocation":   "evals.allocation.runner",
        "trade_plan":   "evals.trade_plan.runner",
        "memo":         "evals.memo.runner",
        "queries":      "evals.queries.runner",
        "triggers":     "evals.triggers.runner",
        "architecture": "evals.architecture.runner",
        "opportunity":  "evals.opportunity.runner",
    }
    if stage not in runners:
        raise KeyError(f"unknown eval stage: {stage}")
    mod = importlib.import_module(runners[stage])
    return mod.run


def run_eval(repo_root: str, stage: str | None, all_stages: bool) -> int:
    root = Path(repo_root)
    if all_stages:
        stages = (
            "data", "news", "research", "discovery", "scoring",
            "gold_score", "allocation", "trade_plan",
            "memo", "queries", "triggers", "architecture", "opportunity",
        )
        by_stage: dict[str, int] = {}
        for s in stages:
            try:
                rc = _get_runner(s)(root)
            except Exception as e:
                print(f"eval {s} raised: {e}")
                rc = 2
            by_stage[s] = rc
        _print_eval_summary(by_stage)
        return max(by_stage.values())
    if stage is None:
        print("ERROR: provide a stage or --all")
        return 2
    try:
        return _get_runner(stage)(root)
    except KeyError as e:
        print(f"ERROR: {e}")
        return 2


def _print_eval_summary(by_stage: dict[str, int]) -> None:
    def label(rc: int) -> str:
        return {0: "PASS", 1: "WARN", 2: "FAIL"}.get(rc, f"rc={rc}")
    print("eval summary:")
    for stage, rc in by_stage.items():
        print(f"  {label(rc):4} {stage}")
    worst = max(by_stage.values())
    print(f"overall: {label(worst)}")
