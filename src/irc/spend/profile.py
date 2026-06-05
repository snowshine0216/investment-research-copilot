from __future__ import annotations
from irc.schemas.spend import SpendPricingConfig
from irc.spend.types import TaskUsage, UsageProfile


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
