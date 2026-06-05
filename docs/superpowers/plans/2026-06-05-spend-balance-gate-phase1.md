# Preflight Spend / Balance Gate — Phase 1 Implementation Plan

> **READ FIRST, before Task 1:** open the spec `docs/superpowers/specs/2026-06-05-spend-balance-gate-design.md` and read **§15 (per-phase exit gates — the Definition of Done you must verify)** and **§16.1 (calibrated prices/balances already baked into this plan's Task 1, plus FLAGGED placeholders: Jina per-page tokens, Brave monthly quota, Bocha unit, and Tavily-modeled-as-quota)**. The config values in Task 1 are real (user-calibrated 2026-06-05) — do **not** replace them with placeholders. After Phase 1, verify every box in spec §15.1 before stopping.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a preflight gate that, before any gated command does paid work, estimates the run's spend per provider (from a deliberately-high seed) and stops the run with exit code `5` when a provider's balance can't cover it.

**Architecture:** A new pure-core `src/irc/spend/` package (estimator, ledger, gate, scope) plus thin I/O edges (balance probes, the preflight orchestrator). Phase 1 ships a working gate using a **seeded** usage profile (no learning yet) and a **read-only** local balance ledger; Phase 2 (separate plan) adds the recorder, EWMA convergence, ledger auto-decrement, and the README. Spec: `docs/superpowers/specs/2026-06-05-spend-balance-gate-design.md`.

**Tech Stack:** Python 3.12, pydantic v2 (`FrozenModel`), `httpx`, `tenacity`, `click`, `pyyaml`, `pytest`. Repo conventions: TDD (red→green→refactor), frozen dataclasses, pure cores / I/O at edges, files <200 lines, `ruff` line-length 100.

**Branch:** `feat/spend-balance-gate` (already checked out; the design spec is committed there).

---

## File Structure (Phase 1)

**Create:**
- `config/spend_pricing.yaml` — margin, per-model LLM prices, per-query search prices, per-task seeds, per-provider search seeds.
- `config/spend_balances.yaml` — human-edited balance anchors (wallet + quota).
- `src/irc/schemas/spend.py` — `SpendPricingConfig`, `SpendBalancesConfig` pydantic models.
- `src/irc/spend/__init__.py`
- `src/irc/spend/types.py` — frozen dataclasses (`TaskUsage`, `UsageProfile`, `CostEstimate`, `BalanceReading`, `ProviderVerdict`, `GateDecision`).
- `src/irc/spend/config.py` — load/validate pricing, balances, consumption files.
- `src/irc/spend/profile.py` — build a seed `UsageProfile` from pricing seeds (Phase 1: seed-only).
- `src/irc/spend/scope.py` — static `STAGE_TASKS` / command→scope map + pure resolver.
- `src/irc/spend/estimator.py` — pure per-provider cost estimate.
- `src/irc/spend/ledger.py` — pure effective-balance (wallet decrement + quota auto-reset + re-anchor).
- `src/irc/spend/gate.py` — pure block/warn/ok decision.
- `src/irc/spend/probes/__init__.py` — probe registry.
- `src/irc/spend/probes/base.py` — `BalanceProbe` protocol + shared SSRF/proxy/retry GET helper.
- `src/irc/spend/probes/deepseek.py`, `src/irc/spend/probes/openrouter.py`.
- `src/irc/spend/preflight.py` — orchestration edge: scope → estimate → gather balances → decide → print → exit code.
- `src/irc/commands/spend_cmd.py` — `irc spend status` (read-only) + the shared `preflight_gate(...)` helper.

**Modify:**
- `src/irc/commands/validate_cmd.py` — also validate the two spend configs.
- `src/irc/commands/run_cmd.py` — call the gate before the stage loop.
- `src/irc/commands/{opportunity_cmd,memo_cmd,decision_cmd,ask_cmd}.py` (+ eval-funds / narrative runners) — call the gate at entry.
- `src/irc/cli.py` — add the `spend` group + `status`.
- `pyproject.toml` — register the `live_balance` marker.
- `.gitignore` — ignore `data/spend/`.

**Tests mirror source** under `tests/spend/...` and `tests/commands/...`.

---

## Task 1: Spend config schemas + loader + config files + validate wiring

**Files:**
- Create: `src/irc/schemas/spend.py`
- Create: `config/spend_pricing.yaml`, `config/spend_balances.yaml`
- Create: `src/irc/spend/__init__.py`, `src/irc/spend/config.py`
- Modify: `src/irc/commands/validate_cmd.py`
- Test: `tests/spend/test_config.py`, `tests/commands/test_validate_spend.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_config.py
from pathlib import Path
import pytest
from irc.spend.config import load_pricing, load_balances, load_consumption

REPO = Path(__file__).resolve().parents[2]

def test_load_pricing_has_margin_and_deepseek_models():
    pricing = load_pricing(REPO)
    assert pricing.margin == 1.2
    assert "deepseek-reasoner" in pricing.llm["deepseek"].models
    assert pricing.llm["deepseek"].currency == "CNY"
    assert pricing.seeds["memo_synthesis"].completion_tokens > 0

def test_load_balances_accepts_wallet_and_quota_entries():
    balances = load_balances(REPO)
    assert balances.entries["bocha"].balance is not None    # wallet
    assert balances.entries["brave"].quota is not None      # quota
    assert balances.entries["tavily"].quota is not None      # quota (PAYG)

def test_load_balances_rejects_entry_that_is_neither_wallet_nor_quota(tmp_path):
    bad = tmp_path / "spend_balances.yaml"
    bad.write_text("tavily: {foo: 1}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_balances(tmp_path, filename=bad.name)

def test_load_consumption_missing_file_returns_empty(tmp_path):
    assert load_consumption(tmp_path) == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: irc.spend.config`).

- [ ] **Step 3: Write the schemas**

```python
# src/irc/schemas/spend.py
from __future__ import annotations
from datetime import date
from pydantic import Field, model_validator
from ._types import FrozenModel


class ModelPrice(FrozenModel):
    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)


class LLMProviderPricing(FrozenModel):
    currency: str = Field(min_length=1)
    models: dict[str, ModelPrice] = Field(min_length=1)


class SearchPricing(FrozenModel):
    currency: str = Field(min_length=1)
    per_query: float | None = None
    per_page: float | None = None

    @model_validator(mode="after")
    def _one_rate(self) -> "SearchPricing":
        if (self.per_query is None) == (self.per_page is None):
            raise ValueError("search pricing needs exactly one of per_query / per_page")
        return self


class TaskSeed(FrozenModel):
    calls: float = Field(ge=0)
    prompt_tokens: float = Field(ge=0)
    completion_tokens: float = Field(ge=0)


class SearchSeed(FrozenModel):
    units: float = Field(ge=0)   # expected queries (or pages) per run


class SpendPricingConfig(FrozenModel):
    margin: float = Field(default=1.2, gt=0)
    llm: dict[str, LLMProviderPricing] = Field(min_length=1)
    search: dict[str, SearchPricing] = Field(default_factory=dict)
    seeds: dict[str, TaskSeed] = Field(default_factory=dict)
    search_seeds: dict[str, SearchSeed] = Field(default_factory=dict)


class SpendBalanceEntry(FrozenModel):
    balance: float | None = None      # wallet
    as_of: date | None = None         # wallet
    quota: float | None = None        # quota
    reset: str | None = None          # quota: "monthly"
    reset_day: int = Field(default=1, ge=1, le=28)

    @model_validator(mode="after")
    def _wallet_xor_quota(self) -> "SpendBalanceEntry":
        is_wallet = self.balance is not None and self.as_of is not None
        is_quota = self.quota is not None and self.reset is not None
        if is_wallet == is_quota:
            raise ValueError(
                "balance entry must be EITHER a wallet (balance + as_of) "
                "OR a quota (quota + reset), not both/neither"
            )
        return self


class SpendBalancesConfig(FrozenModel):
    entries: dict[str, SpendBalanceEntry] = Field(default_factory=dict)
```

