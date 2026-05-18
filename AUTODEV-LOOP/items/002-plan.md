# 002 — Plan

## Step 1 — failing tests (Red)

### 1a. `tests/evals/test_registry.py` (new)

```python
"""Registry contract tests."""
from __future__ import annotations

import pytest

from evals._shared.registry import (
    REGISTRY,
    EvalStageSpec,
    active_suite_stages,
    get_spec,
    is_inactive,
)


def test_all_thirteen_known_stages_present() -> None:
    expected = {
        "data", "research", "discovery", "scoring", "gold_score",
        "allocation", "trade_plan", "memo", "architecture", "opportunity",
        "triggers", "news", "queries",
    }
    assert set(REGISTRY) == expected


def test_active_suite_excludes_news_and_queries() -> None:
    stages = active_suite_stages()
    assert "news" not in stages
    assert "queries" not in stages


def test_active_suite_includes_triggers_as_unimplemented_active() -> None:
    assert "triggers" in active_suite_stages()
    assert REGISTRY["triggers"].lifecycle == "unimplemented_active"


def test_news_is_inactive_legacy() -> None:
    spec = REGISTRY["news"]
    assert spec.lifecycle == "inactive_legacy"
    assert spec.in_all_suite is False
    assert is_inactive(spec) is True


def test_queries_is_inactive_uninstrumented() -> None:
    spec = REGISTRY["queries"]
    assert spec.lifecycle == "inactive_uninstrumented"
    assert spec.in_all_suite is False
    assert is_inactive(spec) is True


def test_get_spec_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_spec("ghost")


def test_runner_module_path_is_dotted_evals_path() -> None:
    for stage, spec in REGISTRY.items():
        assert spec.runner_module == f"evals.{stage}.runner"


def test_eval_stage_spec_is_frozen() -> None:
    spec = REGISTRY["data"]
    with pytest.raises(Exception):  # FrozenInstanceError subclasses Exception
        spec.stage = "other"  # type: ignore[misc]
```

### 1b. Extend `tests/commands/test_eval_cmd.py`

Add:

```python
def test_eval_inactive_news_returns_inactive_message(tmp_path, capsys):
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage="news", all_stages=False)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert rc == 2
    assert "inactive_legacy" in out.lower() or "inactive" in out.lower()
    assert "news" in out.lower()


def test_eval_inactive_queries_returns_inactive_message(tmp_path, capsys):
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage="queries", all_stages=False)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert rc == 2
    assert "inactive" in out.lower()
    assert "queries" in out.lower()


def test_eval_inactive_does_not_invoke_runner(tmp_path, monkeypatch):
    """Direct invocation of inactive stage must NOT touch the runner module
    (which would write a misleading missing-input report)."""
    from irc.commands import eval_cmd

    called: list[str] = []

    def fake_import(name: str):
        called.append(name)
        raise AssertionError(f"runner module {name} should not be imported for inactive stages")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage="news", all_stages=False)
    assert rc == 2
    assert called == []


def test_eval_all_excludes_inactive_stages(tmp_path, capsys):
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(str(tmp_path), stage=None, all_stages=True)
    captured = capsys.readouterr()
    out = (captured.out + captured.err).lower()
    assert "news" not in out
    assert "queries" not in out
    # active stages still listed
    for stage in ("data", "research", "discovery", "triggers"):
        assert stage in out
```

Run `uv run pytest tests/evals/test_registry.py tests/commands/test_eval_cmd.py -x` — every new test FAILs.

## Step 2 — implementation (Green)

### 2a. Create `evals/_shared/registry.py`

