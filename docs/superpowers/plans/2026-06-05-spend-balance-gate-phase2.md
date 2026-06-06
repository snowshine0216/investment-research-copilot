# Spend / Balance Gate — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the spend gate *learn*: capture each run's actual paid-API usage, fold it into a rolling EWMA usage profile so the next estimate converges on reality, auto-decrement the local ledger, and emit estimated-vs-actual artifacts — hands-off on every gated run.

**Architecture:** Pure cores + I/O at the command edge, honouring the repo's two hard rules at once (locked by [ADR 0013](../../adr/0013-spend-recorder-usage-as-data.md)). LLM token actuals ride home **as data**: stage cores already return `ChatResponse` (carrying `prompt_tokens`/`completion_tokens`) and the `ResolvedRoute` carries `.task`, so each gated **command edge** accumulates a `list[CostEntry]` (via the existing pure `append_cost`) — no `recorder` param leaks into a pure core (purity preserved) and no module-global accumulator exists (no shared mutable state). At command end the edge folds actuals → `usage_profile.json` (EWMA, §5.4), decrements `consumption.json`, and writes `outputs/<date>/spend_actuals.json`; the gate writes `spend_estimate.json` at start. The estimator is unchanged — it already consumes a `UsageProfile`; Phase 2 just feeds it the **effective profile** (learned where `samples>0`, seed where `samples==0`).

**Tech Stack:** Python 3.12, frozen dataclasses, pydantic (`schemas/spend.py`), DuckDB-free JSON state under `data/spend/`, `io_utils.atomic_write_text` (`.tmp → os.replace`), pytest (no-mock pure-core tests + tmp-repo edge tests). Conventions: TDD red→green→refactor, files <200 lines, funcs <20 lines, ruff line-length 100.

---

## Context for the implementer (read once)

- **Spec:** `docs/superpowers/specs/2026-06-05-spend-balance-gate-design.md` — §3.2 (convergence flow), §4 (data contracts), §5.4 (EWMA), §5.5 (estimator), §6.2/§6.3 (ledger), §10 (Phase 2 scope), §12 (artifacts + auto-convergence + trigger commands), §13 (README), §15.2 (exit gate).
- **Handoff:** `docs/superpowers/plans/2026-06-05-spend-balance-gate-phase2-HANDOFF.md`.
- **Calibration is decided (§16.1 item 5):** convergence is proven with **simulated/injected actuals — no real spend**. Every test below is deterministic.
- **The seam (verified):**
  - `src/irc/llm/cost_tracker.py` already defines `CostEntry(task, provider, model, prompt_tokens, completion_tokens, latency_ms, ts)` and a **pure** `append_cost(history, entry) -> [*history, entry]`. **Unwired today** — Phase 2 wires it at the command edges.
  - True LLM choke point: `call_chat(route, messages, …) -> ChatResponse` in `src/irc/llm/http_client.py` (`ChatResponse.prompt_tokens/.completion_tokens` parsed at lines 87-93). `ResolvedRoute.task/.provider/.model` available.
  - Stage cores return `ChatResponse` to their command (e.g. `memo/synthesizer.py:synthesize_memo(...) -> ChatResponse`, `memo/auditor.py`, `queries/responder.py`). The command edge is where usage is observable.
  - Search choke points: `research/search/dispatch.py:multi_provider_search` (1 query unit per `provider.search()`) and `extract_top_pages` (1 page unit per `extractor.extract()`); `provider.name` / `extractor.name` available.
  - Atomic write: `io_utils.atomic_write_text(path, content)`.
  - Ledger read path (reuse): `spend/ledger.py:effective_balance` reads `consumption[provider]` → wallet `{consumed_since, since}` / quota `{consumed_this_period, period_start}`.
  - Gate edge: `commands/spend_cmd.py:preflight_gate` → `spend/preflight.py:run_preflight`. `run_cmd.py:_gate` (line 98) calls it; stages run as sub-runners (`rc = fn(repo_root)`), so **each gated command records its own slice**.
- **Tasks are stage-disjoint** (`spend/scope.py:STAGE_TASKS`): `memo_synthesis/memo_audit` only in memo; `thesis_falsify/thesis_defend` only in opportunity; etc. So per-command EWMA folding never double-folds one task within a single `irc run`.
- **Test gotchas (Phase 1, preserve):** autouse `IRC_SKIP_SPEND_GATE` fixture in `tests/conftest.py` bypasses the gate in tests; `run_preflight` ignores that flag (only `preflight_gate` checks it). Unit-test the recorder edge with injected actuals + a fixed `today` + a `tmp_path` repo. `config/` is gitignored → any new committed config is `git add -f`'d. `基金概况` ban is unrelated here.

## File map (what each file owns after Phase 2)

| File | Change | Responsibility |
|---|---|---|
| `src/irc/spend/types.py` | **modify** | add `TaskActual`, `RunActuals` frozen dataclasses |
| `src/irc/spend/recorder.py` | **create** | pure: `CostEntry` history + search counts → `RunActuals`; `actuals_to_dict` |
| `src/irc/spend/profile.py` | **modify** | add `fold_actuals` (EWMA) + `effective_profile` (samples fallback) |
| `src/irc/spend/ledger.py` | **modify** | add pure `apply_usage` (wallet/quota decrement writer-side) |
| `src/irc/spend/config.py` | **modify** | add `load_usage_profile_raw` / `write_usage_profile` / `write_consumption` (atomic) |
| `src/irc/spend/estimate_io.py` | **create** | pure `estimate_to_dict`; merge-aware actuals dict builder |
| `src/irc/spend/preflight.py` | **modify** | write `spend_estimate.json` at start; use effective profile |
| `src/irc/spend/record_run.py` | **create** | edge orchestrator: accumulate → merge actuals file → fold profile → decrement ledger |
| `src/irc/commands/memo_cmd.py` | **modify** | accumulate `CostEntry`s; call `record_command_run` at end (first proven wiring) |
| `src/irc/commands/{opportunity,decision,eval_funds,narrative,ask}_cmd.py` | **modify** | same edge hook (Task 9, incremental) |
| `README.md` | **modify** | "Spend / balance gate" §13 expansion |
| `tests/spend/test_recorder.py`, `test_profile.py`, `test_ledger.py`, `test_estimate_io.py`, `test_record_run.py` | create/modify | TDD |
| `tests/commands/test_memo_recorder.py`, `tests/docs/test_readme_spend.py` | create | integration + docs grep |