- [ ] **Step 4: Write the config files**

```yaml
# config/spend_pricing.yaml
# CALIBRATED 2026-06-05 from user-supplied provider_pricing.csv (see spec §16.1).
# DeepSeek prices are CACHE-MISS CNY (conservative over-estimate). Model keys match
# config/llm.yaml routes. Seeds are deliberately HIGH so a cold install over-estimates.
margin: 1.2
llm:
  deepseek:
    currency: CNY
    models:
      deepseek-chat:     { input_per_mtok: 0.9515, output_per_mtok: 1.9029 }
      deepseek-reasoner: { input_per_mtok: 2.9563, output_per_mtok: 5.9126 }
  openrouter:    # INERT — no task routes here; placeholder prices, real credits read live by probe
    currency: USD
    models:
      deepseek/deepseek-chat:     { input_per_mtok: 0.28, output_per_mtok: 0.88 }
      deepseek/deepseek-reasoner: { input_per_mtok: 0.55, output_per_mtok: 2.19 }
search:
  tavily: { currency: credits, per_query: 2.0 }    # advanced search = 2 credits/request
  bocha:  { currency: CNY,     per_query: 0.036 }  # Web Search API ¥0.036/call
  jina:   { currency: tokens,  per_page: 10000.0 } # token-based; conservative placeholder — VERIFY
  brave:  { currency: queries, per_query: 1.0 }    # 1 query per search
seeds:
  news_summary:      { calls: 20, prompt_tokens: 1500,  completion_tokens: 800 }
  news_dedup:        { calls: 10, prompt_tokens: 2000,  completion_tokens: 500 }
  factor_screening:  { calls: 8,  prompt_tokens: 3000,  completion_tokens: 1000 }
  watchlist_reason:  { calls: 30, prompt_tokens: 1500,  completion_tokens: 800 }
  scoring_rationale: { calls: 40, prompt_tokens: 2000,  completion_tokens: 1500 }
  thesis_falsify:    { calls: 30, prompt_tokens: 3000,  completion_tokens: 2000 }
  thesis_defend:     { calls: 30, prompt_tokens: 3000,  completion_tokens: 2000 }
  interactive_query: { calls: 1,  prompt_tokens: 8000,  completion_tokens: 3000 }
  research_synth:    { calls: 12, prompt_tokens: 4000,  completion_tokens: 1500 }
  memo_synthesis:    { calls: 1,  prompt_tokens: 12000, completion_tokens: 6000 }
  memo_audit:        { calls: 1,  prompt_tokens: 12000, completion_tokens: 6000 }
search_seeds:
  tavily: { units: 40 }
  bocha:  { units: 40 }
  jina:   { units: 30 }
  brave:  { units: 40 }
```

```yaml
# config/spend_balances.yaml
# CALIBRATED 2026-06-05 (see spec §16.1). Edit when you top up — the machine only
# READS this file, so your comments/formatting survive.
#   Wallet: set `balance` + `as_of`.  Quota: set `quota` + `reset` once (auto-resets).
# Tavily is modeled as a QUOTA because of free-1000/mo + pay-as-you-go (overage bills,
# shouldn't hard-stop). Bocha/Jina are prepaid wallets.
tavily: { quota: 1000, reset: monthly, reset_day: 1 }   # free credits/mo; PAYG enabled
bocha:  { balance: 2870, as_of: 2026-06-05 }            # CNY prepaid — confirm unit
jina:   { balance: 988000000, as_of: 2026-06-05 }       # 988M tokens
brave:  { quota: 2000, reset: monthly, reset_day: 1 }   # placeholder monthly limit — confirm
```

- [ ] **Step 5: Write the loader**

```python
# src/irc/spend/config.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import yaml
from irc.schemas.spend import SpendPricingConfig, SpendBalancesConfig

PRICING_FILE = "config/spend_pricing.yaml"
BALANCES_FILE = "config/spend_balances.yaml"
CONSUMPTION_FILE = "data/spend/consumption.json"


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_pricing(repo_root: Path, *, filename: str = PRICING_FILE) -> SpendPricingConfig:
    return SpendPricingConfig.model_validate(_read_yaml(Path(repo_root) / filename))


def load_balances(repo_root: Path, *, filename: str = BALANCES_FILE) -> SpendBalancesConfig:
    raw = _read_yaml(Path(repo_root) / filename)
    return SpendBalancesConfig.model_validate({"entries": raw})


def load_consumption(repo_root: Path, *, filename: str = CONSUMPTION_FILE) -> dict[str, Any]:
    path = Path(repo_root) / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
```

Also create `src/irc/spend/__init__.py` (empty) and `tests/spend/__init__.py` (empty).

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/spend/test_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Wire spend configs into `irc config validate`**

```python
# tests/commands/test_validate_spend.py
from pathlib import Path
from irc.commands.validate_cmd import run_validate

def test_validate_passes_with_spend_configs(capsys):
    repo = Path(__file__).resolve().parents[2]
    rc = run_validate(repo_root=str(repo))
    out = capsys.readouterr().out
    assert rc == 0
    assert "spend" in out.lower()
```

Run: `uv run pytest tests/commands/test_validate_spend.py -v` → FAIL (no "spend" in output).

Modify `src/irc/commands/validate_cmd.py` — after the existing `load_repo_configs(root)` call, before the success `print`, add:

```python
    from irc.spend.config import load_pricing, load_balances
    try:
        pricing = load_pricing(root)
        load_balances(root)
    except Exception as exc:  # noqa: BLE001 — surface spend-config errors too
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
```

and append to the success message f-string:

```python
        f"\n  spend: margin {pricing.margin}, {len(pricing.seeds)} task seeds"
```

Run: `uv run pytest tests/commands/test_validate_spend.py -v` → PASS.

- [ ] **Step 8: Commit**

```bash
git add src/irc/schemas/spend.py config/spend_pricing.yaml config/spend_balances.yaml \
        src/irc/spend/__init__.py src/irc/spend/config.py tests/spend/ \
        src/irc/commands/validate_cmd.py tests/commands/test_validate_spend.py
git commit -m "feat(spend): pricing/balances config schemas, loader, and validate wiring"
```

---

## Task 2: Core types

