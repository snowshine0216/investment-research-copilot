from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Callable

from evals._shared.missing_input import (
    EVAL_RC_SKIPPED,
    skipped_report,
    write_missing_input_report,
)
from evals._shared.registry import (
    EvalStageSpec,
    active_suite_stages,
    get_spec,
    is_inactive,
    is_live_gated,
)
from irc.commands.spend_cmd import preflight_gate

_log = logging.getLogger(__name__)

_LIVE_ENV = "IRC_RUN_LIVE_LLM_EVAL"
_TRUE = {"1", "true", "yes", "on"}


def _resolve_runner(spec: EvalStageSpec) -> Callable[[Path], int]:
    mod = importlib.import_module(spec.runner_module)
    return mod.run


def _run_live_gated(root: Path, spec: EvalStageSpec) -> int:
    """SKIPPED when the env gate is unset; otherwise budget-gate before dispatch."""
    if os.environ.get(_LIVE_ENV, "").strip().lower() not in _TRUE:
        report = skipped_report(spec.stage, "env absent; not executed")
        write_missing_input_report(root, report)
        print(f"{spec.stage} eval: SKIPPED (env absent; not executed)")
        return EVAL_RC_SKIPPED
    gate = preflight_gate(str(root), "eval-live")
    if gate != 0:
        return gate
    return _resolve_runner(spec)(root)


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
    if is_live_gated(spec):
        return _run_live_gated(root, spec)
    return _resolve_runner(spec)(root)


def _run_active_suite(root: Path) -> int:
    by_stage: dict[str, int] = {}
    for s in active_suite_stages():
        try:
            by_stage[s] = _resolve_runner(get_spec(s))(root)
        except Exception:  # noqa: BLE001 — one stage failing must not kill the suite
            _log.exception("eval stage %s raised", s)
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
