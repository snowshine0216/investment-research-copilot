from pathlib import Path
from irc.config_loader import load_yaml
from irc.spend.scope import resolve_scope, ALL_LLM_TASKS

REPO = Path(__file__).resolve().parents[2]


def test_run_scope_with_research_includes_search_providers():
    scope = resolve_scope("run", stages=("research", "score", "memo"))
    assert "scoring_rationale" in scope.tasks
    assert "memo_synthesis" in scope.tasks
    assert "tavily" in scope.search_providers


def test_run_scope_without_research_has_no_search_providers():
    scope = resolve_scope("run", stages=("score", "memo"))
    assert scope.search_providers == frozenset()


def test_ask_scope_is_interactive_query_only():
    scope = resolve_scope("ask")
    assert scope.tasks == frozenset({"interactive_query"})


def test_every_llm_yaml_task_is_mapped_somewhere():
    llm = load_yaml(REPO / "config/llm.yaml", REPO)
    assert set(llm.tasks) <= ALL_LLM_TASKS, (
        f"unmapped tasks escape the gate: {set(llm.tasks) - ALL_LLM_TASKS}"
    )
