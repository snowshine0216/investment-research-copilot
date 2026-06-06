from __future__ import annotations
from collections.abc import Mapping
from irc.spend.types import CostEstimate, RunActuals


def estimate_to_dict(estimates: Mapping[str, CostEstimate]) -> dict:
    """Pure: per-provider estimate → JSON-ready dict (currency never crossed)."""
    return {
        p: {"currency": e.currency, "amount": e.amount, "breakdown": dict(e.breakdown)}
        for p, e in estimates.items()
    }


def _wmean(c1: float, v1: float, c2: float, v2: float) -> float:
    total = c1 + c2
    return (c1 * v1 + c2 * v2) / total if total else 0.0


def merge_actuals_dict(existing: Mapping, actuals: RunActuals) -> dict:
    """Pure (Q3b): accumulate one command's RunActuals into the date-level actuals dict
    as the cumulative actual usage for the date. A repeated task sums calls and takes
    calls-weighted token means; search units sum — both halves uniformly cumulative."""
    tasks = dict(existing.get("tasks", {}))
    for name, a in actuals.tasks.items():
        prev = tasks.get(name)
        if prev is None:
            tasks[name] = {"calls": a.calls, "avg_prompt_tokens": a.avg_prompt_tokens,
                           "avg_completion_tokens": a.avg_completion_tokens}
            continue
        tasks[name] = {
            "calls": prev["calls"] + a.calls,
            "avg_prompt_tokens": _wmean(prev["calls"], prev["avg_prompt_tokens"],
                                        a.calls, a.avg_prompt_tokens),
            "avg_completion_tokens": _wmean(prev["calls"], prev["avg_completion_tokens"],
                                            a.calls, a.avg_completion_tokens),
        }
    units = dict(existing.get("search_units", {}))
    for provider, n in actuals.search_units.items():
        units[provider] = int(units.get(provider, 0)) + int(n)
    return {"tasks": tasks, "search_units": units}
