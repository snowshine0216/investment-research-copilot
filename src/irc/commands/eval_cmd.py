from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from evals._shared.registry import (
    EvalStageSpec,
    active_suite_stages,
    get_spec,
    is_inactive,
)


def _resolve_runner(spec: EvalStageSpec) -> Callable[[Path], int]:
    mod = importlib.import_module(spec.runner_module)
    return mod.run


def run_eval(repo_root: str, stage: str | None, all_stages: bool) -> int:
    root = Path(repo_root)
    if all_stages:
        return _run_active_suite(root)
    if stage is None:
        print("ERROR: provide a stage or --all")
        return 2
    try:
        spec = get_spec(stage)
    except KeyError as e:
        print(f"ERROR: {e}")
        return 2
    if is_inactive(spec):
        print(
            f"{spec.stage} eval is {spec.lifecycle}; "
            f"not part of the active suite — no current artifact contract to evaluate"
        )
        return 2
    return _resolve_runner(spec)(root)


def _run_active_suite(root: Path) -> int:
    by_stage: dict[str, int] = {}
    for s in active_suite_stages():
        try:
            by_stage[s] = _resolve_runner(get_spec(s))(root)
        except Exception as e:  # noqa: BLE001 — one stage failing must not kill the suite
            print(f"eval {s} raised: {e}")
            by_stage[s] = 2
    _print_eval_summary(by_stage)
    return max(by_stage.values()) if by_stage else 0


def _print_eval_summary(by_stage: dict[str, int]) -> None:
    def label(rc: int) -> str:
        return {0: "PASS", 1: "WARN", 2: "FAIL"}.get(rc, f"rc={rc}")
    print("eval summary:")
    for stage, rc in by_stage.items():
        print(f"  {label(rc):4} {stage}")
    if by_stage:
        print(f"overall: {label(max(by_stage.values()))}")