---

### Task 1: `TaskActual` / `RunActuals` data contracts

**Files:**
- Modify: `src/irc/spend/types.py`
- Test: `tests/spend/test_types.py`

- [ ] **Step 1: Write the failing test** — append to `tests/spend/test_types.py`:

```python
from irc.spend.types import TaskActual, RunActuals


def test_task_actual_is_frozen_and_holds_per_run_means():
    a = TaskActual(task="memo_synthesis", calls=2.0,
                   avg_prompt_tokens=1500.0, avg_completion_tokens=900.0)
    assert (a.task, a.calls, a.avg_prompt_tokens, a.avg_completion_tokens) == (
        "memo_synthesis", 2.0, 1500.0, 900.0)
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        a.calls = 3.0  # type: ignore[misc]


def test_run_actuals_groups_tasks_and_search_units():
    r = RunActuals(
        tasks={"memo_synthesis": TaskActual("memo_synthesis", 1.0, 1000.0, 500.0)},
        search_units={"tavily": 4},
    )
    assert r.tasks["memo_synthesis"].calls == 1.0
    assert r.search_units["tavily"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_types.py -q`
Expected: FAIL — `ImportError: cannot import name 'TaskActual'`.

- [ ] **Step 3: Write minimal implementation** — append to `src/irc/spend/types.py`:

```python
@dataclass(frozen=True)
class TaskActual:
    """One run's observed usage for a single llm.yaml task (means per call)."""
    task: str
    calls: float
    avg_prompt_tokens: float
    avg_completion_tokens: float


@dataclass(frozen=True)
class RunActuals:
    """A gated command's measured paid usage: LLM per task + search units per provider."""
    tasks: Mapping[str, TaskActual]
    search_units: Mapping[str, int]
```

