from __future__ import annotations
from collections.abc import Mapping, Sequence
from irc.llm.cost_tracker import CostEntry
from irc.spend.types import RunActuals, TaskActual


def actuals_from_costs(
    history: Sequence[CostEntry], *, search_units: Mapping[str, int],
) -> RunActuals:
    """Pure: a run's CostEntry history + per-provider search counts → RunActuals.
    Per task: call count, mean prompt tokens, mean completion tokens."""
    by_task: dict[str, list[CostEntry]] = {}
    for entry in history:
        by_task.setdefault(entry.task, []).append(entry)
    tasks = {
        task: TaskActual(
            task=task,
            calls=float(len(entries)),
            avg_prompt_tokens=sum(e.prompt_tokens for e in entries) / len(entries),
            avg_completion_tokens=sum(e.completion_tokens for e in entries) / len(entries),
        )
        for task, entries in by_task.items()
    }
    return RunActuals(tasks=tasks, search_units=dict(search_units))
