from __future__ import annotations
from dataclasses import dataclass

# NOTE: stage→task rows reflect each stage's call() sites. The completeness test
# (test_every_llm_yaml_task_is_mapped_somewhere) guards against an unmapped task
# silently escaping the gate. Verify exact rows against call sites when wiring.
STAGE_TASKS: dict[str, tuple[str, ...]] = {
    "research": ("research_synth", "news_summary", "news_dedup"),
    "discover": ("factor_screening", "watchlist_reason"),
    "score": ("scoring_rationale",),
    "opportunity": ("thesis_falsify", "thesis_defend"),
    "memo": ("memo_synthesis", "memo_audit"),
}

COMMAND_TASKS: dict[str, tuple[str, ...]] = {
    "ask": ("interactive_query",),
    "eval-funds": ("scoring_rationale", "thesis_falsify", "thesis_defend"),
    "narrative": ("scoring_rationale", "thesis_falsify", "thesis_defend"),
    "opportunity": ("thesis_falsify", "thesis_defend"),
    "memo": ("memo_synthesis", "memo_audit"),
    "monitor": ("monitor_impact", "monitor_narrative"),
    "eval-live": ("monitor_impact", "monitor_narrative"),
    "decision": (),
}

STAGE_SEARCH_PROVIDERS: dict[str, tuple[str, ...]] = {
    "research": ("tavily", "brave", "bocha", "jina"),
}

# NEW: command-level search providers (mirrors STAGE_SEARCH_PROVIDERS for `run`).
COMMAND_SEARCH_PROVIDERS: dict[str, tuple[str, ...]] = {
    "monitor": ("tavily", "brave", "bocha", "jina"),
}

ALL_LLM_TASKS: frozenset[str] = frozenset(
    t for tasks in STAGE_TASKS.values() for t in tasks
) | frozenset(t for tasks in COMMAND_TASKS.values() for t in tasks)


@dataclass(frozen=True)
class Scope:
    tasks: frozenset[str]
    search_providers: frozenset[str]


def resolve_scope(command: str, *, stages: tuple[str, ...] | None = None) -> Scope:
    """Pure: command (+ the stages that will actually run, for `run`) → the tasks
    and search providers that will fire."""
    if command == "run":
        run_stages = stages or tuple(STAGE_TASKS)
        tasks = frozenset(t for s in run_stages for t in STAGE_TASKS.get(s, ()))
        search = frozenset(
            p for s in run_stages for p in STAGE_SEARCH_PROVIDERS.get(s, ())
        )
        return Scope(tasks=tasks, search_providers=search)
    return Scope(
        tasks=frozenset(COMMAND_TASKS.get(command, ())),
        search_providers=frozenset(COMMAND_SEARCH_PROVIDERS.get(command, ())),
    )
