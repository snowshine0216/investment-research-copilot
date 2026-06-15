from __future__ import annotations
from irc.schemas.llm import LLMConfig
from irc.schemas.spend import SpendPricingConfig
from irc.spend.types import CostEstimate, UsageProfile


def _resolve_priced_model(provider_pricing, route_model: str | None) -> str:
    """Env-resolved models (route.model is None) price under the provider's first
    seeded model id (preflight is secret-free; actuals use the real model)."""
    if route_model is not None:
        return route_model
    return next(iter(provider_pricing.models))


def _llm_estimates(
    tasks: frozenset[str], llm: LLMConfig, profile: UsageProfile, pricing: SpendPricingConfig,
) -> dict[str, tuple[str, float, dict[str, float]]]:
    acc: dict[str, tuple[str, float, dict[str, float]]] = {}
    for task in sorted(tasks):
        route = llm.tasks[task]
        provider = route.provider
        provider_pricing = pricing.llm[provider]
        priced_model = _resolve_priced_model(provider_pricing, route.model)
        price = provider_pricing.models[priced_model]
        usage = profile.tasks[task]
        cost = usage.avg_calls_per_run * (
            usage.avg_prompt_tokens * price.input_per_mtok
            + usage.avg_completion_tokens * price.output_per_mtok
        ) / 1_000_000.0
        currency = provider_pricing.currency
        prev_amt, prev_break = (acc[provider][1], dict(acc[provider][2])) if provider in acc else (0.0, {})
        prev_break[task] = cost
        acc[provider] = (currency, prev_amt + cost, prev_break)
    return acc


def estimate(
    tasks: frozenset[str],
    search_providers: frozenset[str],
    llm: LLMConfig,
    profile: UsageProfile,
    pricing: SpendPricingConfig,
) -> dict[str, CostEstimate]:
    """Pure: scoped tasks + search providers → per-provider cost estimate, each in
    that provider's own currency. Currencies are never summed across providers."""
    out: dict[str, CostEstimate] = {}
    for provider, (currency, amount, breakdown) in _llm_estimates(tasks, llm, profile, pricing).items():
        out[provider] = CostEstimate(provider, currency, amount, breakdown)
    for provider in sorted(search_providers):
        sp = pricing.search.get(provider)
        seed = pricing.search_seeds.get(provider)
        if sp is None or seed is None:
            continue
        per_unit = sp.per_query if sp.per_query is not None else sp.per_page
        amount = seed.units * float(per_unit)
        out[provider] = CostEstimate(provider, sp.currency, amount, {provider: amount})
    return out
