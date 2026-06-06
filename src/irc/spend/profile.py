from __future__ import annotations
from collections.abc import Mapping
from irc.schemas.spend import SpendPricingConfig
from irc.spend.types import TaskActual, TaskUsage, UsageProfile


def _ewma(old: float, observed: float, alpha: float) -> float:
    return alpha * observed + (1.0 - alpha) * old


def fold_actuals(
    profile: UsageProfile, actuals: Mapping[str, TaskActual],
) -> UsageProfile:
    """Pure (§5.4): EWMA-blend observed actuals into the profile per task.
    new = α·observed + (1−α)·old, samples += 1. Tasks absent from `actuals`
    are returned unchanged. Returns a NEW UsageProfile (no mutation)."""
    a = profile.alpha
    tasks = dict(profile.tasks)
    for task, obs in actuals.items():
        old = tasks.get(task)
        if old is None:
            continue
        tasks[task] = TaskUsage(
            task=task,
            avg_calls_per_run=_ewma(old.avg_calls_per_run, obs.calls, a),
            avg_prompt_tokens=_ewma(old.avg_prompt_tokens, obs.avg_prompt_tokens, a),
            avg_completion_tokens=_ewma(old.avg_completion_tokens, obs.avg_completion_tokens, a),
            samples=old.samples + 1,
        )
    return UsageProfile(tasks=tasks, alpha=a)


def seed_profile(pricing: SpendPricingConfig, *, alpha: float = 0.3) -> UsageProfile:
    """Build a cold (unlearned) profile from the seed table. Phase 1 uses this
    directly; Phase 2 will overlay learned EWMA values where samples > 0."""
    tasks = {
        name: TaskUsage(
            task=name,
            avg_calls_per_run=seed.calls,
            avg_prompt_tokens=seed.prompt_tokens,
            avg_completion_tokens=seed.completion_tokens,
            samples=0,
        )
        for name, seed in pricing.seeds.items()
    }
    return UsageProfile(tasks=tasks, alpha=alpha)
