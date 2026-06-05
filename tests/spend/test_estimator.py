from pathlib import Path
from irc.config_loader import load_yaml
from irc.spend.config import load_pricing
from irc.spend.profile import seed_profile
from irc.spend.estimator import estimate

REPO = Path(__file__).resolve().parents[2]


def _fixtures():
    llm = load_yaml(REPO / "config/llm.yaml", REPO)
    pricing = load_pricing(REPO)
    return llm, pricing, seed_profile(pricing)


def test_llm_estimate_matches_seed_times_price_for_one_task():
    llm, pricing, profile = _fixtures()
    out = estimate(frozenset({"memo_synthesis"}), frozenset(), llm, profile, pricing)
    # Derive expected from config so the test survives price recalibration.
    route = llm.tasks["memo_synthesis"]
    price = pricing.llm[route.provider].models[route.model]
    seed = pricing.seeds["memo_synthesis"]
    expected = seed.calls * (seed.prompt_tokens * price.input_per_mtok
                             + seed.completion_tokens * price.output_per_mtok) / 1e6
    assert out[route.provider].currency == pricing.llm[route.provider].currency
    assert abs(out[route.provider].amount - expected) < 1e-9
    assert out[route.provider].breakdown["memo_synthesis"] > 0


def test_search_estimate_uses_query_count_times_per_query():
    llm, pricing, profile = _fixtures()
    out = estimate(frozenset(), frozenset({"bocha"}), llm, profile, pricing)
    expected = pricing.search_seeds["bocha"].units * pricing.search["bocha"].per_query
    assert abs(out["bocha"].amount - expected) < 1e-9
    assert out["bocha"].currency == "CNY"


def test_currency_is_never_crossed_each_provider_has_one_currency():
    llm, pricing, profile = _fixtures()
    out = estimate(frozenset({"memo_synthesis", "scoring_rationale"}),
                   frozenset({"tavily", "bocha"}), llm, profile, pricing)
    # deepseek=CNY, tavily=credits, bocha=CNY — but each entry is a single currency
    assert all(isinstance(e.currency, str) and e.currency for e in out.values())
    assert out["tavily"].currency == "credits"
