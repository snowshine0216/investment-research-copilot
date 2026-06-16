"""Single source of truth for which evals exist and how they behave.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/002-spec.md

Lifecycle states:
- ``active``                  — runs as a real measurement of a live producer.
- ``unimplemented_active``    — kept in the active suite so its absence shows
                                up as an honest FAIL (e.g. ``triggers``).
- ``inactive_legacy``         — runner exists but no live producer in the
                                current pipeline (e.g. ``news``).
- ``inactive_uninstrumented`` — feature is live but writes no persisted
                                artifact (e.g. ``queries`` / ``irc ask``).

Inactive stages are excluded from ``--all`` and produce a clear inactive-stage
CLI message when invoked directly — they do NOT pretend their input artifact
is missing (the previous behavior masked retirement decisions behind generic
FAIL reports).

Active-but-excluded-from-``--all``: a stage may be ``lifecycle="active"`` yet
``in_all_suite=False`` when it is informational and data-dependent (its inputs
accrue slowly), so it must NOT make the green ``--all`` suite data-dependent.
``monitor_forward`` (M3 predictive-validity backtest) is the first such stage:
run it by name (``irc eval monitor_forward``), scheduled/CI weekly; it never
enters ``active_suite_stages()``. Do NOT "fix" it into ``--all``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Lifecycle = Literal[
    "active",
    "inactive_legacy",
    "inactive_uninstrumented",
    "unimplemented_active",
    "live_gated",
]


@dataclass(frozen=True)
class EvalStageSpec:
    stage: str
    runner_module: str
    lifecycle: Lifecycle
    in_all_suite: bool


_SPECS: tuple[EvalStageSpec, ...] = (
    EvalStageSpec("data",         "evals.data.runner",         "active", True),
    EvalStageSpec("research",     "evals.research.runner",     "active", True),
    EvalStageSpec("discovery",    "evals.discovery.runner",    "active", True),
    EvalStageSpec("scoring",      "evals.scoring.runner",      "active", True),
    EvalStageSpec("gold_score",   "evals.gold_score.runner",   "active", True),
    EvalStageSpec("allocation",   "evals.allocation.runner",   "active", True),
    EvalStageSpec("trade_plan",   "evals.trade_plan.runner",   "active", True),
    EvalStageSpec("memo",         "evals.memo.runner",         "active", True),
    EvalStageSpec("architecture", "evals.architecture.runner", "active", True),
    EvalStageSpec("opportunity",  "evals.opportunity.runner",  "active", True),
    EvalStageSpec("triggers",     "evals.triggers.runner",     "unimplemented_active", True),
    EvalStageSpec("news",         "evals.news.runner",         "inactive_legacy", False),
    EvalStageSpec("queries",      "evals.queries.runner",      "inactive_uninstrumented", False),
    EvalStageSpec("monitor_signal",    "evals.monitor_signal.runner",    "active", True),
    EvalStageSpec("monitor_impact",    "evals.monitor_impact.runner",    "live_gated", False),
    EvalStageSpec("monitor_narrative", "evals.monitor_narrative.runner", "live_gated", False),
    EvalStageSpec("monitor_forward",   "evals.monitor_forward.runner",   "active", False),
)


REGISTRY: dict[str, EvalStageSpec] = {s.stage: s for s in _SPECS}


def get_spec(stage: str) -> EvalStageSpec:
    if stage not in REGISTRY:
        raise KeyError(f"unknown eval stage: {stage}")
    return REGISTRY[stage]


def active_suite_stages() -> tuple[str, ...]:
    return tuple(s.stage for s in _SPECS if s.in_all_suite)


def is_inactive(spec: EvalStageSpec) -> bool:
    return spec.lifecycle in ("inactive_legacy", "inactive_uninstrumented")


def is_live_gated(spec: EvalStageSpec) -> bool:
    return spec.lifecycle == "live_gated"
