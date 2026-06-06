from irc.llm.cost_tracker import CostEntry
from irc.spend.recorder import actuals_from_costs


def _entry(task, p, c):
    return CostEntry(task=task, provider="deepseek", model="deepseek-chat",
                     prompt_tokens=p, completion_tokens=c, latency_ms=10, ts="2026-06-06T01:00:00+08:00")


def test_groups_by_task_counts_calls_and_averages_tokens():
    history = [_entry("memo_synthesis", 1000, 400),
               _entry("memo_synthesis", 2000, 600),
               _entry("memo_audit", 500, 100)]
    actuals = actuals_from_costs(history, search_units={"tavily": 3})
    syn = actuals.tasks["memo_synthesis"]
    assert syn.calls == 2.0
    assert syn.avg_prompt_tokens == 1500.0          # (1000+2000)/2
    assert syn.avg_completion_tokens == 500.0        # (400+600)/2
    assert actuals.tasks["memo_audit"].calls == 1.0
    assert actuals.search_units == {"tavily": 3}


def test_empty_history_yields_no_tasks():
    actuals = actuals_from_costs([], search_units={})
    assert actuals.tasks == {}
    assert actuals.search_units == {}