```python
"""Single source of truth for which evals exist and how they behave."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Lifecycle = Literal[
    "active",
    "inactive_legacy",
    "inactive_uninstrumented",
    "unimplemented_active",
]


@dataclass(frozen=True)
class EvalStageSpec:
    stage: str
    runner_module: str
    lifecycle: Lifecycle
    in_all_suite: bool


_SPECS: tuple[EvalStageSpec, ...] = (
    EvalStageSpec("data",         "evals.data.runner",         "active", True),
    EvalStageSpec("research",     "evals.research.runner",     "active", True),
    EvalStageSpec("discovery",    "evals.discovery.runner",    "active", True),
    EvalStageSpec("scoring",      "evals.scoring.runner",      "active", True),
    EvalStageSpec("gold_score",   "evals.gold_score.runner",   "active", True),
    EvalStageSpec("allocation",   "evals.allocation.runner",   "active", True),
    EvalStageSpec("trade_plan",   "evals.trade_plan.runner",   "active", True),
    EvalStageSpec("memo",         "evals.memo.runner",         "active", True),
    EvalStageSpec("architecture", "evals.architecture.runner", "active", True),
    EvalStageSpec("opportunity",  "evals.opportunity.runner",  "active", True),
    EvalStageSpec("triggers",     "evals.triggers.runner",     "unimplemented_active", True),
    EvalStageSpec("news",         "evals.news.runner",         "inactive_legacy", False),
    EvalStageSpec("queries",      "evals.queries.runner",      "inactive_uninstrumented", False),
)


REGISTRY: dict[str, EvalStageSpec] = {s.stage: s for s in _SPECS}


def get_spec(stage: str) -> EvalStageSpec:
    if stage not in REGISTRY:
        raise KeyError(f"unknown eval stage: {stage}")
    return REGISTRY[stage]


def active_suite_stages() -> tuple[str, ...]:
    return tuple(s.stage for s in _SPECS if s.in_all_suite)


def is_inactive(spec: EvalStageSpec) -> bool:
    return spec.lifecycle in ("inactive_legacy", "inactive_uninstrumented")
```

### 2b. Rewrite `src/irc/commands/eval_cmd.py`

```python
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from evals._shared.registry import (
    EvalStageSpec,
    active_suite_stages,
    get_spec,
    is_inactive,
)


def _resolve_runner(spec: EvalStageSpec) -> Callable[[Path], int]:
    mod = importlib.import_module(spec.runner_module)
    return mod.run


def run_eval(repo_root: str, stage: str | None, all_stages: bool) -> int:
    root = Path(repo_root)
    if all_stages:
        return _run_active_suite(root)
    if stage is None:
        print("ERROR: provide a stage or --all")
        return 2
    try:
        spec = get_spec(stage)
    except KeyError as e:
        print(f"ERROR: {e}")
        return 2
    if is_inactive(spec):
        print(
            f"{spec.stage} eval is {spec.lifecycle}; "
            f"not part of the active suite — no current artifact contract to evaluate"
        )
        return 2
    return _resolve_runner(spec)(root)


def _run_active_suite(root: Path) -> int:
    by_stage: dict[str, int] = {}
    for s in active_suite_stages():
        try:
            by_stage[s] = _resolve_runner(get_spec(s))(root)
        except Exception as e:  # noqa: BLE001 — keep one stage's failure from killing the suite
            print(f"eval {s} raised: {e}")
            by_stage[s] = 2
    _print_eval_summary(by_stage)
    return max(by_stage.values()) if by_stage else 0


def _print_eval_summary(by_stage: dict[str, int]) -> None:
    def label(rc: int) -> str:
        return {0: "PASS", 1: "WARN", 2: "FAIL"}.get(rc, f"rc={rc}")
    print("eval summary:")
    for stage, rc in by_stage.items():
        print(f"  {label(rc):4} {stage}")
    print(f"overall: {label(max(by_stage.values()))}")
```

Run `uv run pytest tests/evals/test_registry.py tests/commands/test_eval_cmd.py -x` — all PASS.

## Step 3 — full suite verification

```
uv run pytest -x
```

Must exit 0.

```
uv run ruff check evals src tests
```

Must exit 0.

```
uv run irc eval news
uv run irc eval queries
```

Both must print an inactive-stage message and exit non-zero, NOT raise ModuleNotFoundError or write a missing-input report under `outputs/`.

## Step 4 — commit

```
feat(evals): introduce eval registry with lifecycle classification (002)
```

## Notes / pitfalls

- The existing `test_run_eval_all_prints_summary` checks `rc == 2` and `"eval summary:" in out` and `"fail" in out`. All three still hold because every active stage will FAIL without inputs.
- The `--all` summary `max()` call must handle the empty-dict edge case in case someone marks every stage `in_all_suite=False`; default to 0 (PASS) since there's nothing to evaluate.
- `is_inactive` is a pure predicate — `unimplemented_active` is NOT inactive (triggers must run).
- Do not change rc semantics: inactive returns 2 (FAIL) so dashboards still treat misdirected invocations as a problem.
- Keep `importlib` import at module level so `monkeypatch.setattr(eval_cmd.importlib, "import_module", ...)` in tests works.