(`Mapping` and `dataclass` are already imported at the top of `types.py`; if not, add `from collections.abc import Mapping` / `from dataclasses import dataclass`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_types.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/types.py tests/spend/test_types.py
git commit -m "feat(spend): TaskActual/RunActuals contracts for Phase 2 recorder"
```

---

### Task 2: `recorder.py` — pure actuals from CostEntry history

**Files:**
- Create: `src/irc/spend/recorder.py`
- Test: `tests/spend/test_recorder.py`

- [ ] **Step 1: Write the failing test** — create `tests/spend/test_recorder.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_recorder.py -q`
Expected: FAIL — `ModuleNotFoundError: irc.spend.recorder`.

- [ ] **Step 3: Write minimal implementation** — create `src/irc/spend/recorder.py`:

```python
from __future__ import annotations
from collections.abc import Mapping, Sequence
from irc.llm.cost_tracker import CostEntry
from irc.spend.types import RunActuals, TaskActual


def actuals_from_costs(
    history: Sequence[CostEntry], *, search_units: Mapping[str, int],
) -> RunActuals:
    """Pure: a run's CostEntry history + per-provider search counts → RunActuals.
    Per task: call count, mean prompt tokens, mean completion tokens."""
    by_task: dict[str, list[CostEntry]] = {}
    for entry in history:
        by_task.setdefault(entry.task, []).append(entry)
    tasks = {
        task: TaskActual(
            task=task,
            calls=float(len(entries)),
            avg_prompt_tokens=sum(e.prompt_tokens for e in entries) / len(entries),
            avg_completion_tokens=sum(e.completion_tokens for e in entries) / len(entries),
        )
        for task, entries in by_task.items()
    }
    return RunActuals(tasks=tasks, search_units=dict(search_units))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_recorder.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/recorder.py tests/spend/test_recorder.py
git commit -m "feat(spend): pure recorder — CostEntry history → RunActuals"
```

---

### Task 3: EWMA fold + learned/seed blend in `profile.py`

**Files:**
- Modify: `src/irc/spend/profile.py`
- Test: `tests/spend/test_profile.py`

This is the **convergence proof** (§15.2 box 2).

- [ ] **Step 1: Write the failing test** — append to `tests/spend/test_profile.py`:

```python
from irc.spend.profile import fold_actuals
from irc.spend.types import UsageProfile, TaskUsage, TaskActual


def _seeded(task, calls, p, c, *, alpha=0.3):
    return UsageProfile(tasks={task: TaskUsage(task, calls, p, c, samples=0)}, alpha=alpha)


def test_fold_moves_estimate_toward_actual_and_increments_samples():
    profile = _seeded("memo_synthesis", calls=4.0, p=4000.0, c=2000.0)  # high cold seed
    actual = {"memo_synthesis": TaskActual("memo_synthesis", calls=1.0,
                                           avg_prompt_tokens=1000.0, avg_completion_tokens=500.0)}
    folded = fold_actuals(profile, actual)
    t = folded.tasks["memo_synthesis"]
    # new = 0.3*actual + 0.7*seed
    assert t.avg_prompt_tokens == 0.3 * 1000.0 + 0.7 * 4000.0   # 3100.0 — moved toward 1000
    assert t.avg_completion_tokens == 0.3 * 500.0 + 0.7 * 2000.0
    assert t.avg_calls_per_run == 0.3 * 1.0 + 0.7 * 4.0
    assert t.samples == 1
    assert t.avg_prompt_tokens < profile.tasks["memo_synthesis"].avg_prompt_tokens  # converging


def test_fold_leaves_untouched_tasks_unchanged():
    profile = UsageProfile(tasks={
        "memo_synthesis": TaskUsage("memo_synthesis", 4.0, 4000.0, 2000.0, samples=0),
        "memo_audit": TaskUsage("memo_audit", 2.0, 1000.0, 300.0, samples=0),
    }, alpha=0.3)
    folded = fold_actuals(profile, {
        "memo_synthesis": TaskActual("memo_synthesis", 1.0, 1000.0, 500.0)})
    assert folded.tasks["memo_audit"] == profile.tasks["memo_audit"]  # disjoint task untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_profile.py -q`
Expected: FAIL — `ImportError: cannot import name 'fold_actuals'`.

- [ ] **Step 3: Write minimal implementation** — append to `src/irc/spend/profile.py`:

```python
from collections.abc import Mapping
from irc.spend.types import TaskActual  # add to existing imports


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_profile.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/profile.py tests/spend/test_profile.py
git commit -m "feat(spend): EWMA fold_actuals — convergence core (spec §5.4)"
```

---

### Task 4: `effective_profile` (learned-over-seed) in `profile.py`

**Files:**
- Modify: `src/irc/spend/profile.py`
- Test: `tests/spend/test_profile.py`

- [ ] **Step 1: Write the failing test** — append to `tests/spend/test_profile.py`:

```python
from irc.spend.profile import effective_profile, seed_profile


def test_effective_profile_uses_learned_where_samples_positive_else_seed():
    seed = UsageProfile(tasks={
        "memo_synthesis": TaskUsage("memo_synthesis", 4.0, 4000.0, 2000.0, samples=0),
        "memo_audit": TaskUsage("memo_audit", 2.0, 1000.0, 300.0, samples=0),
    }, alpha=0.3)
    learned_raw = {  # what usage_profile.json deserialises to
        "memo_synthesis": {"avg_calls_per_run": 1.0, "avg_prompt_tokens": 1100.0,
                           "avg_completion_tokens": 520.0, "samples": 3},
        "memo_audit": {"avg_calls_per_run": 0.0, "avg_prompt_tokens": 0.0,
                       "avg_completion_tokens": 0.0, "samples": 0},  # zeroed → ignore
    }
    blended = effective_profile(seed, learned_raw)
    assert blended.tasks["memo_synthesis"].avg_prompt_tokens == 1100.0     # learned
    assert blended.tasks["memo_synthesis"].samples == 3
    assert blended.tasks["memo_audit"] == seed.tasks["memo_audit"]          # seed fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_profile.py::test_effective_profile_uses_learned_where_samples_positive_else_seed -q`
Expected: FAIL — `ImportError: cannot import name 'effective_profile'`.

- [ ] **Step 3: Write minimal implementation** — append to `src/irc/spend/profile.py`:

```python
def effective_profile(
    seed: UsageProfile, learned_raw: Mapping[str, Mapping[str, float]],
) -> UsageProfile:
    """Pure: overlay learned entries (samples>0) onto the seed profile; seed
    fallback where a task is absent or has samples==0 (§5.3/§5.4)."""
    tasks = dict(seed.tasks)
    for task, row in learned_raw.items():
        if task not in tasks or int(row.get("samples", 0)) <= 0:
            continue
        tasks[task] = TaskUsage(
            task=task,
            avg_calls_per_run=float(row["avg_calls_per_run"]),
            avg_prompt_tokens=float(row["avg_prompt_tokens"]),
            avg_completion_tokens=float(row["avg_completion_tokens"]),
            samples=int(row["samples"]),
        )
    return UsageProfile(tasks=tasks, alpha=seed.alpha)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_profile.py -q`
Expected: PASS (all profile tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/profile.py tests/spend/test_profile.py
git commit -m "feat(spend): effective_profile — learned-over-seed profile (samples fallback)"
```

---

### Task 5: ledger decrement writer (`apply_usage`, pure)

**Files:**
- Modify: `src/irc/spend/ledger.py`
- Test: `tests/spend/test_ledger.py`

Mirror of the existing read path: write the `consumed_since`/`consumed_this_period` the reader already consumes.

- [ ] **Step 1: Write the failing test** — append to `tests/spend/test_ledger.py`:

```python
from datetime import date
from irc.spend.ledger import apply_usage


def test_wallet_accumulates_consumed_since_and_sets_since_when_absent():
    out = apply_usage({}, "tavily", units=4, kind="wallet", today=date(2026, 6, 6))
    assert out["tavily"]["consumed_since"] == 4.0
    assert out["tavily"]["since"] == "2026-06-06"
    out2 = apply_usage(out, "tavily", units=3, kind="wallet", today=date(2026, 6, 7))
    assert out2["tavily"]["consumed_since"] == 7.0          # accumulates
    assert out2["tavily"]["since"] == "2026-06-06"          # anchor date preserved


def test_quota_accumulates_consumed_this_period_and_stamps_period_start():
    out = apply_usage({}, "brave", units=10, kind="quota", today=date(2026, 6, 6))
    assert out["brave"]["consumed_this_period"] == 10.0
    assert out["brave"]["period_start"] == "2026-06-06"


def test_apply_usage_does_not_mutate_input():
    src = {"tavily": {"consumed_since": 1.0, "since": "2026-06-01"}}
    apply_usage(src, "tavily", units=2, kind="wallet", today=date(2026, 6, 6))
    assert src["tavily"]["consumed_since"] == 1.0           # original untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_ledger.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_usage'`.

- [ ] **Step 3: Write minimal implementation** — append to `src/irc/spend/ledger.py`:

```python
def apply_usage(
    consumption: dict[str, Any], provider: str, *, units: float, kind: str, today: date,
) -> dict[str, Any]:
    """Pure: add `units` to a provider's machine-counted consumption, returning a
    NEW dict (input untouched). kind='wallet' → consumed_since (+ since stamp on
    first write); kind='quota' → consumed_this_period (+ period_start stamp)."""
    out = {p: dict(row) for p, row in consumption.items()}
    row = dict(out.get(provider, {}))
    if kind == "quota":
        row["consumed_this_period"] = float(row.get("consumed_this_period", 0.0)) + float(units)
        row.setdefault("period_start", today.isoformat())
    else:
        row["consumed_since"] = float(row.get("consumed_since", 0.0)) + float(units)
        row.setdefault("since", today.isoformat())
    out[provider] = row
    return out
```

(`Any`, `date` are already imported in `ledger.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_ledger.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/ledger.py tests/spend/test_ledger.py
git commit -m "feat(spend): apply_usage — pure ledger decrement writer"
```

---

### Task 6: config I/O — usage_profile.json + consumption.json writers

**Files:**
- Modify: `src/irc/spend/config.py`
- Test: `tests/spend/test_config.py`

- [ ] **Step 1: Write the failing test** — append to `tests/spend/test_config.py`:

```python
import json
from irc.spend.config import (load_usage_profile_raw, write_usage_profile,
                              write_consumption, load_consumption)
from irc.spend.types import UsageProfile, TaskUsage


def test_usage_profile_roundtrips_atomically(tmp_path):
    assert load_usage_profile_raw(tmp_path) == {}        # absent → empty
    profile = UsageProfile(tasks={
        "memo_synthesis": TaskUsage("memo_synthesis", 1.0, 1100.0, 520.0, samples=3)}, alpha=0.3)
    write_usage_profile(tmp_path, profile)
    raw = load_usage_profile_raw(tmp_path)
    assert raw["memo_synthesis"]["samples"] == 3
    assert raw["memo_synthesis"]["avg_prompt_tokens"] == 1100.0
    # file lives at the documented path
    assert (tmp_path / "data/spend/usage_profile.json").exists()


def test_write_consumption_roundtrips(tmp_path):
    write_consumption(tmp_path, {"tavily": {"consumed_since": 4.0, "since": "2026-06-06"}})
    assert load_consumption(tmp_path)["tavily"]["consumed_since"] == 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_usage_profile_raw'`.

- [ ] **Step 3: Write minimal implementation** — append to `src/irc/spend/config.py` (and add `from irc.io_utils import atomic_write_text` + `from irc.spend.types import UsageProfile` at top):

```python
USAGE_PROFILE_FILE = "data/spend/usage_profile.json"


def load_usage_profile_raw(repo_root: Path, *, filename: str = USAGE_PROFILE_FILE) -> dict[str, Any]:
    path = Path(repo_root) / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_usage_profile(repo_root: Path, profile: UsageProfile,
                        *, filename: str = USAGE_PROFILE_FILE) -> None:
    rows = {
        t.task: {"avg_calls_per_run": t.avg_calls_per_run,
                 "avg_prompt_tokens": t.avg_prompt_tokens,
                 "avg_completion_tokens": t.avg_completion_tokens,
                 "samples": t.samples}
        for t in profile.tasks.values()
    }
    atomic_write_text(Path(repo_root) / filename, json.dumps(rows, indent=2, sort_keys=True))


def write_consumption(repo_root: Path, consumption: dict[str, Any],
                      *, filename: str = CONSUMPTION_FILE) -> None:
    atomic_write_text(Path(repo_root) / filename,
                      json.dumps(consumption, indent=2, sort_keys=True))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/config.py tests/spend/test_config.py
git commit -m "feat(spend): atomic writers for usage_profile.json + consumption.json"
```

---

### Task 7: estimate/actuals serialization (`estimate_io.py`, pure)

**Files:**
- Create: `src/irc/spend/estimate_io.py`
- Test: `tests/spend/test_estimate_io.py`

- [ ] **Step 1: Write the failing test** — create `tests/spend/test_estimate_io.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_estimate_io.py -q`
Expected: FAIL — `ModuleNotFoundError: irc.spend.estimate_io`.

- [ ] **Step 3: Write minimal implementation** — create `src/irc/spend/estimate_io.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_estimate_io.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/estimate_io.py tests/spend/test_estimate_io.py
git commit -m "feat(spend): pure estimate/actuals serialization + run-level merge"
```

---

### Task 8: `record_run.py` — the command-edge orchestrator (I/O)

**Files:**
- Create: `src/irc/spend/record_run.py`
- Test: `tests/spend/test_record_run.py`

Ties the pure pieces together at the edge: merge actuals file → fold profile → decrement ledger.

- [ ] **Step 1: Write the failing test** — create `tests/spend/test_record_run.py`:

```python
import json
from datetime import date
from pathlib import Path
import yaml
from irc.llm.cost_tracker import CostEntry
from irc.spend.record_run import record_command_run


def _seed_configs(repo: Path):
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "config/spend_pricing.yaml").write_text(yaml.safe_dump({
        "margin": 1.2,
        "llm": {"deepseek": {"currency": "CNY",
                             "models": {"deepseek-chat": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}}},
        "search": {"tavily": {"currency": "credits", "per_query": 2.0}},
        "seeds": {"memo_synthesis": {"calls": 4, "prompt_tokens": 4000, "completion_tokens": 2000}},
        "search_seeds": {"tavily": {"units": 10}},
    }), encoding="utf-8")
    (repo / "config/spend_balances.yaml").write_text(yaml.safe_dump({
        "bocha": {"balance": 2870, "as_of": "2026-06-01"},          # wallet
        "brave": {"quota": 2000, "reset": "monthly", "reset_day": 1},  # quota
    }), encoding="utf-8")


def test_record_run_writes_actuals_folds_profile_and_decrements_ledger(tmp_path):
    _seed_configs(tmp_path)   # also writes spend_balances.yaml: bocha=wallet, brave=quota
    out_dir = tmp_path / "outputs/2026-06-06"
    history = [CostEntry("memo_synthesis", "deepseek", "deepseek-chat", 1000, 500, 10,
                         "2026-06-06T01:00:00+08:00")]
    record_command_run(
        repo_root=tmp_path, out_dir=out_dir,
        history=history, search_units={"bocha": 4, "brave": 6}, today=date(2026, 6, 6),
    )
    # 1. actuals artifact
    actuals = json.loads((out_dir / "spend_actuals.json").read_text())
    assert actuals["tasks"]["memo_synthesis"]["avg_prompt_tokens"] == 1000.0
    assert actuals["search_units"] == {"bocha": 4, "brave": 6}
    # 2. profile folded (samples 0→1, moved off seed toward actual)
    prof = json.loads((tmp_path / "data/spend/usage_profile.json").read_text())
    assert prof["memo_synthesis"]["samples"] == 1
    assert prof["memo_synthesis"]["avg_prompt_tokens"] == 0.3 * 1000.0 + 0.7 * 4000.0
    # 3. ledger decremented — KIND DERIVED FROM spend_balances.yaml, not passed in (Q2)
    cons = json.loads((tmp_path / "data/spend/consumption.json").read_text())
    assert cons["bocha"]["consumed_since"] == 4.0          # wallet → consumed_since
    assert cons["brave"]["consumed_this_period"] == 6.0    # quota  → consumed_this_period


def test_record_run_accumulates_units_across_commands(tmp_path):
    _seed_configs(tmp_path)
    out_dir = tmp_path / "outputs/2026-06-06"
    for _ in range(2):
        record_command_run(repo_root=tmp_path, out_dir=out_dir, history=[],
                           search_units={"bocha": 5}, today=date(2026, 6, 6))
    cons = json.loads((tmp_path / "data/spend/consumption.json").read_text())
    assert cons["bocha"]["consumed_since"] == 10.0       # 5 + 5 across two commands


def test_record_run_skips_providers_with_no_balance_entry(tmp_path):
    _seed_configs(tmp_path)
    record_command_run(repo_root=tmp_path, out_dir=tmp_path / "outputs/2026-06-06",
                       history=[], search_units={"unknown_provider": 9}, today=date(2026, 6, 6))
    cpath = tmp_path / "data/spend/consumption.json"
    cons = json.loads(cpath.read_text()) if cpath.exists() else {}
    assert "unknown_provider" not in cons                # no entry → no orphan row


def test_record_run_no_paid_calls_writes_nothing(tmp_path):
    # Q4 guard: a command that made no paid calls (e.g. `decision`) records nothing.
    _seed_configs(tmp_path)
    out_dir = tmp_path / "outputs/2026-06-06"
    record_command_run(repo_root=tmp_path, out_dir=out_dir, history=[],
                       search_units={}, today=date(2026, 6, 6))
    assert not (out_dir / "spend_actuals.json").exists()
    assert not (tmp_path / "data/spend/usage_profile.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_record_run.py -q`
Expected: FAIL — `ModuleNotFoundError: irc.spend.record_run`.

- [ ] **Step 3: Write minimal implementation** — create `src/irc/spend/record_run.py`:

```python
from __future__ import annotations
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from irc.io_utils import atomic_write_text
from irc.llm.cost_tracker import CostEntry
from irc.spend.config import (load_balances, load_consumption, load_pricing,
                              load_usage_profile_raw, write_consumption, write_usage_profile)
from irc.spend.estimate_io import merge_actuals_dict
from irc.spend.ledger import apply_usage
from irc.spend.profile import effective_profile, fold_actuals, seed_profile
from irc.spend.recorder import actuals_from_costs


def record_command_run(
    *, repo_root: Path, history: Sequence[CostEntry], search_units: Mapping[str, int],
    today: date, out_dir: Path | None = None,
) -> None:
    """Edge: one gated command's actuals → merge spend_actuals.json, EWMA-fold
    usage_profile.json, decrement consumption.json. Wallet-vs-quota is DERIVED from
    spend_balances.yaml (the same `entry.quota is not None` predicate the reader uses),
    so writer/reader can never drift. Hands-off; each call accumulates. Safe to call on
    both success and failure paths — `history` holds only completed, billed calls (Q4).
    `out_dir` defaults to `repo_root/outputs/<today>` (override only in tests)."""
    if not history and not search_units:
        return                              # no paid calls → nothing to record (spec §12.2)
    root = Path(repo_root)
    out_dir = out_dir or root / "outputs" / today.isoformat()
    actuals = actuals_from_costs(history, search_units=search_units)

    actuals_path = Path(out_dir) / "spend_actuals.json"
    existing = json.loads(actuals_path.read_text()) if actuals_path.exists() else {}
    atomic_write_text(actuals_path,
                      json.dumps(merge_actuals_dict(existing, actuals), indent=2, sort_keys=True))

    pricing = load_pricing(root)
    eff = effective_profile(seed_profile(pricing), load_usage_profile_raw(root))
    write_usage_profile(root, fold_actuals(eff, actuals.tasks))

    balances = load_balances(root)
    consumption = load_consumption(root)
    touched = False
    for provider, units in actuals.search_units.items():
        entry = balances.entries.get(provider)
        if entry is None:
            continue                       # no anchor to deplete → skip (no orphan row)
        kind = "quota" if entry.quota is not None else "wallet"
        consumption = apply_usage(consumption, provider, units=units, kind=kind, today=today)
        touched = True
    if touched:
        write_consumption(root, consumption)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_record_run.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/record_run.py tests/spend/test_record_run.py
git commit -m "feat(spend): record_command_run edge — actuals + EWMA fold + ledger decrement"
```

---

### Task 9: `irc run`-only `spend_estimate.json` + estimates off the effective profile

**Files:**
- Modify: `src/irc/spend/preflight.py`, `src/irc/commands/spend_cmd.py`, `src/irc/commands/run_cmd.py`
- Test: `tests/spend/test_preflight.py`

Design (Q6 + follow-ups): **WHERE** to write = `out_dir`, defaulting to `repo_root/outputs/<today>` (override in tests only). **WHETHER** to write the estimate = a separate `write_estimate` flag, default `False`. Only `run_cmd._gate` passes `write_estimate=True`, so the estimate is **`irc run`-only**; the 6 `preflight_gate(repo_root, "<cmd>")` call sites stay byte-identical (`test_gate_wiring` green) → `write_estimate=False` → they never clobber it. On `--resume`/`--from`/`--only`, `stages` is the *remaining* set, so the written estimate is correctly scoped to what's about to run.

- [ ] **Step 1: Write the failing test** — append to `tests/spend/test_preflight.py` (reuse the module's existing repo-builder helper — Phase 1 tests already construct a repo with `config/llm.yaml` + spend configs; call it `_seed_repo` below):

```python
import json
from datetime import date


def test_run_preflight_writes_estimate_only_when_write_estimate(tmp_path):
    _seed_repo(tmp_path)                       # pricing + llm.yaml + balances (existing helper)
    today = date(2026, 6, 6)
    run_preflight(tmp_path, "memo", api_keys={}, today=today)            # default: no opt-in
    assert not (tmp_path / "outputs/2026-06-06/spend_estimate.json").exists()
    run_preflight(tmp_path, "run", api_keys={}, today=today, write_estimate=True)  # opt-in
    art = json.loads((tmp_path / "outputs/2026-06-06/spend_estimate.json").read_text())
    assert "deepseek" in art and "currency" in art["deepseek"]   # per-provider, currency kept
```

This doubles as the **no-clobber contract**: with `write_estimate` defaulting `False`, the per-stage gates inside `irc run` (which forward the default) write nothing.

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_preflight.py -k write_estimate -q`
Expected: FAIL — `run_preflight() got an unexpected keyword argument 'write_estimate'`.

- [ ] **Step 3: Implement in `src/irc/spend/preflight.py`:**
  1. Signature: add `out_dir: Path | None = None, write_estimate: bool = False`.
  2. Replace `profile = seed_profile(pricing)` with the effective profile:
     ```python
     from irc.spend.profile import effective_profile, seed_profile
     from irc.spend.config import load_usage_profile_raw
     profile = effective_profile(seed_profile(pricing), load_usage_profile_raw(root))
     ```
  3. After `estimates = estimate(...)`, persist iff opted in (default `out_dir` derived here):
     ```python
     if write_estimate:
         from irc.spend.estimate_io import estimate_to_dict
         from irc.io_utils import atomic_write_text
         dest = out_dir or root / "outputs" / today.isoformat()
         atomic_write_text(Path(dest) / "spend_estimate.json",
                           json.dumps(estimate_to_dict(estimates), indent=2, sort_keys=True))
     ```

- [ ] **Step 4: Thread the flag through the two callers (the only writer is `run`):**
  - `spend_cmd.preflight_gate` — add pass-through params, forward them; the 6 locked call sites stay `preflight_gate(repo_root, "<cmd>")` so they inherit `write_estimate=False`:
    ```python
    def preflight_gate(repo_root, command, *, stages=None, today=None,
                       out_dir=None, write_estimate=False) -> int:
        if os.environ.get("IRC_SKIP_SPEND_GATE", "").strip().lower() in _TRUE:
            return 0
        return run_preflight(repo_root, command, stages=stages, api_keys=collect_api_keys(),
                             today=today or _china_today(),
                             out_dir=out_dir, write_estimate=write_estimate)
    ```
  - `run_cmd._gate` — thread `out_dir` (already computed for `_run_stage_loop`) and opt in:
    ```python
    def _gate(repo_root: str, stages: list[str], out_dir: Path) -> int:
        from irc.commands.spend_cmd import preflight_gate
        return preflight_gate(repo_root, "run", stages=tuple(stages),
                              out_dir=out_dir, write_estimate=True)
    ```
    and its caller becomes `gate_rc = _gate(repo_root, stages, out_dir)`.

- [ ] **Step 5: Run tests to verify pass (gate-wiring must stay green)**

Run: `unset VIRTUAL_ENV; uv run pytest tests/spend/test_preflight.py tests/commands/test_gate_wiring.py -q`
Expected: PASS — `test_gate_wiring` still green because the 6 `preflight_gate(repo_root, "<cmd>")` call sites are unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/irc/spend/preflight.py src/irc/commands/spend_cmd.py src/irc/commands/run_cmd.py tests/spend/test_preflight.py
git commit -m "feat(spend): irc run-only spend_estimate.json via write_estimate flag; effective-profile estimates"
```

---

### Task 10: wire the recorder into `memo_cmd` (first proven end-to-end round-trip)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Test: `tests/commands/test_memo_recorder.py`

memo is the cleanest first wiring: `synthesize_memo(...)`/audit return `ChatResponse` to the command, and `route.task` is `memo_synthesis`/`memo_audit`.

- [ ] **Step 1: Read** `src/irc/commands/memo_cmd.py` to find where it (a) resolves routes, (b) calls `synthesize_memo`/auditor and receives each `ChatResponse`, and (c) computes `out_dir`/`today`. Identify the function that owns the full memo command (the one wired into `STAGE_TASKS["memo"]`).

- [ ] **Step 2: Write the failing integration test** — create `tests/commands/test_memo_recorder.py`:

```python
"""memo command, with LLM calls faked, records actuals + folds the profile."""
import json
from datetime import date
from pathlib import Path
import yaml, pytest
from irc.llm._types import ChatResponse


@pytest.fixture
def memo_repo(tmp_path):
    # minimal config so the recorder's load_pricing/seed_profile works
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config/spend_pricing.yaml").write_text(yaml.safe_dump({
        "margin": 1.2,
        "llm": {"deepseek": {"currency": "CNY", "models": {
            "deepseek-chat": {"input_per_mtok": 1.0, "output_per_mtok": 2.0},
            "deepseek-reasoner": {"input_per_mtok": 3.0, "output_per_mtok": 6.0}}}},
        "seeds": {"memo_synthesis": {"calls": 4, "prompt_tokens": 4000, "completion_tokens": 2000},
                  "memo_audit": {"calls": 2, "prompt_tokens": 1000, "completion_tokens": 300}},
    }), encoding="utf-8")
    return tmp_path


def test_memo_run_records_actuals_and_converges(memo_repo, monkeypatch):
    # Fake the two LLM legs so no network; tokens are the "actuals" we expect recorded.
    monkeypatch.setattr("irc.memo.synthesizer.call_chat",
                        lambda **k: ChatResponse(text="memo", prompt_tokens=1000, completion_tokens=500))
    monkeypatch.setattr("irc.memo.auditor.call_chat",
                        lambda **k: ChatResponse(text="ok", prompt_tokens=800, completion_tokens=120))
    # … drive the memo command against memo_repo with a fixed today/out_dir …
    # (exact entrypoint discovered in Step 1; e.g. run_memo(str(memo_repo), today="2026-06-06"))

    prof = json.loads((memo_repo / "data/spend/usage_profile.json").read_text())
    assert prof["memo_synthesis"]["samples"] == 1
    assert prof["memo_synthesis"]["avg_prompt_tokens"] == 0.3 * 1000.0 + 0.7 * 4000.0
    actuals = json.loads(next((memo_repo / "outputs").rglob("spend_actuals.json")).read_text())
    assert actuals["tasks"]["memo_audit"]["avg_completion_tokens"] == 120.0
```

(Adapt the driver line to the real entrypoint found in Step 1. Keep the three assertions — they are the §15.2 round-trip contract.)

- [ ] **Step 3: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/commands/test_memo_recorder.py -q`
Expected: FAIL — no `spend_actuals.json` / `usage_profile.json` produced.

- [ ] **Step 4: Implement the edge hook in `memo_cmd.py`:**
  - Build a local `history: list[CostEntry] = []` at the start of the command function (local — no module global).
  - At each LLM leg, **immediately** after `call_chat` returns the `ChatResponse resp` (before any downstream processing, so a later failure can't lose an already-billed call — Q4), append via the pure helper:
    ```python
    from irc.llm.cost_tracker import CostEntry, append_cost
    from datetime import datetime, timezone, timedelta
    _ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    history = append_cost(history, CostEntry(
        task=route.task, provider=route.provider, model=route.model,
        prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms, ts=_ts))
    ```
  - Wrap the command body so recording fires on **both** success and failure (Q4) — `record_command_run` itself early-returns when nothing was spent, so the `finally` is safe even on an early error:
    ```python
    from irc.spend.record_run import record_command_run
    history: list[CostEntry] = []
    try:
        ...  # existing memo body; each leg appends to `history` immediately (above)
        return rc
    finally:
        try:
            record_command_run(repo_root=Path(repo_root), history=history,
                               search_units={}, today=_today_date)  # out_dir defaults
        except Exception:  # recorder must never alter the command's real rc/exception
            logging.getLogger(__name__).warning("spend recorder failed", exc_info=True)
    ```
  - The inner `try/except Exception` logs a `WARNING` (observable — **not** a silent failure) and never swallows the command's real result; the outer `finally` guarantees billed calls are recorded even when memo raises.

- [ ] **Step 5: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/commands/test_memo_recorder.py tests/spend -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_recorder.py
git commit -m "feat(spend): wire recorder into memo_cmd — first end-to-end convergence"
```

---

### Task 11: README "Spend / balance gate" section + docs grep test (§13)

**Files:**
- Modify: `README.md`
- Test: `tests/docs/test_readme_spend.py`

- [ ] **Step 1: Write the failing test** — create `tests/docs/test_readme_spend.py`:

```python
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_documents_spend_gate_and_artifacts():
    text = README.read_text(encoding="utf-8")
    assert "## Spend / balance gate" in text or "Spend / balance gate" in text
    for path in ("outputs/<date>/spend_estimate.json",
                 "outputs/<date>/spend_actuals.json",
                 "data/spend/usage_profile.json"):
        assert path in text, f"README missing artifact path: {path}"
    assert "IRC_SPEND_MARGIN" in text
    assert "exit code 5" in text or "exit 5" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `unset VIRTUAL_ENV; uv run pytest tests/docs/test_readme_spend.py -q`
Expected: FAIL (paths/heading absent).

- [ ] **Step 3: Expand the README** "Spend / balance gate" section (Phase 1 already added a stub — extend it) to document: the artifact table (§12.1 — estimate at start, actuals at end, learned profile), auto-convergence every run (§12.2), the trigger-command list (§12.3: run/opportunity/memo/decision/eval-funds/narrative --analyze/ask; `spend status` read-only), topping up a no-API provider (edit `config/spend_balances.yaml`), and the `margin`/`IRC_SPEND_MARGIN` knob + **exit code 5** = insufficient balance. Include the three literal artifact paths the test greps. Also state the **convergence scope** (Q5): only LLM estimates converge; search estimates are **seed-based** (retune the `config/spend_pricing.yaml` `search_seeds` by eye against `spend_actuals.json` if they drift) while the search *balance* stays exact via the ledger.

- [ ] **Step 4: Run test to verify it passes**

Run: `unset VIRTUAL_ENV; uv run pytest tests/docs/test_readme_spend.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/docs/test_readme_spend.py
git commit -m "docs(spend): Phase 2 README — estimated-vs-actual artifacts + auto-convergence"
```

---

### Task 12: wire every spends-money runner (Q7 set; usage rides home as data)

The wiring set is **"makes paid calls,"** not "is gated" (Q7): in-run stages `research`/`discover`/`score`/`opportunity`/`memo` + standalone `ask`/`eval-funds`/`narrative --analyze`. **Not** `decision`/`ingest`/`gold`/`allocate`/`plan` (zero paid calls; the empty-history guard no-ops them anyway). `irc run` itself needs **no** change — it invokes these as sub-runners, each recording its slice into the shared dated `spend_actuals.json` (Q3 merge).

Two seams, one principle — **usage returns up as data; the command edge calls `record_command_run`** (Q7). A mutable sink is never threaded *down* (that would mutate an argument); the pure math cores never see a `CostEntry`.

Each subtask is its own TDD cycle + commit, mirroring Task 10's 3-assertion shape (profile `samples 0→1`, `spend_actuals.json` written, the right tokens recorded). Order them low-churn → high-churn:

- [ ] **12a — `ask` (Shape A, no wrapper change).** `respond_to_query` already returns `ChatResponse`; in `run_ask`, append a `CostEntry` from it, then `record_command_run(..., search_units={})` in a `finally` (Q4). The `interactive_query` task `samples 0→1`.

- [ ] **12b — `score` (Shape B).** Change `scoring/factors/macro_fit.py::score_macro_fit(ctx, route) -> FactorScore` to also return its usage: `-> tuple[FactorScore, ChatResponse]`. In `scoring/pipeline.py` (call sites `:84,:113`), collect each returned `ChatResponse` into a **local** `list` and return it up alongside the scores; `run_score` appends `CostEntry`s (task `scoring_rationale`/`macro_fit`) and records. Update the existing `score_macro_fit` tests for the new return tuple.

- [ ] **12c — `discover` (Shape B).** `discovery/reason_writer.py::write_reason` returns its `ChatResponse` alongside the reason; `discovery/pipeline.py` (`:152,:185`) collects; `run_discover` appends `CostEntry`s (`factor_screening`/`watchlist_reason`) and records.

- [ ] **12d — `research` (Shape B) — proves the §15.2 ledger box.** `research/synthesize.py::synthesize_report` returns its `ChatResponse`; `research/theme_research.py` (`:125`) collects LLM usage **and** counts **search units** from `multi_provider_search`/`extract_top_pages` (1 per `provider.search()`, 1 per `extractor.extract()`), keyed by `provider.name`. `run_research` calls `record_command_run(history=…, search_units={provider: n})` → the ledger decrement for Tavily/Bocha/Jina/Brave lands here. After a research run, `irc spend status` shows the wallet reduced / quota advanced.

- [ ] **12e — `opportunity` (Shape B).** `debate.py::run_defend`/`run_falsify` return their `ChatResponse`; `run_debates` collects; `opportunity_cmd.py` (`:1423`) appends `CostEntry`s (`thesis_falsify`/`thesis_defend`) and records.

- [ ] **12f — standalone `eval-funds` + `narrative --analyze`.** These reuse the score/opportunity wrappers already made return-usage in 12b/12e, so each edge (`run_eval_funds`, `run_narrative`) just collects + `record_command_run`. Their tasks (`scoring_rationale`, `thesis_*`) converge.

> **Time-box note:** Tasks 1–11 already satisfy every §15.2 box (recorder round-trip, numerical convergence via Task 3 + memo round-trip, artifacts, ledger decrement *mechanism* via Task 8's unit test, README, no-regression). Task 12 makes the convergence **live for all paid tasks** and gives the ledger box its **end-to-end** proof (12d). 12a is trivial; 12b–12f carry the return-type churn — split across commits, each keeping the suite green.

---

## Definition of Done (§15.2 — verify and paste evidence)

```bash
unset VIRTUAL_ENV
uv run pytest tests/spend -k "recorder or convergence or ledger" -q     # box 1
uv run pytest tests/spend tests/commands/test_memo_recorder.py tests/docs/test_readme_spend.py -q
uv run ruff check src/irc/spend src/irc/commands/memo_cmd.py tests/spend  # lint clean
uv run pytest -q   # no NEW failures vs the ~8 known-baseline (see project_test_suite_baseline memory)
```

- [ ] Recorder round-trip green (Tasks 2,5,8).
- [ ] Convergence proven numerically — `samples 0→1`, estimate moves toward actual (Task 3 test + Task 10 round-trip; capture before/after `avg_prompt_tokens`: seed 4000 → folded 3100 for `memo_synthesis`).
- [ ] Artifacts: `spend_estimate.json` (Task 9) + `spend_actuals.json` (Task 8/10) written; `usage_profile.json` + `consumption.json` updated.
- [ ] Ledger auto-decrement proven — *mechanism* by Task 8's unit test (`apply_usage` + `write_consumption` round-trip), *end-to-end* by Task 12d (a `research` run decrements Tavily/Bocha/Jina/Brave) → `irc spend status` shows reduced wallet / advanced quota.
- [ ] README shipped + docs grep green (Task 11).
- [ ] No regression + lint clean.

## §15.3 final acceptance (after wiring)

Two consecutive gated runs with injected actuals: run 1's estimate = seed; run 2's estimate reflects run 1's recorded actuals — show the two `spend_estimate.json` `amount`s and the delta. (Deterministic per §16.1 item 5 — no real spend.)
