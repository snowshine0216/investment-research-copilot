from irc.spend.types import CostEstimate, RunActuals, TaskActual
from irc.spend.estimate_io import estimate_to_dict, merge_actuals_dict


def test_estimate_to_dict_keeps_currency_per_provider():
    estimates = {
        "deepseek": CostEstimate("deepseek", "CNY", 12.5, {"memo_synthesis": 12.5}),
        "tavily": CostEstimate("tavily", "credits", 8.0, {"tavily": 8.0}),
    }
    d = estimate_to_dict(estimates)
    assert d["deepseek"] == {"currency": "CNY", "amount": 12.5,
                             "breakdown": {"memo_synthesis": 12.5}}
    assert d["tavily"]["currency"] == "credits"


def test_merge_actuals_accumulates_disjoint_stage_tasks_in_one_run():
    first = merge_actuals_dict({}, RunActuals(
        tasks={"memo_synthesis": TaskActual("memo_synthesis", 1.0, 1000.0, 500.0)},
        search_units={"tavily": 3}))
    second = merge_actuals_dict(first, RunActuals(
        tasks={"thesis_falsify": TaskActual("thesis_falsify", 2.0, 800.0, 200.0)},
        search_units={"tavily": 2}))
    assert set(second["tasks"]) == {"memo_synthesis", "thesis_falsify"}
    assert second["search_units"]["tavily"] == 5          # 3 + 2 accumulate


def test_merge_actuals_calls_weighted_means_a_repeated_task():
    # Q3(b): same task recorded twice in a day → calls-weighted token means, summed calls.
    first = merge_actuals_dict({}, RunActuals(
        tasks={"memo_synthesis": TaskActual("memo_synthesis", 1.0, 1000.0, 400.0)}, search_units={}))
    second = merge_actuals_dict(first, RunActuals(
        tasks={"memo_synthesis": TaskActual("memo_synthesis", 3.0, 2000.0, 800.0)}, search_units={}))
    t = second["tasks"]["memo_synthesis"]
    assert t["calls"] == 4.0                                       # 1 + 3
    assert t["avg_prompt_tokens"] == (1 * 1000.0 + 3 * 2000.0) / 4  # 1750.0, calls-weighted
    assert t["avg_completion_tokens"] == (1 * 400.0 + 3 * 800.0) / 4  # 700.0