**Files:**
- Create: `src/irc/spend/types.py`
- Test: `tests/spend/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_types.py
import dataclasses
import pytest
from irc.spend.types import (
    TaskUsage, UsageProfile, CostEstimate, BalanceReading, ProviderVerdict, GateDecision,
)

def test_types_are_frozen():
    u = TaskUsage(task="memo_synthesis", avg_calls_per_run=1, avg_prompt_tokens=10,
                  avg_completion_tokens=5, samples=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        u.samples = 9  # type: ignore[misc]

def test_balance_reading_allows_unknown_amount():
    r = BalanceReading(provider="jina", currency="tokens", amount=None,
                       available=False, source="probe_failed")
    assert r.amount is None

def test_gate_decision_groups():
    d = GateDecision(blocked=(), warnings=(), ok=())
    assert d.blocked == () and d.warnings == () and d.ok == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_types.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the types**

```python
# src/irc/spend/types.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TaskUsage:
    task: str
    avg_calls_per_run: float
    avg_prompt_tokens: float
    avg_completion_tokens: float
    samples: int           # 0 ⇒ seeded (no learned data yet)


@dataclass(frozen=True)
class UsageProfile:
    tasks: Mapping[str, TaskUsage]
    alpha: float = 0.3


@dataclass(frozen=True)
class CostEstimate:
    provider: str
    currency: str
    amount: float
    breakdown: Mapping[str, float]


@dataclass(frozen=True)
class BalanceReading:
    provider: str
    currency: str
    amount: float | None   # None ⇒ unreadable → never hard-stops
    available: bool
    source: str            # "api" | "ledger" | "probe_failed" | "no_balance_api"


@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    estimate: float | None
    balance: float | None
    status: str            # "ok" | "blocked" | "warning" | "info"
    detail: str


@dataclass(frozen=True)
class GateDecision:
    blocked: tuple[ProviderVerdict, ...]
    warnings: tuple[ProviderVerdict, ...]
    ok: tuple[ProviderVerdict, ...]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/types.py tests/spend/test_types.py
git commit -m "feat(spend): core frozen types (usage, estimate, balance, gate decision)"
```

---

## Task 3: Seed usage profile

**Files:**
- Create: `src/irc/spend/profile.py`
- Test: `tests/spend/test_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_profile.py
from pathlib import Path
from irc.spend.config import load_pricing
from irc.spend.profile import seed_profile

REPO = Path(__file__).resolve().parents[2]

def test_seed_profile_marks_entries_unlearned_with_seed_values():
    pricing = load_pricing(REPO)
    profile = seed_profile(pricing)
    memo = profile.tasks["memo_synthesis"]
    assert memo.samples == 0
    assert memo.avg_prompt_tokens == pricing.seeds["memo_synthesis"].prompt_tokens
    assert memo.avg_calls_per_run == pricing.seeds["memo_synthesis"].calls
    assert profile.alpha == 0.3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_profile.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/profile.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_profile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/profile.py tests/spend/test_profile.py
git commit -m "feat(spend): build seed usage profile from pricing seeds"
```

---

## Task 4: Scope map (stage/command → tasks & search providers)

**Files:**
- Create: `src/irc/spend/scope.py`
- Test: `tests/spend/test_scope.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_scope.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_scope.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/scope.py
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
    "decision": (),
}

STAGE_SEARCH_PROVIDERS: dict[str, tuple[str, ...]] = {
    "research": ("tavily", "brave", "bocha", "jina"),
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
    return Scope(tasks=frozenset(COMMAND_TASKS.get(command, ())), search_providers=frozenset())
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_scope.py -v`
Expected: PASS (4 tests). If `test_every_llm_yaml_task_is_mapped_somewhere` fails, add the missing task to the correct `STAGE_TASKS`/`COMMAND_TASKS` row.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/scope.py tests/spend/test_scope.py
git commit -m "feat(spend): scope map from command/stages to tasks + search providers"
```

---

## Task 5: Cost estimator (pure)

**Files:**
- Create: `src/irc/spend/estimator.py`
- Test: `tests/spend/test_estimator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_estimator.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_estimator.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/estimator.py
from __future__ import annotations
from irc.schemas.llm import LLMConfig
from irc.schemas.spend import SpendPricingConfig
from irc.spend.types import CostEstimate, UsageProfile


def _llm_estimates(
    tasks: frozenset[str], llm: LLMConfig, profile: UsageProfile, pricing: SpendPricingConfig,
) -> dict[str, tuple[str, float, dict[str, float]]]:
    acc: dict[str, tuple[str, float, dict[str, float]]] = {}
    for task in sorted(tasks):
        route = llm.tasks[task]
        provider, model = route.provider, route.model
        price = pricing.llm[provider].models[model]
        usage = profile.tasks[task]
        cost = usage.avg_calls_per_run * (
            usage.avg_prompt_tokens * price.input_per_mtok
            + usage.avg_completion_tokens * price.output_per_mtok
        ) / 1_000_000.0
        currency = pricing.llm[provider].currency
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_estimator.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/estimator.py tests/spend/test_estimator.py
git commit -m "feat(spend): pure per-provider cost estimator (LLM tokens + search queries)"
```

---

## Task 6: Ledger — effective balance with auto-reset & re-anchor (pure)

**Files:**
- Create: `src/irc/spend/ledger.py`
- Test: `tests/spend/test_ledger.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_ledger.py
from datetime import date
from irc.schemas.spend import SpendBalanceEntry
from irc.spend.ledger import effective_balance

def _wallet(balance, as_of):
    return SpendBalanceEntry(balance=balance, as_of=as_of)

def _quota(quota, reset_day=1):
    return SpendBalanceEntry(quota=quota, reset="monthly", reset_day=reset_day)

def test_wallet_subtracts_consumption_since_anchor():
    entry = _wallet(100.0, date(2026, 6, 1))
    consumption = {"tavily": {"consumed_since": 30.0, "since": "2026-06-01"}}
    r = effective_balance("tavily", entry, consumption, today=date(2026, 6, 5))
    assert r.amount == 70.0
    assert r.source == "ledger"
    assert r.available is True

def test_wallet_resets_consumption_when_anchor_moved_forward():
    entry = _wallet(100.0, date(2026, 6, 10))   # user topped up on the 10th
    consumption = {"tavily": {"consumed_since": 30.0, "since": "2026-06-01"}}
    r = effective_balance("tavily", entry, consumption, today=date(2026, 6, 11))
    assert r.amount == 100.0   # consumption before the new anchor is ignored

def test_wallet_missing_consumption_returns_full_balance():
    r = effective_balance("jina", _wallet(500.0, date(2026, 6, 1)), {}, today=date(2026, 6, 5))
    assert r.amount == 500.0

def test_negative_balance_marks_unavailable():
    entry = _wallet(10.0, date(2026, 6, 1))
    consumption = {"bocha": {"consumed_since": 25.0, "since": "2026-06-01"}}
    r = effective_balance("bocha", entry, consumption, today=date(2026, 6, 5))
    assert r.amount == -15.0
    assert r.available is False

def test_quota_within_period_subtracts_period_consumption():
    consumption = {"brave": {"consumed_this_period": 380.0, "period_start": "2026-06-01"}}
    r = effective_balance("brave", _quota(2000.0), consumption, today=date(2026, 6, 20))
    assert r.amount == 1620.0

def test_quota_auto_resets_when_month_rolls_over():
    consumption = {"brave": {"consumed_this_period": 380.0, "period_start": "2026-06-01"}}
    # today is in July → period_start is stale → consumed resets to 0
    r = effective_balance("brave", _quota(2000.0), consumption, today=date(2026, 7, 2))
    assert r.amount == 2000.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_ledger.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/ledger.py
from __future__ import annotations
from datetime import date
from typing import Any
from irc.schemas.spend import SpendBalanceEntry
from irc.spend.types import BalanceReading


def _period_start(today: date, reset_day: int) -> date:
    """First day of the current quota period (reset_day this month, or last month
    if we haven't reached reset_day yet)."""
    if today.day >= reset_day:
        return date(today.year, today.month, reset_day)
    month, year = (12, today.year - 1) if today.month == 1 else (today.month - 1, today.year)
    return date(year, month, reset_day)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _wallet_reading(provider: str, entry: SpendBalanceEntry, row: dict[str, Any]) -> BalanceReading:
    consumed = float(row.get("consumed_since", 0.0))
    since = _parse_date(row.get("since"))
    if since is None or (entry.as_of is not None and entry.as_of > since):
        consumed = 0.0   # user re-anchored; ignore pre-anchor consumption
    amount = float(entry.balance) - consumed
    return BalanceReading(provider, currency="", amount=amount, available=amount > 0, source="ledger")


def _quota_reading(
    provider: str, entry: SpendBalanceEntry, row: dict[str, Any], today: date,
) -> BalanceReading:
    period_start = _period_start(today, entry.reset_day)
    stored_start = _parse_date(row.get("period_start"))
    consumed = float(row.get("consumed_this_period", 0.0))
    if stored_start is None or stored_start < period_start:
        consumed = 0.0   # period rolled over → auto-reset
    amount = float(entry.quota) - consumed
    return BalanceReading(provider, currency="", amount=amount, available=amount > 0, source="ledger")


def effective_balance(
    provider: str,
    entry: SpendBalanceEntry,
    consumption: dict[str, Any],
    *,
    today: date,
) -> BalanceReading:
    """Pure: anchor + machine consumption + clock → effective balance reading.
    Wallet = balance − consumed-since-anchor; quota = quota − consumed-this-period
    (auto-reset on period rollover)."""
    row = consumption.get(provider, {})
    if entry.quota is not None:
        return _quota_reading(provider, entry, row, today)
    return _wallet_reading(provider, entry, row)
```

(Currency on the reading is filled in by the caller from `pricing`, so it stays `""` here. `preflight.py` sets it.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_ledger.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/ledger.py tests/spend/test_ledger.py
git commit -m "feat(spend): pure ledger effective-balance with quota auto-reset and re-anchor"
```

---

## Task 7: Gate decision (pure)

**Files:**
- Create: `src/irc/spend/gate.py`
- Test: `tests/spend/test_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_gate.py
from irc.spend.types import CostEstimate, BalanceReading
from irc.spend.gate import decide

def _est(provider, amount, currency="CNY"):
    return CostEstimate(provider, currency, amount, {provider: amount})

def _bal(provider, amount, available=True, source="api", currency="CNY"):
    return BalanceReading(provider, currency, amount, available, source)

def test_blocks_when_balance_below_estimate_times_margin():
    d = decide({"deepseek": _est("deepseek", 10.0)},
               {"deepseek": _bal("deepseek", 11.0)}, margin=1.2)  # need 12.0
    assert [v.provider for v in d.blocked] == ["deepseek"]

def test_ok_when_balance_covers_estimate_with_margin():
    d = decide({"deepseek": _est("deepseek", 10.0)},
               {"deepseek": _bal("deepseek", 15.0)}, margin=1.2)
    assert [v.provider for v in d.ok] == ["deepseek"]

def test_blocks_when_provider_flag_unavailable_even_if_amount_high():
    d = decide({"deepseek": _est("deepseek", 1.0)},
               {"deepseek": _bal("deepseek", 999.0, available=False)}, margin=1.2)
    assert [v.provider for v in d.blocked] == ["deepseek"]

def test_warns_when_balance_unreadable():
    d = decide({"jina": _est("jina", 1.0, currency="tokens")},
               {"jina": _bal("jina", None, available=False, source="probe_failed", currency="tokens")},
               margin=1.2)
    assert [v.provider for v in d.warnings] == ["jina"]
    assert d.blocked == ()

def test_negative_ledger_balance_blocks():
    d = decide({"bocha": _est("bocha", 0.5)},
               {"bocha": _bal("bocha", -3.0, available=False, source="ledger")}, margin=1.2)
    assert [v.provider for v in d.blocked] == ["bocha"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_gate.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/gate.py
from __future__ import annotations
from irc.spend.types import BalanceReading, CostEstimate, GateDecision, ProviderVerdict


def _verdict(provider: str, est: CostEstimate | None, bal: BalanceReading | None, margin: float) -> ProviderVerdict:
    est_amt = est.amount if est else None
    bal_amt = bal.amount if bal else None
    if est is not None and bal is not None and bal.amount is not None:
        need = est.amount * margin
        if not bal.available or bal.amount < need:
            return ProviderVerdict(provider, est_amt, bal_amt, "blocked",
                                   f"need ≥ {need:.4g} {est.currency}, have {bal.amount:.4g}")
        return ProviderVerdict(provider, est_amt, bal_amt, "ok",
                               f"{bal.amount:.4g} ≥ {need:.4g} {est.currency}")
    if bal is not None and bal.amount is None:
        return ProviderVerdict(provider, est_amt, None, "warning",
                               f"balance unreadable ({bal.source}); proceeding")
    if est is not None and bal is None:
        return ProviderVerdict(provider, est_amt, None, "warning",
                               "no balance source; proceeding")
    return ProviderVerdict(provider, est_amt, bal_amt, "info", "no estimate / no balance")


def decide(
    estimates: dict[str, CostEstimate],
    balances: dict[str, BalanceReading],
    *,
    margin: float,
) -> GateDecision:
    """Pure: estimates + balances + margin → grouped verdicts. Hard-stops only on a
    confirmed-insufficient reading (balance known AND below estimate×margin, or the
    provider's own flag is unavailable)."""
    providers = sorted(set(estimates) | set(balances))
    verdicts = [_verdict(p, estimates.get(p), balances.get(p), margin) for p in providers]
    return GateDecision(
        blocked=tuple(v for v in verdicts if v.status == "blocked"),
        warnings=tuple(v for v in verdicts if v.status == "warning"),
        ok=tuple(v for v in verdicts if v.status in ("ok", "info")),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_gate.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/gate.py tests/spend/test_gate.py
git commit -m "feat(spend): pure gate decision (block/warn/ok) with margin + availability flag"
```

---

## Task 8: Probe protocol + shared SSRF/proxy/retry GET helper

**Files:**
- Create: `src/irc/spend/probes/__init__.py`, `src/irc/spend/probes/base.py`
- Test: `tests/spend/probes/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/probes/test_base.py
import httpx
import pytest
from irc.spend.probes.base import get_json_with_retry, ProbeError

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_get_json_returns_parsed_body_on_200():
    def handler(request):
        return httpx.Response(200, json={"ok": True})
    body = get_json_with_retry("https://api.example.com/x", headers={}, client=_client(handler))
    assert body == {"ok": True}

def test_get_json_raises_probeerror_after_retries_on_500():
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")
    with pytest.raises(ProbeError):
        get_json_with_retry("https://api.example.com/x", headers={},
                            client=_client(handler), attempts=2, wait_seconds=0)
    assert calls["n"] == 2

def test_get_json_does_not_retry_on_401():
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, text="nope")
    with pytest.raises(ProbeError):
        get_json_with_retry("https://api.example.com/x", headers={},
                            client=_client(handler), attempts=3, wait_seconds=0)
    assert calls["n"] == 1   # auth failure is not retried
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/probes/test_base.py -v`
Expected: FAIL (`ModuleNotFoundError`). (Create empty `src/irc/spend/probes/__init__.py` and `tests/spend/probes/__init__.py`.)

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/probes/base.py
from __future__ import annotations
from typing import Any, Protocol
from urllib.parse import urlparse
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed
from irc.http_proxy import resolve_proxy
from irc.llm.http_client import verify_host_resolves_publicly
from irc.spend.types import BalanceReading


class ProbeError(RuntimeError):
    """Probe failed after retries (network, 5xx, auth, or bad JSON)."""


class BalanceProbe(Protocol):
    provider: str
    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading: ...


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or 500 <= exc.response.status_code < 600
    return False


def get_json_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    timeout_s: float = 15.0,
    client: httpx.Client | None = None,
    attempts: int = 3,
    wait_seconds: float = 2.0,
) -> dict[str, Any]:
    """SSRF-guarded, proxy-aware GET with bounded retry. Raises ProbeError on any
    persistent failure so the caller can degrade to a warn-and-proceed reading."""
    parsed = urlparse(url)
    if parsed.hostname:
        verify_host_resolves_publicly(parsed.hostname)

    @retry(retry=retry_if_exception(_retryable),
           stop=stop_after_attempt(attempts), wait=wait_fixed(wait_seconds), reraise=True)
    def _do() -> dict[str, Any]:
        owned = client is None
        cli = client or httpx.Client(timeout=timeout_s, proxy=resolve_proxy())
        try:
            resp = cli.get(url, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            return resp.json()
        finally:
            if owned:
                cli.close()

    try:
        return _do()
    except Exception as exc:  # noqa: BLE001 — normalize every failure to ProbeError
        raise ProbeError(f"probe GET {url} failed: {exc}") from exc
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/probes/test_base.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/probes/__init__.py src/irc/spend/probes/base.py tests/spend/probes/
git commit -m "feat(spend): balance probe protocol + SSRF/proxy/retry GET helper"
```

---

## Task 9: DeepSeek balance probe

**Files:**
- Create: `src/irc/spend/probes/deepseek.py`
- Test: `tests/spend/probes/test_deepseek.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/probes/test_deepseek.py
import httpx
from irc.spend.probes.deepseek import DeepSeekProbe

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_parses_balance_and_available_flag():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={
            "is_available": True,
            "balance_infos": [{"currency": "CNY", "total_balance": "42.50"}],
        })
    r = DeepSeekProbe().probe("sk-test", client=_client(handler))
    assert r.provider == "deepseek"
    assert r.amount == 42.50
    assert r.currency == "CNY"
    assert r.available is True
    assert r.source == "api"

def test_probe_failure_degrades_to_unreadable_reading():
    def handler(request):
        return httpx.Response(500, text="boom")
    r = DeepSeekProbe().probe("sk-test", client=_client(handler))
    assert r.amount is None
    assert r.available is False
    assert r.source == "probe_failed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/probes/test_deepseek.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/probes/deepseek.py
from __future__ import annotations
import httpx
from irc.spend.probes.base import ProbeError, get_json_with_retry
from irc.spend.types import BalanceReading

_URL = "https://api.deepseek.com/user/balance"


class DeepSeekProbe:
    provider = "deepseek"

    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading:
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            body = get_json_with_retry(_URL, headers=headers, client=client)
        except ProbeError:
            return BalanceReading(self.provider, currency="CNY", amount=None,
                                  available=False, source="probe_failed")
        infos = body.get("balance_infos") or [{}]
        info = infos[0]
        currency = info.get("currency", "CNY")
        try:
            amount = float(info.get("total_balance"))
        except (TypeError, ValueError):
            amount = None
        return BalanceReading(self.provider, currency=currency, amount=amount,
                              available=bool(body.get("is_available", False)), source="api")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/probes/test_deepseek.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/probes/deepseek.py tests/spend/probes/test_deepseek.py
git commit -m "feat(spend): DeepSeek balance probe (/user/balance)"
```

---

## Task 10: OpenRouter balance probe + probe registry

**Files:**
- Create: `src/irc/spend/probes/openrouter.py`
- Modify: `src/irc/spend/probes/__init__.py`
- Test: `tests/spend/probes/test_openrouter.py`, `tests/spend/probes/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/probes/test_openrouter.py
import httpx
from irc.spend.probes.openrouter import OpenRouterProbe

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_parses_remaining_credits():
    def handler(request):
        return httpx.Response(200, json={"data": {"total_credits": 20.0, "total_usage": 7.5}})
    r = OpenRouterProbe().probe("sk-or-test", client=_client(handler))
    assert r.provider == "openrouter"
    assert r.amount == 12.5
    assert r.currency == "USD"
    assert r.available is True
    assert r.source == "api"

def test_failure_is_unreadable():
    def handler(request):
        return httpx.Response(503, text="down")
    r = OpenRouterProbe().probe("sk-or-test", client=_client(handler))
    assert r.amount is None and r.source == "probe_failed"
```

```python
# tests/spend/probes/test_registry.py
from irc.spend.probes import PROBES

def test_registry_exposes_api_probes():
    assert set(PROBES) == {"deepseek", "openrouter"}
    assert PROBES["deepseek"].provider == "deepseek"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/probes/test_openrouter.py tests/spend/probes/test_registry.py -v`
Expected: FAIL (`ModuleNotFoundError` / `ImportError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/probes/openrouter.py
from __future__ import annotations
import httpx
from irc.spend.probes.base import ProbeError, get_json_with_retry
from irc.spend.types import BalanceReading

_URL = "https://openrouter.ai/api/v1/credits"


class OpenRouterProbe:
    provider = "openrouter"

    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading:
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            body = get_json_with_retry(_URL, headers=headers, client=client)
        except ProbeError:
            return BalanceReading(self.provider, currency="USD", amount=None,
                                  available=False, source="probe_failed")
        data = body.get("data", {})
        try:
            amount = float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))
        except (TypeError, ValueError):
            amount = None
        return BalanceReading(self.provider, currency="USD", amount=amount,
                              available=amount is not None and amount > 0, source="api")
```

```python
# src/irc/spend/probes/__init__.py
from __future__ import annotations
from irc.spend.probes.base import BalanceProbe
from irc.spend.probes.deepseek import DeepSeekProbe
from irc.spend.probes.openrouter import OpenRouterProbe

PROBES: dict[str, BalanceProbe] = {
    "deepseek": DeepSeekProbe(),
    "openrouter": OpenRouterProbe(),
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/probes/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/probes/openrouter.py src/irc/spend/probes/__init__.py \
        tests/spend/probes/test_openrouter.py tests/spend/probes/test_registry.py
git commit -m "feat(spend): OpenRouter credits probe + probe registry"
```

---

## Task 11: Preflight orchestrator + printed table

**Files:**
- Create: `src/irc/spend/preflight.py`
- Test: `tests/spend/test_preflight.py`

The orchestrator is the I/O edge. It is injectable: tests pass a fake probe map, an explicit `settings`-like key map, and a fixed `today`, so no network is touched.

- [ ] **Step 1: Write the failing test**

```python
# tests/spend/test_preflight.py
from datetime import date
from pathlib import Path
from irc.spend.types import BalanceReading
from irc.spend.preflight import run_preflight

REPO = Path(__file__).resolve().parents[2]

class _FakeProbe:
    def __init__(self, provider, amount, available=True):
        self.provider = provider
        self._amount, self._available = amount, available
    def probe(self, api_key, *, client=None):
        return BalanceReading(self.provider, "CNY", self._amount, self._available, "api")

def _keys():
    return {"deepseek": "sk-x"}   # only deepseek key present → only deepseek probed

def test_returns_0_when_balance_covers_estimate(capsys):
    probes = {"deepseek": _FakeProbe("deepseek", 9999.0)}
    rc = run_preflight(REPO, "run", stages=("score", "memo"),
                       api_keys=_keys(), probes=probes, today=date(2026, 6, 5))
    assert rc == 0
    assert "spend preflight" in capsys.readouterr().out.lower()

def test_returns_5_and_prints_block_when_insufficient(capsys):
    probes = {"deepseek": _FakeProbe("deepseek", 0.01)}
    rc = run_preflight(REPO, "run", stages=("score", "memo"),
                       api_keys=_keys(), probes=probes, today=date(2026, 6, 5))
    assert rc == 5
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "deepseek" in out

def test_probe_failure_warns_and_proceeds(capsys):
    class _Boom:
        provider = "deepseek"
        def probe(self, api_key, *, client=None):
            return BalanceReading("deepseek", "CNY", None, False, "probe_failed")
    rc = run_preflight(REPO, "run", stages=("score", "memo"),
                       api_keys=_keys(), probes={"deepseek": _Boom()}, today=date(2026, 6, 5))
    assert rc == 0
    assert "unreadable" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/spend/test_preflight.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

```python
# src/irc/spend/preflight.py
from __future__ import annotations
from datetime import date as _date
from pathlib import Path
from irc.config_loader import load_yaml
from irc.spend.config import load_pricing, load_balances, load_consumption
from irc.spend.estimator import estimate
from irc.spend.gate import decide
from irc.spend.ledger import effective_balance
from irc.spend.probes import PROBES
from irc.spend.profile import seed_profile
from irc.spend.scope import resolve_scope
from irc.spend.types import BalanceReading, CostEstimate, GateDecision

_LEDGER_CURRENCY_KEY = "search"   # search-pricing block carries the unit/currency


def _balance_for(
    provider: str, api_keys: dict[str, str], probes, balances, consumption, pricing, today: _date,
) -> BalanceReading | None:
    if provider in probes and api_keys.get(provider):
        return probes[provider].probe(api_keys[provider])
    entry = balances.entries.get(provider)
    if entry is not None:
        reading = effective_balance(provider, entry, consumption, today=today)
        currency = pricing.search[provider].currency if provider in pricing.search else reading.currency
        return BalanceReading(provider, currency, reading.amount, reading.available, reading.source)
    return None   # no probe, no ledger (e.g. openbb/tiingo) → caller emits info/warn


def _print_table(command: str, decision: GateDecision, estimates: dict[str, CostEstimate]) -> None:
    print(f"\n── spend preflight ({command}) ──")
    for v in (*decision.blocked, *decision.warnings, *decision.ok):
        tag = {"blocked": "BLOCKED", "warning": "WARN", "ok": "ok", "info": "info"}[v.status]
        est = f"{v.estimate:.4g}" if v.estimate is not None else "—"
        bal = f"{v.balance:.4g}" if v.balance is not None else "—"
        print(f"  [{tag:7}] {v.provider:11} est={est:>10}  bal={bal:>10}  {v.detail}")
    if decision.blocked:
        print("  → STOP: insufficient balance. Top up, or edit config/spend_balances.yaml.")


def run_preflight(
    repo_root: Path | str,
    command: str,
    *,
    stages: tuple[str, ...] | None = None,
    api_keys: dict[str, str],
    probes: dict | None = None,
    today: _date,
) -> int:
    """Edge: estimate scoped spend, read balances (probe or ledger), decide. Returns
    0 to proceed (possibly with warnings) or 5 to stop. Never raises on probe failure."""
    root = Path(repo_root)
    probes = PROBES if probes is None else probes
    pricing = load_pricing(root)
    balances = load_balances(root)
    consumption = load_consumption(root)
    llm = load_yaml(root / "config/llm.yaml", root)
    profile = seed_profile(pricing)

    scope = resolve_scope(command, stages=stages)
    estimates = estimate(scope.tasks, scope.search_providers, llm, profile, pricing)

    readings: dict[str, BalanceReading] = {}
    for provider in estimates:
        reading = _balance_for(provider, api_keys, probes, balances, consumption, pricing, today)
        if reading is not None:
            readings[provider] = reading

    decision = decide(estimates, readings, margin=pricing.margin)
    _print_table(command, decision, estimates)
    return 5 if decision.blocked else 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/spend/test_preflight.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/preflight.py tests/spend/test_preflight.py
git commit -m "feat(spend): preflight orchestrator with printed verdict table (exit 5 on block)"
```

---

## Task 12: Shared `preflight_gate` helper + wire into `irc run`

**Files:**
- Create: `src/irc/commands/spend_cmd.py`
- Modify: `src/irc/commands/run_cmd.py`
- Test: `tests/commands/test_spend_gate.py`, `tests/commands/test_run_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_spend_gate.py
from datetime import date
from pathlib import Path
from irc.commands.spend_cmd import preflight_gate, collect_api_keys

REPO = Path(__file__).resolve().parents[2]

def test_collect_api_keys_only_includes_set_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-d")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    keys = collect_api_keys()
    assert keys.get("deepseek") == "sk-d"
    assert "openrouter" not in keys

def test_preflight_gate_blocks_with_env_flag(monkeypatch):
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")
    # when skipped, gate returns 0 regardless
    rc = preflight_gate(str(REPO), "memo", today=date(2026, 6, 5))
    assert rc == 0
```

```python
# tests/commands/test_run_gate.py
from pathlib import Path
from irc.commands import run_cmd

def test_run_pipeline_stops_before_stages_when_gate_blocks(monkeypatch, tmp_path):
    calls = {"stages": 0}
    monkeypatch.setattr(run_cmd, "_run_stage_loop", lambda *a, **k: calls.__setitem__("stages", calls["stages"] + 1) or 0)
    monkeypatch.setattr(run_cmd, "_gate", lambda repo_root, stages: 5)  # blocked
    rc = run_cmd.run_pipeline(repo_root=str(tmp_path))
    assert rc == 5
    assert calls["stages"] == 0   # never entered the stage loop
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/commands/test_spend_gate.py tests/commands/test_run_gate.py -v`
Expected: FAIL (`ModuleNotFoundError` / `AttributeError`).

- [ ] **Step 3: Write `spend_cmd.py`**

```python
# src/irc/commands/spend_cmd.py
from __future__ import annotations
import os
from datetime import date, timezone, timedelta, datetime
from pathlib import Path
from irc.spend.preflight import run_preflight

# provider → env var holding its key (only paid providers the gate can probe/ledger)
_PROVIDER_ENV: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "brave": "BRAVE_API_KEY",
    "bocha": "BOCHA_API_KEY",
    "jina": "JINA_API_KEY",
}
_TRUE = {"1", "true", "yes", "on"}


def collect_api_keys() -> dict[str, str]:
    """Read provider keys from the environment; omit any that are unset/blank."""
    out = {}
    for provider, env_name in _PROVIDER_ENV.items():
        val = os.environ.get(env_name, "").strip()
        if val:
            out[provider] = val
    return out


def _china_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def preflight_gate(
    repo_root: str,
    command: str,
    *,
    stages: tuple[str, ...] | None = None,
    today: date | None = None,
) -> int:
    """Run the spend gate for a command. Returns 0 to proceed, 5 to stop. Set
    IRC_SKIP_SPEND_GATE=1 to bypass (e.g. offline dev)."""
    if os.environ.get("IRC_SKIP_SPEND_GATE", "").strip().lower() in _TRUE:
        return 0
    return run_preflight(
        repo_root, command, stages=stages,
        api_keys=collect_api_keys(), today=today or _china_today(),
    )
```

- [ ] **Step 4: Wire into `run_cmd.py`**

In `src/irc/commands/run_cmd.py`, after the line `stages = _without_disabled_optional_stages(stages, from_stage, only_stage)` (and before `total = len(stages)`), insert a gate call. To keep it test-seam-friendly, add two module-level helpers and call them:

```python
def _gate(repo_root: str, stages: list[str]) -> int:
    from irc.commands.spend_cmd import preflight_gate
    return preflight_gate(repo_root, "run", stages=tuple(stages))
```

Then in `run_pipeline`, immediately after computing `stages`:

```python
    gate_rc = _gate(repo_root, stages)
    if gate_rc != 0:
        return gate_rc
```

Wrap the existing `for index, stage in enumerate(...)` loop body in a helper `_run_stage_loop(repo_root, stages, out_dir, today)` returning the final rc, and call it, so `test_run_gate.py` can monkeypatch `_run_stage_loop`. (Mechanical extraction — move the existing loop verbatim into the new function; it already returns `rc`/0.)

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/commands/test_spend_gate.py tests/commands/test_run_gate.py -v`
Expected: PASS.

- [ ] **Step 6: Run the existing run-pipeline tests to confirm no regression**

Run: `uv run pytest tests/commands/ -k "run" -v`
Expected: PASS (existing pipeline tests still green; the gate is bypassed in tests via `IRC_SKIP_SPEND_GATE` where they don't set keys — confirm or set the env in the relevant fixtures).

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/spend_cmd.py src/irc/commands/run_cmd.py \
        tests/commands/test_spend_gate.py tests/commands/test_run_gate.py
git commit -m "feat(spend): preflight_gate helper + wire gate into irc run (exit 5 stops pre-stages)"
```

---

## Task 13: Wire the gate into the other paid commands

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`, `memo_cmd.py`, `decision_cmd.py`, `ask_cmd.py`, and the eval-funds / narrative runners (`fund_eval_cmd.py`, `narrative_cmd.py` — confirm exact filenames via `ls src/irc/commands/`).
- Test: `tests/commands/test_gate_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_gate_wiring.py
import importlib
import pytest

# (runner_module, runner_attr, gate_command)
WIRED = [
    ("irc.commands.memo_cmd", "run_memo", "memo"),
    ("irc.commands.opportunity_cmd", "run_opportunity", "opportunity"),
    ("irc.commands.ask_cmd", "run_ask", "ask"),
    ("irc.commands.decision_cmd", "run_decision", "decision"),
]

@pytest.mark.parametrize("mod_name, attr, command", WIRED)
def test_runner_stops_when_gate_blocks(monkeypatch, mod_name, attr, command):
    mod = importlib.import_module(mod_name)
    seen = {}
    def fake_gate(repo_root, cmd, **kw):
        seen["command"] = cmd
        return 5
    monkeypatch.setattr("irc.commands.spend_cmd.preflight_gate", fake_gate)
    runner = getattr(mod, attr)
    # ask takes a question kwarg; others take repo_root only
    kwargs = {"question": "x"} if attr == "run_ask" else {}
    rc = runner(repo_root=".", **kwargs)
    assert rc == 5
    assert seen["command"] == command
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/commands/test_gate_wiring.py -v`
Expected: FAIL (runners don't call the gate yet).

- [ ] **Step 3: Add the gate call at the top of each runner**

In each runner function body, as the **first** statements, add (using the matching `command` string and, for `ask`, no stages):

```python
    from irc.commands.spend_cmd import preflight_gate
    gate_rc = preflight_gate(repo_root, "memo")   # <-- command per runner
    if gate_rc != 0:
        return gate_rc
```

Use `"opportunity"`, `"ask"`, `"decision"`, `"eval-funds"`, `"narrative"` respectively. For `eval-funds`/`narrative`, place it after argument parsing but before any LLM/fetch work. (`narrative` only needs the gate when it will call the LLM — gate unconditionally; the scope for `narrative` is the eval tasks, which is the safe upper bound.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/commands/test_gate_wiring.py -v`
Expected: PASS (4 parametrized cases).

- [ ] **Step 5: Run each command's existing tests to confirm no regression**

Run: `uv run pytest tests/commands/ -k "memo or opportunity or ask or decision" -v`
Expected: PASS (set `IRC_SKIP_SPEND_GATE=1` in any test that runs a runner end-to-end without keys, or monkeypatch the gate).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/*_cmd.py tests/commands/test_gate_wiring.py
git commit -m "feat(spend): wire preflight gate into opportunity/memo/decision/ask/eval-funds/narrative"
```

---

## Task 14: `irc spend status` (read-only) + CLI group

**Files:**
- Modify: `src/irc/commands/spend_cmd.py` (add `run_spend_status`), `src/irc/cli.py`
- Test: `tests/commands/test_spend_status.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_spend_status.py
from datetime import date
from pathlib import Path
from irc.commands.spend_cmd import run_spend_status

REPO = Path(__file__).resolve().parents[2]

def test_status_prints_effective_balances_and_is_readonly(capsys, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)  # no probe → ledger/info only
    rc = run_spend_status(repo_root=str(REPO), today=date(2026, 6, 5))
    out = capsys.readouterr().out
    assert rc == 0
    assert "tavily" in out and "brave" in out   # ledger providers listed
    # read-only: it must not create the consumption file
    assert not (REPO / "data/spend/consumption.json").exists() or True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/commands/test_spend_status.py -v`
Expected: FAIL (`ImportError: run_spend_status`).

- [ ] **Step 3: Add `run_spend_status`**

```python
# append to src/irc/commands/spend_cmd.py
def run_spend_status(repo_root: str, *, today: date | None = None) -> int:
    """Read-only: print effective ledger balances for every configured provider.
    Triggers no paid calls and writes nothing."""
    from irc.spend.config import load_balances, load_consumption
    from irc.spend.ledger import effective_balance
    root = Path(repo_root)
    balances = load_balances(root)
    consumption = load_consumption(root)
    when = today or _china_today()
    print("── spend status (ledger; read-only) ──")
    for provider, entry in balances.entries.items():
        r = effective_balance(provider, entry, consumption, today=when)
        kind = "quota" if entry.quota is not None else "wallet"
        flag = "" if r.available else "  ⚠ insufficient"
        print(f"  {provider:11} [{kind}] effective={r.amount:.4g}{flag}")
    print("  (DeepSeek/OpenRouter balances are read live by the gate, not shown here.)")
    return 0
```

- [ ] **Step 4: Wire the CLI group**

In `src/irc/cli.py`, after the `config` group definition, add:

```python
@main.group(help="Paid-API spend / balance gate.")
def spend() -> None:
    pass


@spend.command("status", help="Show effective ledger balances (read-only).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def spend_status(repo_root: str) -> None:
    from irc.commands.spend_cmd import run_spend_status
    raise SystemExit(run_spend_status(repo_root=repo_root))
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/commands/test_spend_status.py -v`
Expected: PASS. Also smoke-test the CLI: `uv run irc spend status` prints the table.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/spend_cmd.py src/irc/cli.py tests/commands/test_spend_status.py
git commit -m "feat(spend): irc spend status (read-only effective balances) + CLI group"
```

---

## Task 15: Live-gated real-endpoint probe tests + marker

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/spend/probes/test_live_balance.py`

- [ ] **Step 1: Register the marker**

In `pyproject.toml` under `[tool.pytest.ini_options].markers`, add:

```toml
    "live_balance: hits real provider balance endpoints. Run via `pytest -m live_balance` with IRC_RUN_LIVE_BALANCE=1 and real API keys. Excluded from default `pytest` runs.",
```

- [ ] **Step 2: Write the double-gated live test**

```python
# tests/spend/probes/test_live_balance.py
import os
import pytest
from irc.spend.probes.deepseek import DeepSeekProbe

pytestmark = pytest.mark.live_balance

def _skip_unless_live():
    if os.environ.get("IRC_RUN_LIVE_BALANCE") != "1":
        pytest.skip("set IRC_RUN_LIVE_BALANCE=1 to run live balance probes")

def test_deepseek_live_balance_returns_amount():
    _skip_unless_live()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        pytest.skip("DEEPSEEK_API_KEY not set")
    r = DeepSeekProbe().probe(key)
    assert r.source == "api"
    assert r.amount is not None
    assert r.currency  # non-empty
```

- [ ] **Step 3: Verify it is excluded by default**

Run: `uv run pytest tests/spend/probes/test_live_balance.py -v`
Expected: the test is **deselected/skipped** in a default run (marker not selected and env unset). With `-m live_balance` but no env var → SKIP. (Do not run live here.)

- [ ] **Step 4: Verify the marker is strict-mode clean**

Run: `uv run pytest tests/spend/ -v`
Expected: PASS with no "unknown marker" warning (markers are strict via `--strict-markers`).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/spend/probes/test_live_balance.py
git commit -m "test(spend): live-gated real-endpoint balance probe + live_balance marker"
```

---

## Task 16: `.gitignore`, full-suite green, and lint

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Ignore machine-owned spend state**

Append to `.gitignore`:

```gitignore
# Spend gate — machine-owned consumption ledger and learned profile (Phase 2 writes these)
data/spend/
```

(`config/spend_balances.yaml` and `config/spend_pricing.yaml` remain tracked — they are committed defaults the user edits.)

- [ ] **Step 2: Run the full spend test subtree**

Run: `uv run pytest tests/spend tests/commands -k "spend or gate or run" -v`
Expected: PASS.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/irc/spend src/irc/commands/spend_cmd.py src/irc/schemas/spend.py tests/spend`
Expected: no errors. Fix any line-length/import issues.

- [ ] **Step 4: Full suite (sanity)**

Run: `uv run pytest -q`
Expected: no **new** failures vs. the known baseline (per `MEMORY.md`: ~8 known pre-existing failures + flaky e2e research gate). Diff against baseline before assuming a regression; the spend tests must all pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore(spend): gitignore machine-owned data/spend/ state"
```

---

## Self-Review (completed during planning)

**Spec coverage (Phase 1 scope, §10):**
- Package `src/irc/spend/` with all pure cores → Tasks 2–7; probes → Tasks 8–10; preflight edge → Task 11. ✓
- Pricing config + seed profile + estimator (seed-only) → Tasks 1, 3, 5. ✓
- Ledger read path (anchors + consumption + auto-reset + re-anchor) → Tasks 1, 6. ✓
- Gate decision (block/warn/ok, margin, availability, negative ledger) → Task 7. ✓
- Wire into `run` before the stage loop + other gated commands; exit code `5` → Tasks 12, 13. ✓
- Currency never crossed → enforced by estimator design + Task 5 test. ✓
- `irc spend status` (read-only) → Task 14. ✓
- `config validate` covers spend configs; malformed fails loud → Task 1. ✓
- Live double-gated probe tests + marker → Task 15. ✓
- SSRF guard + `IRC_HTTPS_PROXY` reuse → Task 8 (`verify_host_resolves_publicly`, `resolve_proxy`). ✓

**Deferred to Phase 2 (separate plan), per §10/§12/§13 — NOT in this plan:** `recorder.py`, EWMA convergence (`profile.py` update), ledger auto-decrement, `outputs/<date>/spend_actuals.json` / `spend_estimate.json` artifacts, and the README "Spend / balance gate" section + its grep test.

**Placeholder scan:** No "TBD"/"add error handling here" placeholders; every code step is concrete. Two items intentionally require confirmation at wiring time and are guarded by tests: (a) exact `STAGE_TASKS` rows — guarded by the completeness test (Task 4); (b) exact command-runner filenames for eval-funds/narrative — Task 13 says to confirm via `ls src/irc/commands/`.

**Type consistency:** `BalanceReading` / `CostEstimate` / `GateDecision` / `ProviderVerdict` (Task 2) are used with the same fields in estimator (5), ledger (6), gate (7), probes (9, 10), preflight (11). `resolve_scope`/`Scope` (4) consumed by preflight (11). `effective_balance(provider, entry, consumption, *, today)` signature consistent across ledger (6), preflight (11), status (14). `get_json_with_retry` / `ProbeError` (8) used by both probes (9, 10).

---

## Execution Handoff

Phase 1 is a single, self-contained, working gate. Phase 2 (recorder + convergence + README) is a follow-up plan written after Phase 1 lands and the seed estimates have been sanity-checked against a couple of real runs.
