# Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the repo skeleton, the configuration system (inputs + 12 config YAMLs with pydantic schemas), the LLM gateway (DeepSeek direct + OpenRouter), and a working CLI that supports `irc init`, `irc config validate`, and `irc freshness`.

**Architecture:** Single Python package `src/irc/` with stage-aligned subpackages. Pure-function pipeline conventions established here: configs are immutable frozendicts loaded once at startup, all I/O is pushed to stage wrapper layers, no mutable module-level state. LLM gateway exposes a `call(task, payload, config) -> Response` pure-ish surface that hides provider details.

**Tech Stack:** Python 3.12, uv (env), pydantic 2 + pydantic-settings (config + secrets), pyyaml, httpx (LLM HTTP), tenacity (retry), click (CLI), pytest + pytest-mock + respx (HTTP mocks), frozendict.

---

## Plan Series Overview

This is **Plan 1 of 4**:
- Plan 1 (this doc): Foundation — repo, configs, LLM gateway, CLI skeleton.
- Plan 2: Data + DuckDB + Discovery + Scoring — first watchlist + scores.
- Plan 3: Gold scoring + Allocation + Trade Plan + Memo — first usable weekly memo.
- Plan 4: News layer + Research (LDR) + Eval framework + Polish — full MVP.

After Plan 1 lands you can run `irc init`, `irc config validate`, and call DeepSeek / Claude (via OpenRouter) through the gateway, but no investment data flows yet.

---

## File Structure

```
investment-research-copilot/
├── pyproject.toml                          # NEW — deps + entry point
├── .gitignore                              # NEW — Python + .env + data/ + outputs/
├── .env.example                            # NEW — secret template
├── README.md                               # NEW — quickstart
├── src/
│   └── irc/
│       ├── __init__.py                     # NEW — version
│       ├── settings.py                     # NEW — pydantic-settings (env)
│       ├── config_loader.py                # NEW — YAML + schema dispatch
│       ├── cli.py                          # NEW — click entry
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── inputs.py                   # NEW — AccountFile, PreferencesFile
│       │   ├── llm.py                      # NEW — LLMConfig
│       │   ├── scoring.py                  # NEW — ScoringConfig
│       │   ├── gold.py                     # NEW — GoldDriversConfig
│       │   ├── discovery.py                # NEW — DiscoveryConfig
│       │   ├── valuation.py                # NEW — ValuationBucketsConfig
│       │   ├── triggers.py                 # NEW — TriggersConfig
│       │   ├── overrides.py                # NEW — OverridesConfig
│       │   ├── macro_view.py               # NEW — MacroViewConfig
│       │   └── universe.py                 # NEW — UniverseConfig
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── gateway.py                  # NEW — task → (provider,model) + call()
│       │   ├── http_client.py              # NEW — httpx wrapper
│       │   ├── retry.py                    # NEW — tenacity policy
│       │   └── cost_tracker.py             # NEW — token + cost log
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── init_cmd.py                 # NEW — `irc init`
│       │   ├── validate_cmd.py             # NEW — `irc config validate`
│       │   └── freshness_cmd.py            # NEW — `irc freshness`
│       └── templates/                      # NEW — packaged default YAMLs
│           ├── inputs/
│           │   ├── account.yaml
│           │   └── preferences.yaml
│           └── config/
│               ├── llm.yaml
│               ├── scoring.yaml
│               ├── gold_drivers.yaml
│               ├── discovery.yaml
│               ├── valuation_buckets.yaml
│               ├── triggers.yaml
│               ├── overrides.yaml
│               ├── macro_view.yaml
│               └── universe/
│                   ├── qdii_us.yaml
│                   ├── qdii_hk.yaml
│                   ├── cn_funds.yaml
│                   └── gold.yaml
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── schemas/
    │   ├── test_inputs.py
    │   ├── test_llm.py
    │   ├── test_scoring.py
    │   ├── test_gold.py
    │   ├── test_discovery.py
    │   ├── test_valuation.py
    │   ├── test_triggers.py
    │   ├── test_overrides.py
    │   ├── test_macro_view.py
    │   └── test_universe.py
    ├── test_settings.py
    ├── test_config_loader.py
    ├── llm/
    │   ├── test_gateway.py
    │   ├── test_http_client.py
    │   ├── test_retry.py
    │   └── test_cost_tracker.py
    ├── commands/
    │   ├── test_init_cmd.py
    │   ├── test_validate_cmd.py
    │   └── test_freshness_cmd.py
    └── test_cli_smoke.py
```

Files marked NEW are created during this plan. No existing files are modified (this is a fresh repo).

**File-size rule (per CLAUDE.md):** every file < 200 lines, every function < 20 lines. If you hit the limit, split before continuing.

---

## Task 1: Repo Scaffolding (pyproject + gitignore + uv)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/irc/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "investment-research-copilot"
version = "0.1.0"
description = "Weekly research and recommendation system for gold, funds, and ETFs."
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.6,<3",
    "pydantic-settings>=2.2,<3",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "tenacity>=8.2",
    "click>=8.1",
    "frozendict>=2.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "respx>=0.21",
    "ruff>=0.4",
]

[project.scripts]
irc = "irc.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/irc"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
*.egg-info/
build/
dist/
.venv/

# Secrets
.env

# Project artifacts (gitignored, runtime-only)
data/
outputs/

# OS / Editor
.DS_Store
.idea/
.vscode/
```

- [ ] **Step 3: Write `README.md`**

```markdown
# Investment Research Copilot

Weekly research-and-recommendation system for gold + Mainland China funds + Mainland China ETFs + HK ETFs (via QDII proxy) + US ETFs (via QDII proxy). Outputs Markdown research memos with full source provenance.

See `docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md` for the design spec.

## Quick start

```bash
uv sync --all-extras
cp .env.example .env             # then fill DEEPSEEK_API_KEY + OPENROUTER_API_KEY
uv run irc init                  # writes inputs/ + config/ defaults
uv run irc config validate       # checks all YAML
```

## Tests

```bash
uv run pytest
```
```

- [ ] **Step 4: Write `src/irc/__init__.py` and `tests/__init__.py`**

```python
# src/irc/__init__.py
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 5: Write `tests/conftest.py`**

```python
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Empty temporary repo root with inputs/ and config/ ready to populate."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    return tmp_path
```

- [ ] **Step 6: Verify `uv` install works**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv sync --all-extras
```
Expected: succeeds; `.venv/` created; no errors.

- [ ] **Step 7: Verify pytest collects no tests yet**

Run: `uv run pytest`
Expected: "no tests ran" (exit 5) — this is OK for now.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore README.md src/ tests/
git commit -m "feat: repo scaffolding (pyproject, gitignore, package skeleton)"
```

---

## Task 2: Settings Module (pydantic-settings reads .env)

**Files:**
- Create: `.env.example`
- Create: `src/irc/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write `.env.example`**

```bash
# Required (MVP cannot start without these)
DEEPSEEK_API_KEY=sk-replace-me
OPENROUTER_API_KEY=sk-or-replace-me

# Optional (LDR self-hosted)
LDR_BASE_URL=http://localhost:8080
LDR_API_TOKEN=

# Optional (OpenBB premium providers, MVP works without)
OPENBB_FMP_KEY=
OPENBB_TIINGO_KEY=

# Roadmap (not used in MVP)
TUSHARE_TOKEN=
ANTHROPIC_API_KEY=
```

- [ ] **Step 2: Write the failing test `tests/test_settings.py`**

```python
from __future__ import annotations
import pytest
from irc.settings import Settings


def test_settings_loads_required_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    s = Settings()
    assert s.deepseek_api_key == "sk-test-deepseek"
    assert s.openrouter_api_key == "sk-or-test"


def test_settings_missing_deepseek_fails(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    with pytest.raises(Exception):
        Settings()


def test_settings_optional_fields_default_empty(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    s = Settings()
    assert s.openbb_fmp_key == ""
    assert s.tushare_token == ""
```

- [ ] **Step 3: Run test, verify failure**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'Settings'`.

- [ ] **Step 4: Implement `src/irc/settings.py`**

```python
from __future__ import annotations
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loads secrets from .env and OS environment. Field names are lowercased
    and read from upper-case env names by pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required
    deepseek_api_key: str = Field(min_length=1)
    openrouter_api_key: str = Field(min_length=1)

    # Optional (LDR)
    ldr_base_url: str = "http://localhost:8080"
    ldr_api_token: str = ""

    # Optional (OpenBB extras)
    openbb_fmp_key: str = ""
    openbb_tiingo_key: str = ""

    # Roadmap (declared so .env doesn't error on extras)
    tushare_token: str = ""
    anthropic_api_key: str = ""
```

- [ ] **Step 5: Run test, verify pass**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add .env.example src/irc/settings.py tests/test_settings.py
git commit -m "feat(settings): pydantic-settings reads required + optional env vars"
```

---

## Task 3: Inputs Schemas (account.yaml, preferences.yaml)

**Files:**
- Create: `src/irc/schemas/__init__.py`
- Create: `src/irc/schemas/inputs.py`
- Create: `tests/schemas/__init__.py`
- Create: `tests/schemas/test_inputs.py`

- [ ] **Step 1: Write `src/irc/schemas/__init__.py` and `tests/schemas/__init__.py` (empty)**

```python
# src/irc/schemas/__init__.py
```

```python
# tests/schemas/__init__.py
```

- [ ] **Step 2: Write the failing test `tests/schemas/test_inputs.py`**

```python
from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.inputs import (
    AccountFile,
    PreferencesFile,
    Holding,
    AssetClassTarget,
)


def test_account_file_minimal_valid():
    raw = {
        "accounts": [
            {
                "broker": "cmb",
                "currency": "cny",
                "available_venues": ["cmb_fund", "cmb_gold"],
                "holdings": [
                    {"asset_class": "gold", "form": "paper_gold", "cost_basis_cny": 10000}
                ],
            }
        ]
    }
    cfg = AccountFile.model_validate(raw)
    assert cfg.accounts[0].broker == "cmb"
    assert cfg.accounts[0].holdings[0].cost_basis_cny == 10000


def test_account_file_requires_at_least_one_holding():
    raw = {"accounts": [{"broker": "cmb", "currency": "cny", "available_venues": [], "holdings": []}]}
    with pytest.raises(ValidationError):
        AccountFile.model_validate(raw)


def test_preferences_file_minimal_valid():
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }
    cfg = PreferencesFile.model_validate(raw)
    assert cfg.asset_class_targets["gold"].center == 0.20


def test_preferences_centers_must_sum_to_one():
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.50, "band": [0.40, 0.60]},
            "cn_equity_fund": {"center": 0.50, "band": [0.40, 0.60]},
            "cn_bond_fund": {"center": 0.50, "band": [0.40, 0.60]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }
    with pytest.raises(ValidationError):
        PreferencesFile.model_validate(raw)


def test_asset_class_target_band_must_contain_center():
    with pytest.raises(ValidationError):
        AssetClassTarget(center=0.20, band=[0.30, 0.40])
```

- [ ] **Step 3: Run, verify failure**

Run: `uv run pytest tests/schemas/test_inputs.py -v`
Expected: ImportError (module doesn't exist yet).

- [ ] **Step 4: Implement `src/irc/schemas/inputs.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


AssetClass = Literal[
    "gold", "cn_equity_fund", "cn_bond_fund", "cn_etf",
    "hk_etf", "us_etf", "cash"
]
GoldForm = Literal["paper_gold", "physical", "etf", "theme_fund"]
Currency = Literal["cny", "usd", "hkd"]
Broker = Literal["cmb", "huatai", "tiger", "futu", "ibkr", "schwab", "other"]
Venue = Literal[
    "cmb_fund", "cmb_gold",
    "cn_brokerage", "hk_brokerage", "us_brokerage",
]
Horizon = Literal["long_core_medium_rotation", "long_only", "rotation_focus"]
ReportLang = Literal["zh", "en"]


class Holding(BaseModel):
    asset_class: AssetClass
    form: GoldForm | None = None
    instrument_id: str | None = None
    cost_basis_cny: float = Field(ge=0)
    units: float | None = None
    hold_since: str | None = None


class Account(BaseModel):
    broker: Broker
    currency: Currency
    available_venues: list[Venue]
    holdings: list[Holding] = Field(min_length=1)


class AccountFile(BaseModel):
    accounts: list[Account] = Field(min_length=1)


class RiskBand(BaseModel):
    max_drawdown: list[float] = Field(min_length=2, max_length=2)
    horizon: Horizon

    @field_validator("max_drawdown")
    @classmethod
    def _check_band(cls, v: list[float]) -> list[float]:
        lo, hi = v
        if not (0.0 < lo < hi < 1.0):
            raise ValueError(f"max_drawdown must be 0<lo<hi<1, got {v}")
        return v


class UniverseFlags(BaseModel):
    cn_funds: bool
    cn_etfs: bool
    hk_etfs: bool
    us_etfs: bool


class AssetClassTarget(BaseModel):
    center: float = Field(ge=0, le=1)
    band: list[float] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _band_contains_center(self) -> "AssetClassTarget":
        lo, hi = self.band
        if not (0 <= lo <= self.center <= hi <= 1):
            raise ValueError(
                f"band must satisfy 0<=lo<=center<=hi<=1, got center={self.center}, band={self.band}"
            )
        return self


class CurrencyTolerance(BaseModel):
    cny: list[float] = Field(min_length=2, max_length=2)
    usd: list[float] = Field(min_length=2, max_length=2)
    hkd: list[float] = Field(min_length=2, max_length=2)

    @field_validator("cny", "usd", "hkd")
    @classmethod
    def _check_pair(cls, v: list[float]) -> list[float]:
        lo, hi = v
        if not (0.0 <= lo < hi <= 1.0):
            raise ValueError(f"tolerance must be 0<=lo<hi<=1, got {v}")
        return v


class Constraints(BaseModel):
    allow_short: bool
    allow_leverage: bool
    exclude_themes: list[str]


class InvestmentPlan(BaseModel):
    monthly_new_capital_cny: float = Field(ge=0)
    current_total_cny: float | None = Field(default=None, ge=0)


class PreferencesFile(BaseModel):
    risk_band: RiskBand
    universe: UniverseFlags
    asset_class_targets: dict[AssetClass, AssetClassTarget]
    currency_tolerance: CurrencyTolerance
    constraints: Constraints
    investment_plan: InvestmentPlan
    report_language: ReportLang

    @model_validator(mode="after")
    def _centers_sum_to_one(self) -> "PreferencesFile":
        total = sum(t.center for t in self.asset_class_targets.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(f"asset_class_targets centers must sum to ~1.0, got {total:.4f}")
        return self
```

- [ ] **Step 5: Run, verify all 5 tests pass**

Run: `uv run pytest tests/schemas/test_inputs.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/schemas/__init__.py src/irc/schemas/inputs.py tests/schemas/
git commit -m "feat(schemas): inputs (account + preferences) with strict validation"
```

---

## Task 4: LLM Config Schema

**Files:**
- Create: `src/irc/schemas/llm.py`
- Create: `tests/schemas/test_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/schemas/test_llm.py
from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.llm import LLMConfig


def test_llm_config_minimal():
    raw = {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "news_summary": {"provider": "deepseek", "model": "deepseek-chat"},
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
        },
    }
    cfg = LLMConfig.model_validate(raw)
    assert cfg.tasks["memo_synthesis"].provider == "openrouter"


def test_llm_config_unknown_provider_in_task_fails():
    raw = {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
        },
        "tasks": {"x": {"provider": "ghost", "model": "y"}},
    }
    with pytest.raises(ValidationError):
        LLMConfig.model_validate(raw)


def test_llm_config_required_tasks_present():
    """memo_synthesis and memo_audit are required tasks (HARD-fail criticality)."""
    raw = {
        "providers": {
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
        },
    }
    with pytest.raises(ValidationError, match="memo_audit"):
        LLMConfig.model_validate(raw)
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/schemas/test_llm.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/schemas/llm.py`**

```python
from __future__ import annotations
from pydantic import BaseModel, Field, model_validator


REQUIRED_TASKS: tuple[str, ...] = (
    "memo_synthesis",
    "memo_audit",
)


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str = Field(min_length=1)


class TaskRoute(BaseModel):
    provider: str
    model: str = Field(min_length=1)


class LLMConfig(BaseModel):
    providers: dict[str, ProviderConfig] = Field(min_length=1)
    tasks: dict[str, TaskRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_routes(self) -> "LLMConfig":
        for task_name, route in self.tasks.items():
            if route.provider not in self.providers:
                raise ValueError(
                    f"task '{task_name}' references unknown provider '{route.provider}'"
                )
        missing = [t for t in REQUIRED_TASKS if t not in self.tasks]
        if missing:
            raise ValueError(f"required tasks missing: {missing}")
        return self
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/schemas/test_llm.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/schemas/llm.py tests/schemas/test_llm.py
git commit -m "feat(schemas): LLMConfig with provider/task validation"
```

---

## Task 5: Scoring + Gold Drivers Schemas

**Files:**
- Create: `src/irc/schemas/scoring.py`
- Create: `src/irc/schemas/gold.py`
- Create: `tests/schemas/test_scoring.py`
- Create: `tests/schemas/test_gold.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/schemas/test_scoring.py
from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.scoring import ScoringConfig


def test_scoring_config_default_weights_sum_to_one():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 80, "buy_candidate": 60, "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "2026-05-07-v1",
    }
    cfg = ScoringConfig.model_validate(raw)
    assert sum(cfg.factor_weights.values()) == pytest.approx(1.0)


def test_scoring_weights_must_sum_to_one():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.50, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {"strong_buy_candidate": 80, "buy_candidate": 60, "watch": 40, "avoid": 20},
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v",
    }
    with pytest.raises(ValidationError, match="sum"):
        ScoringConfig.model_validate(raw)


def test_action_thresholds_must_be_descending():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 60, "buy_candidate": 80, "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v",
    }
    with pytest.raises(ValidationError, match="descending"):
        ScoringConfig.model_validate(raw)
```

```python
# tests/schemas/test_gold.py
from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.gold import GoldDriversConfig


def test_gold_drivers_minimal():
    raw = {
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.25, "direction": "inverse"},
            "dxy": {"weight": 0.15, "direction": "inverse"},
            "inflation_5y5y": {"weight": 0.15, "direction": "positive"},
            "cb_purchases_wgc": {"weight": 0.15, "direction": "positive_slow"},
            "etf_holdings_gld": {"weight": 0.15, "direction": "confirmation_short"},
            "geopolitical_proxy": {"weight": 0.15, "direction": "positive_pulse"},
        },
        "regime_detection": {
            "vol_window_months": 6, "vol_baseline_window_months": 12,
            "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25,
        },
        "band": {"rolling_window_months": 6},
    }
    cfg = GoldDriversConfig.model_validate(raw)
    assert sum(d.weight for d in cfg.drivers.values()) == pytest.approx(1.0)


def test_gold_weights_sum_to_one_required():
    raw = {
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.50, "direction": "inverse"},
            "dxy": {"weight": 0.50, "direction": "inverse"},
        },
        "regime_detection": {"vol_window_months": 6, "vol_baseline_window_months": 12, "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25},
        "band": {"rolling_window_months": 6},
    }
    # 6 drivers required - this raw has only 2
    with pytest.raises(ValidationError):
        GoldDriversConfig.model_validate(raw)
```

- [ ] **Step 2: Run, verify failures**

Run: `uv run pytest tests/schemas/test_scoring.py tests/schemas/test_gold.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/schemas/scoring.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


FactorName = Literal["valuation_cost", "risk", "quality", "macro_fit", "thesis_news"]
ActionName = Literal["strong_buy_candidate", "buy_candidate", "watch", "avoid"]


class ScoringConfig(BaseModel):
    factor_weights: dict[FactorName, float]
    action_thresholds: dict[ActionName, int]
    conviction_data_completeness_threshold: float = Field(ge=0, le=1)
    weights_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> "ScoringConfig":
        if len(self.factor_weights) != 5:
            raise ValueError("factor_weights must include all 5 factors")
        total = sum(self.factor_weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"factor_weights must sum to 1.0, got {total:.6f}")
        # action_thresholds must be strictly descending
        order: tuple[ActionName, ...] = ("strong_buy_candidate", "buy_candidate", "watch", "avoid")
        vals = [self.action_thresholds[k] for k in order]
        if any(a <= b for a, b in zip(vals, vals[1:])):
            raise ValueError(f"action_thresholds must be strictly descending, got {vals}")
        return self
```

- [ ] **Step 4: Implement `src/irc/schemas/gold.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


DriverName = Literal[
    "real_yield_10y_tips", "dxy", "inflation_5y5y",
    "cb_purchases_wgc", "etf_holdings_gld", "geopolitical_proxy",
]
DriverDirection = Literal[
    "inverse", "positive", "positive_slow", "confirmation_short", "positive_pulse",
]


class DriverSpec(BaseModel):
    weight: float = Field(ge=0, le=1)
    direction: DriverDirection


class RegimeDetection(BaseModel):
    vol_window_months: int = Field(gt=0)
    vol_baseline_window_months: int = Field(gt=0)
    vol_ratio_range_threshold: float = Field(gt=0)
    adx_range_threshold: float = Field(gt=0)


class BandConfig(BaseModel):
    rolling_window_months: int = Field(gt=0)


class GoldDriversConfig(BaseModel):
    drivers: dict[DriverName, DriverSpec]
    regime_detection: RegimeDetection
    band: BandConfig

    @model_validator(mode="after")
    def _validate(self) -> "GoldDriversConfig":
        if len(self.drivers) != 6:
            raise ValueError(f"all 6 drivers required, got {len(self.drivers)}")
        total = sum(d.weight for d in self.drivers.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"driver weights must sum to 1.0, got {total:.6f}")
        return self
```

- [ ] **Step 5: Run, verify all tests pass**

Run: `uv run pytest tests/schemas/test_scoring.py tests/schemas/test_gold.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/schemas/scoring.py src/irc/schemas/gold.py tests/schemas/test_scoring.py tests/schemas/test_gold.py
git commit -m "feat(schemas): scoring + gold drivers configs with sum-to-one validation"
```

---

## Task 6: Remaining Config Schemas (Discovery, Valuation, Triggers, Overrides, MacroView, Universe)

**Files:**
- Create: `src/irc/schemas/discovery.py`
- Create: `src/irc/schemas/valuation.py`
- Create: `src/irc/schemas/triggers.py`
- Create: `src/irc/schemas/overrides.py`
- Create: `src/irc/schemas/macro_view.py`
- Create: `src/irc/schemas/universe.py`
- Create: corresponding tests in `tests/schemas/`

- [ ] **Step 1: Write all 6 failing test files**

```python
# tests/schemas/test_discovery.py
from __future__ import annotations
from irc.schemas.discovery import DiscoveryConfig


def test_discovery_config_default():
    raw = {
        "hard_filters": {
            "inception_years_min": 3,
            "cn_fund_aum_cny_min": 500_000_000,
            "us_etf_aum_usd_min": 100_000_000,
            "cn_active_expense_ratio_max": 0.015,
            "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003,
            "etf_daily_volume_cny_min": 10_000_000,
        },
        "quality_filters": {
            "drawdown_3y_buffer": 1.2,
            "tracking_error_max": 0.015,
            "manager_tenure_years_min": 2,
        },
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    }
    cfg = DiscoveryConfig.model_validate(raw)
    assert cfg.hard_filters.inception_years_min == 3
```

```python
# tests/schemas/test_valuation.py
from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.valuation import ValuationBucketsConfig


def test_buckets_must_be_ordered():
    raw = {
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly", "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow", "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold", "granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
        ]
    }
    cfg = ValuationBucketsConfig.model_validate(raw)
    assert cfg.buckets[0].max_percentile == 0.30


def test_buckets_disordered_fails():
    raw = {
        "buckets": [
            {"max_percentile": 0.60, "buy_method": "lump_sum", "granularity": "x"},
            {"max_percentile": 0.30, "buy_method": "dca_weekly", "granularity": "x"},
        ]
    }
    with pytest.raises(ValidationError, match="ascending"):
        ValuationBucketsConfig.model_validate(raw)
```

```python
# tests/schemas/test_triggers.py
from __future__ import annotations
from irc.schemas.triggers import TriggersConfig


def test_triggers_config_minimal():
    raw = {
        "triggers": {
            "real_yield_low": {"data_field": "macro.real_yield_10y_tips", "comparator": "<=", "threshold": 0.0},
            "vix_high": {"data_field": "macro.vix", "comparator": ">", "threshold": 25.0},
        }
    }
    cfg = TriggersConfig.model_validate(raw)
    assert "real_yield_low" in cfg.triggers
```

```python
# tests/schemas/test_overrides.py
from __future__ import annotations
from irc.schemas.overrides import OverridesConfig


def test_overrides_lists_default_empty():
    cfg = OverridesConfig.model_validate({"boost_list": [], "ban_list": []})
    assert cfg.boost_list == []
```

```python
# tests/schemas/test_macro_view.py
from __future__ import annotations
from irc.schemas.macro_view import MacroViewConfig


def test_macro_view_minimal():
    raw = {"views": [], "active": False}
    cfg = MacroViewConfig.model_validate(raw)
    assert cfg.active is False


def test_macro_view_with_views():
    raw = {
        "views": [{"text": "Fed will cut by July", "biased_factor": "macro_fit", "bias": 0.10}],
        "active": True,
    }
    cfg = MacroViewConfig.model_validate(raw)
    assert cfg.views[0].bias == 0.10
```

```python
# tests/schemas/test_universe.py
from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.universe import UniverseConfig


def test_universe_minimal():
    raw = {
        "instruments": [
            {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
             "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
             "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
        ]
    }
    cfg = UniverseConfig.model_validate(raw)
    assert cfg.instruments[0].instrument_id == "006075"


def test_universe_duplicate_ids_fail():
    raw = {
        "instruments": [
            {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
             "name_cn": "x", "asset_class": "us_etf", "currency": "cny",
             "tracked_index": "y", "venue_required": ["cmb_fund"]},
            {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
             "name_cn": "x", "asset_class": "us_etf", "currency": "cny",
             "tracked_index": "y", "venue_required": ["cmb_fund"]},
        ]
    }
    with pytest.raises(ValidationError, match="duplicate"):
        UniverseConfig.model_validate(raw)
```

- [ ] **Step 2: Run, verify failures**

Run: `uv run pytest tests/schemas/ -v`
Expected: import errors for the 6 new files (existing schemas pass).

- [ ] **Step 3: Implement `src/irc/schemas/discovery.py`**

```python
from __future__ import annotations
from pydantic import BaseModel, Field


class HardFilters(BaseModel):
    inception_years_min: int = Field(ge=0)
    cn_fund_aum_cny_min: float = Field(ge=0)
    us_etf_aum_usd_min: float = Field(ge=0)
    cn_active_expense_ratio_max: float = Field(ge=0, le=1)
    cn_passive_expense_ratio_max: float = Field(ge=0, le=1)
    us_etf_expense_ratio_max: float = Field(ge=0, le=1)
    etf_daily_volume_cny_min: float = Field(ge=0)


class QualityFilters(BaseModel):
    drawdown_3y_buffer: float = Field(gt=0)
    tracking_error_max: float = Field(ge=0, le=1)
    manager_tenure_years_min: float = Field(ge=0)


class RoleBucketConfig(BaseModel):
    min_candidates_per_role: int = Field(gt=0)
    fail_below: int = Field(ge=0)


class DiscoveryConfig(BaseModel):
    hard_filters: HardFilters
    quality_filters: QualityFilters
    role_bucket: RoleBucketConfig
```

- [ ] **Step 4: Implement `src/irc/schemas/valuation.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


BuyMethod = Literal[
    "lump_sum", "dca_weekly", "dca_monthly", "dca_weekly_slow",
    "dca_monthly_threshold", "scaled_in_2", "scaled_in_3", "scaled_in_4",
    "threshold_triggered", "gold_anchor_plus_band", "small_account_anchor",
    "suspend",
]


class Bucket(BaseModel):
    max_percentile: float = Field(ge=0, le=1)
    buy_method: BuyMethod
    granularity: str


class ValuationBucketsConfig(BaseModel):
    buckets: list[Bucket] = Field(min_length=1)

    @model_validator(mode="after")
    def _ascending(self) -> "ValuationBucketsConfig":
        cuts = [b.max_percentile for b in self.buckets]
        if any(a >= b for a, b in zip(cuts, cuts[1:])):
            raise ValueError(f"buckets must be ascending by max_percentile, got {cuts}")
        return self
```

- [ ] **Step 5: Implement `src/irc/schemas/triggers.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


Comparator = Literal["<", "<=", ">", ">=", "==", "!="]


class TriggerSpec(BaseModel):
    data_field: str = Field(min_length=1)
    comparator: Comparator
    threshold: float


class TriggersConfig(BaseModel):
    triggers: dict[str, TriggerSpec] = Field(default_factory=dict)
```

- [ ] **Step 6: Implement `src/irc/schemas/overrides.py`**

```python
from __future__ import annotations
from pydantic import BaseModel, Field


class OverrideEntry(BaseModel):
    instrument_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class OverridesConfig(BaseModel):
    boost_list: list[OverrideEntry] = Field(default_factory=list)
    ban_list: list[OverrideEntry] = Field(default_factory=list)
```

- [ ] **Step 7: Implement `src/irc/schemas/macro_view.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


BiasFactor = Literal["macro_fit", "thesis_news", "risk", "quality", "valuation_cost"]


class MacroViewEntry(BaseModel):
    text: str = Field(min_length=1)
    biased_factor: BiasFactor
    bias: float = Field(ge=-0.30, le=0.30)


class MacroViewConfig(BaseModel):
    views: list[MacroViewEntry] = Field(default_factory=list)
    active: bool = False
```

- [ ] **Step 8: Implement `src/irc/schemas/universe.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


Market = Literal[
    "cn_on_exchange", "cn_off_exchange",
    "hk_on_exchange", "us_on_exchange",
    "cmb_internal",  # for paper gold etc.
]
AssetClass = Literal[
    "gold", "cn_equity_fund", "cn_bond_fund", "cn_etf",
    "hk_etf", "us_etf", "cash",
]
Currency = Literal["cny", "usd", "hkd"]


class Instrument(BaseModel):
    instrument_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    market: Market
    name_cn: str = Field(min_length=1)
    name_en: str | None = None
    asset_class: AssetClass
    currency: Currency
    tracked_index: str | None = None
    venue_required: list[str] = Field(default_factory=list)


class UniverseConfig(BaseModel):
    instruments: list[Instrument] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicates(self) -> "UniverseConfig":
        ids = [i.instrument_id for i in self.instruments]
        if len(ids) != len(set(ids)):
            seen: set[str] = set()
            dups = [x for x in ids if x in seen or seen.add(x)]  # type: ignore
            raise ValueError(f"duplicate instrument_ids: {dups}")
        return self
```

- [ ] **Step 9: Run, verify all tests pass**

Run: `uv run pytest tests/schemas/ -v`
Expected: all schema tests passing (~14 tests).

- [ ] **Step 10: Commit**

```bash
git add src/irc/schemas/discovery.py src/irc/schemas/valuation.py src/irc/schemas/triggers.py src/irc/schemas/overrides.py src/irc/schemas/macro_view.py src/irc/schemas/universe.py tests/schemas/test_discovery.py tests/schemas/test_valuation.py tests/schemas/test_triggers.py tests/schemas/test_overrides.py tests/schemas/test_macro_view.py tests/schemas/test_universe.py
git commit -m "feat(schemas): discovery + valuation + triggers + overrides + macro_view + universe"
```

---

## Task 7: Config Loader (YAML → schema dispatch)

**Files:**
- Create: `src/irc/config_loader.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_loader.py
from __future__ import annotations
from pathlib import Path
import pytest
import yaml
from irc.config_loader import load_yaml, load_repo_configs, ConfigBundle


def write_yaml(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def _minimal_inputs(tmp: Path) -> None:
    write_yaml(tmp / "inputs/account.yaml", {
        "accounts": [
            {"broker": "cmb", "currency": "cny", "available_venues": ["cmb_gold"],
             "holdings": [{"asset_class": "gold", "form": "paper_gold", "cost_basis_cny": 10000}]}
        ]
    })
    write_yaml(tmp / "inputs/preferences.yaml", {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {"cny": [0.40, 0.65], "usd": [0.25, 0.45], "hkd": [0.05, 0.20]},
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    })


def _minimal_configs(tmp: Path) -> None:
    write_yaml(tmp / "config/llm.yaml", {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
            "memo_audit": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6"},
        },
    })
    write_yaml(tmp / "config/scoring.yaml", {
        "factor_weights": {"valuation_cost": 0.10, "risk": 0.25, "quality": 0.20, "macro_fit": 0.25, "thesis_news": 0.20},
        "action_thresholds": {"strong_buy_candidate": 80, "buy_candidate": 60, "watch": 40, "avoid": 20},
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "2026-05-07-v1",
    })
    write_yaml(tmp / "config/gold_drivers.yaml", {
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.25, "direction": "inverse"},
            "dxy": {"weight": 0.15, "direction": "inverse"},
            "inflation_5y5y": {"weight": 0.15, "direction": "positive"},
            "cb_purchases_wgc": {"weight": 0.15, "direction": "positive_slow"},
            "etf_holdings_gld": {"weight": 0.15, "direction": "confirmation_short"},
            "geopolitical_proxy": {"weight": 0.15, "direction": "positive_pulse"},
        },
        "regime_detection": {"vol_window_months": 6, "vol_baseline_window_months": 12, "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25},
        "band": {"rolling_window_months": 6},
    })
    write_yaml(tmp / "config/discovery.yaml", {
        "hard_filters": {
            "inception_years_min": 3, "cn_fund_aum_cny_min": 500_000_000,
            "us_etf_aum_usd_min": 100_000_000,
            "cn_active_expense_ratio_max": 0.015, "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003, "etf_daily_volume_cny_min": 10_000_000,
        },
        "quality_filters": {"drawdown_3y_buffer": 1.2, "tracking_error_max": 0.015, "manager_tenure_years_min": 2},
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    })
    write_yaml(tmp / "config/valuation_buckets.yaml", {
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly", "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow", "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold", "granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
        ]
    })
    write_yaml(tmp / "config/triggers.yaml", {"triggers": {}})
    write_yaml(tmp / "config/overrides.yaml", {"boost_list": [], "ban_list": []})
    write_yaml(tmp / "config/macro_view.yaml", {"views": [], "active": False})
    for name in ("qdii_us", "qdii_hk", "cn_funds", "gold"):
        write_yaml(tmp / f"config/universe/{name}.yaml", {"instruments": []})


def test_load_yaml_dispatches_on_filename(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    cfg = load_yaml(tmp_repo / "inputs/account.yaml")
    assert cfg.accounts[0].broker == "cmb"


def test_load_repo_configs_returns_bundle(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)
    bundle = load_repo_configs(tmp_repo)
    assert isinstance(bundle, ConfigBundle)
    assert bundle.preferences.asset_class_targets["gold"].center == 0.20
    assert bundle.scoring.weights_version == "2026-05-07-v1"


def test_load_repo_configs_bad_yaml_raises(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)
    # Break preferences (invalid centers sum)
    bad = yaml.safe_load((tmp_repo / "inputs/preferences.yaml").read_text())
    bad["asset_class_targets"]["gold"]["center"] = 0.99
    bad["asset_class_targets"]["gold"]["band"] = [0.95, 1.00]
    (tmp_repo / "inputs/preferences.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="sum"):
        load_repo_configs(tmp_repo)
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/config_loader.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

from irc.schemas.inputs import AccountFile, PreferencesFile
from irc.schemas.llm import LLMConfig
from irc.schemas.scoring import ScoringConfig
from irc.schemas.gold import GoldDriversConfig
from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.valuation import ValuationBucketsConfig
from irc.schemas.triggers import TriggersConfig
from irc.schemas.overrides import OverridesConfig
from irc.schemas.macro_view import MacroViewConfig
from irc.schemas.universe import UniverseConfig


_FILENAME_TO_SCHEMA: dict[str, type] = {
    "inputs/account.yaml": AccountFile,
    "inputs/preferences.yaml": PreferencesFile,
    "config/llm.yaml": LLMConfig,
    "config/scoring.yaml": ScoringConfig,
    "config/gold_drivers.yaml": GoldDriversConfig,
    "config/discovery.yaml": DiscoveryConfig,
    "config/valuation_buckets.yaml": ValuationBucketsConfig,
    "config/triggers.yaml": TriggersConfig,
    "config/overrides.yaml": OverridesConfig,
    "config/macro_view.yaml": MacroViewConfig,
    "config/universe/qdii_us.yaml": UniverseConfig,
    "config/universe/qdii_hk.yaml": UniverseConfig,
    "config/universe/cn_funds.yaml": UniverseConfig,
    "config/universe/gold.yaml": UniverseConfig,
}


def _resolve_schema(repo_root: Path, file_path: Path) -> type:
    rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    if rel not in _FILENAME_TO_SCHEMA:
        raise KeyError(f"no schema registered for {rel}")
    return _FILENAME_TO_SCHEMA[rel]


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_yaml(file_path: Path, repo_root: Path | None = None) -> Any:
    """Load a single repo YAML through its registered schema."""
    if repo_root is None:
        repo_root = file_path.parent
        for _ in range(5):
            if (repo_root / "pyproject.toml").exists() or (repo_root / "inputs").exists():
                break
            repo_root = repo_root.parent
    schema = _resolve_schema(repo_root, file_path)
    raw = _read_yaml(file_path)
    return schema.model_validate(raw)


@dataclass(frozen=True)
class ConfigBundle:
    account: AccountFile
    preferences: PreferencesFile
    llm: LLMConfig
    scoring: ScoringConfig
    gold_drivers: GoldDriversConfig
    discovery: DiscoveryConfig
    valuation_buckets: ValuationBucketsConfig
    triggers: TriggersConfig
    overrides: OverridesConfig
    macro_view: MacroViewConfig
    universe_qdii_us: UniverseConfig
    universe_qdii_hk: UniverseConfig
    universe_cn_funds: UniverseConfig
    universe_gold: UniverseConfig


def load_repo_configs(repo_root: Path) -> ConfigBundle:
    """Load every YAML the system needs and return a single immutable bundle.
    Validates each file against its pydantic schema; first failure raises."""
    p = repo_root
    return ConfigBundle(
        account=load_yaml(p / "inputs/account.yaml", p),
        preferences=load_yaml(p / "inputs/preferences.yaml", p),
        llm=load_yaml(p / "config/llm.yaml", p),
        scoring=load_yaml(p / "config/scoring.yaml", p),
        gold_drivers=load_yaml(p / "config/gold_drivers.yaml", p),
        discovery=load_yaml(p / "config/discovery.yaml", p),
        valuation_buckets=load_yaml(p / "config/valuation_buckets.yaml", p),
        triggers=load_yaml(p / "config/triggers.yaml", p),
        overrides=load_yaml(p / "config/overrides.yaml", p),
        macro_view=load_yaml(p / "config/macro_view.yaml", p),
        universe_qdii_us=load_yaml(p / "config/universe/qdii_us.yaml", p),
        universe_qdii_hk=load_yaml(p / "config/universe/qdii_hk.yaml", p),
        universe_cn_funds=load_yaml(p / "config/universe/cn_funds.yaml", p),
        universe_gold=load_yaml(p / "config/universe/gold.yaml", p),
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/config_loader.py tests/test_config_loader.py
git commit -m "feat(config_loader): YAML → schema dispatch + ConfigBundle"
```

---

## Task 8: Default Templates (packaged with code)

**Files:**
- Create: `src/irc/templates/inputs/account.yaml`
- Create: `src/irc/templates/inputs/preferences.yaml`
- Create: `src/irc/templates/config/llm.yaml`
- Create: `src/irc/templates/config/scoring.yaml`
- Create: `src/irc/templates/config/gold_drivers.yaml`
- Create: `src/irc/templates/config/discovery.yaml`
- Create: `src/irc/templates/config/valuation_buckets.yaml`
- Create: `src/irc/templates/config/triggers.yaml`
- Create: `src/irc/templates/config/overrides.yaml`
- Create: `src/irc/templates/config/macro_view.yaml`
- Create: `src/irc/templates/config/universe/qdii_us.yaml`
- Create: `src/irc/templates/config/universe/qdii_hk.yaml`
- Create: `src/irc/templates/config/universe/cn_funds.yaml`
- Create: `src/irc/templates/config/universe/gold.yaml`
- Modify: `pyproject.toml` (include templates as package data)

- [ ] **Step 1: Write `src/irc/templates/inputs/account.yaml`**

```yaml
# Investment Research Copilot — account snapshot
# Edit broker / currency / holdings to match your real situation.
accounts:
  - broker: cmb
    currency: cny
    available_venues: [cmb_fund, cmb_gold]
    holdings:
      - asset_class: gold
        form: paper_gold
        cost_basis_cny: 10000
        # `units` optional; system can back-derive from CMB price history
```

- [ ] **Step 2: Write `src/irc/templates/inputs/preferences.yaml`**

```yaml
# Investment Research Copilot — preferences (gold-20 starter)
risk_band:
  max_drawdown: [0.10, 0.20]
  horizon: long_core_medium_rotation

universe:
  cn_funds: true
  cn_etfs: true
  hk_etfs: true
  us_etfs: true

asset_class_targets:
  gold:           { center: 0.20, band: [0.12, 0.28] }
  cn_equity_fund: { center: 0.25, band: [0.18, 0.35] }
  cn_bond_fund:   { center: 0.15, band: [0.10, 0.25] }
  hk_etf:         { center: 0.10, band: [0.05, 0.15] }
  us_etf:         { center: 0.25, band: [0.18, 0.35] }
  cash:           { center: 0.05, band: [0.00, 0.10] }

currency_tolerance:
  cny: [0.40, 0.65]
  usd: [0.25, 0.45]
  hkd: [0.05, 0.20]

constraints:
  allow_short: false
  allow_leverage: false
  exclude_themes: []

investment_plan:
  monthly_new_capital_cny: 0    # fill once you decide your monthly contribution

report_language: zh
```

- [ ] **Step 3: Write `src/irc/templates/config/llm.yaml`**

```yaml
providers:
  deepseek:
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
  openrouter:
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

tasks:
  news_summary:       { provider: deepseek,   model: deepseek-chat }
  news_dedup:         { provider: deepseek,   model: deepseek-chat }
  factor_screening:   { provider: deepseek,   model: deepseek-chat }
  watchlist_reason:   { provider: deepseek,   model: deepseek-chat }
  scoring_rationale:  { provider: deepseek,   model: deepseek-reasoner }
  thesis_falsify:     { provider: deepseek,   model: deepseek-reasoner }
  interactive_query:  { provider: deepseek,   model: deepseek-reasoner }
  memo_synthesis:     { provider: openrouter, model: anthropic/claude-opus-4.7 }
  memo_audit:         { provider: openrouter, model: anthropic/claude-sonnet-4.6 }
```

- [ ] **Step 4: Write `src/irc/templates/config/scoring.yaml`**

```yaml
factor_weights:
  valuation_cost: 0.10
  risk:           0.25
  quality:        0.20
  macro_fit:      0.25
  thesis_news:    0.20

action_thresholds:
  strong_buy_candidate: 80
  buy_candidate:        60
  watch:                40
  avoid:                20

conviction_data_completeness_threshold: 0.80
weights_version: "2026-05-07-v1"
```

- [ ] **Step 5: Write `src/irc/templates/config/gold_drivers.yaml`**

```yaml
drivers:
  real_yield_10y_tips: { weight: 0.25, direction: inverse }
  dxy:                 { weight: 0.15, direction: inverse }
  inflation_5y5y:      { weight: 0.15, direction: positive }
  cb_purchases_wgc:    { weight: 0.15, direction: positive_slow }
  etf_holdings_gld:    { weight: 0.15, direction: confirmation_short }
  geopolitical_proxy:  { weight: 0.15, direction: positive_pulse }

regime_detection:
  vol_window_months: 6
  vol_baseline_window_months: 12
  vol_ratio_range_threshold: 1.5
  adx_range_threshold: 25

band:
  rolling_window_months: 6
```

- [ ] **Step 6: Write `src/irc/templates/config/discovery.yaml`**

```yaml
hard_filters:
  inception_years_min: 3
  cn_fund_aum_cny_min: 500000000
  us_etf_aum_usd_min: 100000000
  cn_active_expense_ratio_max: 0.015
  cn_passive_expense_ratio_max: 0.005
  us_etf_expense_ratio_max: 0.003
  etf_daily_volume_cny_min: 10000000

quality_filters:
  drawdown_3y_buffer: 1.2
  tracking_error_max: 0.015
  manager_tenure_years_min: 2

role_bucket:
  min_candidates_per_role: 8
  fail_below: 5
```

- [ ] **Step 7: Write `src/irc/templates/config/valuation_buckets.yaml`**

```yaml
buckets:
  - { max_percentile: 0.30, buy_method: lump_sum,                 granularity: "1-2 tranches" }
  - { max_percentile: 0.60, buy_method: dca_weekly,               granularity: "12-16 weeks" }
  - { max_percentile: 0.80, buy_method: dca_weekly_slow,          granularity: "24-26 weeks" }
  - { max_percentile: 0.95, buy_method: dca_monthly_threshold,    granularity: "36+ weeks" }
  - { max_percentile: 1.00, buy_method: suspend,                  granularity: "n/a" }
```

- [ ] **Step 8: Write `src/irc/templates/config/triggers.yaml`**

```yaml
triggers:
  real_yield_low:
    data_field: macro.real_yield_10y_tips
    comparator: "<="
    threshold: 0.0
  vix_high:
    data_field: macro.vix
    comparator: ">"
    threshold: 25.0
  weekly_drawdown_4pct:
    data_field: instrument.weekly_return
    comparator: "<="
    threshold: -0.04
```

- [ ] **Step 9: Write `src/irc/templates/config/overrides.yaml`**

```yaml
boost_list: []
ban_list: []
```

- [ ] **Step 10: Write `src/irc/templates/config/macro_view.yaml`**

```yaml
views: []
active: false
```

- [ ] **Step 11: Write the four universe templates**

```yaml
# src/irc/templates/config/universe/qdii_us.yaml
instruments:
  - { instrument_id: "006075", ticker: "006075", market: cn_off_exchange,
      name_cn: "易方达标普500", asset_class: us_etf, currency: cny,
      tracked_index: "S&P 500", venue_required: [cmb_fund] }
  - { instrument_id: "050025", ticker: "050025", market: cn_off_exchange,
      name_cn: "博时标普500", asset_class: us_etf, currency: cny,
      tracked_index: "S&P 500", venue_required: [cmb_fund] }
  - { instrument_id: "161130", ticker: "161130", market: cn_off_exchange,
      name_cn: "易方达纳斯达克100", asset_class: us_etf, currency: cny,
      tracked_index: "Nasdaq 100", venue_required: [cmb_fund] }
  - { instrument_id: "513500", ticker: "513500", market: cn_on_exchange,
      name_cn: "华夏标普500ETF", asset_class: us_etf, currency: cny,
      tracked_index: "S&P 500", venue_required: [cn_brokerage] }
  - { instrument_id: "159941", ticker: "159941", market: cn_on_exchange,
      name_cn: "广发纳指ETF", asset_class: us_etf, currency: cny,
      tracked_index: "Nasdaq 100", venue_required: [cn_brokerage] }
```

```yaml
# src/irc/templates/config/universe/qdii_hk.yaml
instruments:
  - { instrument_id: "159920", ticker: "159920", market: cn_on_exchange,
      name_cn: "恒生ETF", asset_class: hk_etf, currency: cny,
      tracked_index: "Hang Seng", venue_required: [cn_brokerage] }
  - { instrument_id: "513180", ticker: "513180", market: cn_on_exchange,
      name_cn: "华夏恒生科技", asset_class: hk_etf, currency: cny,
      tracked_index: "Hang Seng Tech", venue_required: [cn_brokerage] }
  - { instrument_id: "513530", ticker: "513530", market: cn_on_exchange,
      name_cn: "港股红利ETF", asset_class: hk_etf, currency: cny,
      tracked_index: "HK Dividend", venue_required: [cn_brokerage] }
```

```yaml
# src/irc/templates/config/universe/cn_funds.yaml
instruments:
  - { instrument_id: "510300", ticker: "510300", market: cn_on_exchange,
      name_cn: "华泰柏瑞沪深300ETF", asset_class: cn_etf, currency: cny,
      tracked_index: "沪深300", venue_required: [cn_brokerage] }
  - { instrument_id: "510500", ticker: "510500", market: cn_on_exchange,
      name_cn: "南方中证500ETF", asset_class: cn_etf, currency: cny,
      tracked_index: "中证500", venue_required: [cn_brokerage] }
```

```yaml
# src/irc/templates/config/universe/gold.yaml
instruments:
  - { instrument_id: "cmb_paper_gold", ticker: "CMB_AU", market: cmb_internal,
      name_cn: "招商银行账户金", asset_class: gold, currency: cny,
      venue_required: [cmb_gold] }
  - { instrument_id: "518880", ticker: "518880", market: cn_on_exchange,
      name_cn: "华安黄金ETF", asset_class: gold, currency: cny,
      tracked_index: "SHFE Au99.99", venue_required: [cn_brokerage] }
  - { instrument_id: "159934", ticker: "159934", market: cn_on_exchange,
      name_cn: "易方达黄金ETF", asset_class: gold, currency: cny,
      tracked_index: "SHFE Au99.99", venue_required: [cn_brokerage] }
```

- [ ] **Step 12: Update `pyproject.toml` to include templates as package data**

Replace the `[tool.hatch.build.targets.wheel]` section with:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/irc"]

[tool.hatch.build.targets.wheel.force-include]
"src/irc/templates" = "irc/templates"
```

- [ ] **Step 13: Verify the templates load through the schemas**

Run:
```bash
uv run python -c "
from pathlib import Path
from irc.config_loader import load_yaml
root = Path('src/irc/templates')
# act like repo root for resolution by symlinking? simpler: just test schemas individually
import yaml
from irc.schemas.inputs import AccountFile, PreferencesFile
print(AccountFile.model_validate(yaml.safe_load(open(root/'inputs/account.yaml'))).accounts[0].broker)
print(PreferencesFile.model_validate(yaml.safe_load(open(root/'inputs/preferences.yaml'))).asset_class_targets['gold'].center)
"
```
Expected: `cmb` and `0.2`.

- [ ] **Step 14: Commit**

```bash
git add src/irc/templates/ pyproject.toml
git commit -m "feat(templates): packaged default inputs + 12 config YAMLs (gold-20 starter)"
```

---

## Task 9: LLM Gateway — Task Routing (pure)

**Files:**
- Create: `src/irc/llm/__init__.py`
- Create: `src/irc/llm/gateway.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_gateway.py`

- [ ] **Step 1: Write empty `__init__.py` files**

```python
# src/irc/llm/__init__.py
```

```python
# tests/llm/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/llm/test_gateway.py
from __future__ import annotations
import pytest
from irc.schemas.llm import LLMConfig
from irc.llm.gateway import resolve_route, ResolvedRoute


def _cfg() -> LLMConfig:
    return LLMConfig.model_validate({
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "news_summary": {"provider": "deepseek", "model": "deepseek-chat"},
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
            "memo_audit": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6"},
        },
    })


def test_resolve_route_returns_provider_model_url():
    r = resolve_route("news_summary", _cfg())
    assert isinstance(r, ResolvedRoute)
    assert r.provider == "deepseek"
    assert r.model == "deepseek-chat"
    assert r.base_url == "https://api.deepseek.com"
    assert r.api_key_env == "DEEPSEEK_API_KEY"


def test_resolve_route_unknown_task_raises():
    with pytest.raises(KeyError, match="unknown task"):
        resolve_route("ghost_task", _cfg())


def test_resolve_route_is_pure():
    cfg1 = _cfg()
    r1 = resolve_route("memo_synthesis", cfg1)
    r2 = resolve_route("memo_synthesis", cfg1)
    assert r1 == r2
    # config object unchanged
    assert cfg1.tasks["memo_synthesis"].model == "anthropic/claude-opus-4.7"
```

- [ ] **Step 3: Run, verify failure**

Run: `uv run pytest tests/llm/test_gateway.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/irc/llm/gateway.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.llm import LLMConfig


@dataclass(frozen=True)
class ResolvedRoute:
    """Outcome of routing a task to a concrete (provider, model, endpoint)."""
    task: str
    provider: str
    model: str
    base_url: str
    api_key_env: str


def resolve_route(task: str, config: LLMConfig) -> ResolvedRoute:
    """Pure: task name → ResolvedRoute. Raises KeyError on unknown task."""
    if task not in config.tasks:
        raise KeyError(f"unknown task: {task!r}")
    route = config.tasks[task]
    provider_cfg = config.providers[route.provider]
    return ResolvedRoute(
        task=task,
        provider=route.provider,
        model=route.model,
        base_url=provider_cfg.base_url,
        api_key_env=provider_cfg.api_key_env,
    )
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/llm/test_gateway.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/llm/__init__.py src/irc/llm/gateway.py tests/llm/__init__.py tests/llm/test_gateway.py
git commit -m "feat(llm/gateway): pure task → ResolvedRoute resolver"
```

---

## Task 10: LLM Retry Policy

**Files:**
- Create: `src/irc/llm/retry.py`
- Create: `tests/llm/test_retry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_retry.py
from __future__ import annotations
import httpx
import pytest
from irc.llm.retry import classify_failure, FailureKind, NoRetryError


def test_classify_429_is_rate_limit():
    resp = httpx.Response(status_code=429)
    assert classify_failure(resp) == FailureKind.RATE_LIMITED


def test_classify_500_is_server_error():
    resp = httpx.Response(status_code=503)
    assert classify_failure(resp) == FailureKind.SERVER_ERROR


def test_classify_401_raises_no_retry():
    resp = httpx.Response(status_code=401)
    with pytest.raises(NoRetryError, match="auth"):
        classify_failure(resp)


def test_classify_400_other_no_retry():
    resp = httpx.Response(status_code=404)
    with pytest.raises(NoRetryError):
        classify_failure(resp)


def test_classify_2xx_returns_ok():
    resp = httpx.Response(status_code=200)
    assert classify_failure(resp) == FailureKind.OK
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/llm/test_retry.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/llm/retry.py`**

```python
from __future__ import annotations
from enum import Enum
import httpx


class FailureKind(str, Enum):
    OK = "ok"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"


class NoRetryError(Exception):
    """Failure classes that must not be retried (auth, 4xx other)."""


def classify_failure(response: httpx.Response) -> FailureKind:
    """Pure classification of an HTTP response into retry policy buckets.
    Raises NoRetryError for 4xx that should not be retried."""
    code = response.status_code
    if 200 <= code < 300:
        return FailureKind.OK
    if code == 429:
        return FailureKind.RATE_LIMITED
    if 500 <= code < 600:
        return FailureKind.SERVER_ERROR
    if code in (401, 403):
        raise NoRetryError(f"auth failure {code}; check credentials")
    raise NoRetryError(f"non-retryable {code}")


# Backoff schedules, exposed as data so caller can compose them.
RATE_LIMIT_BACKOFF_SECONDS: tuple[int, ...] = (2, 4, 8, 16)
SERVER_ERROR_BACKOFF_SECONDS: tuple[int, ...] = (1, 3, 9)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/llm/test_retry.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/llm/retry.py tests/llm/test_retry.py
git commit -m "feat(llm/retry): classify HTTP failures into retry policy buckets"
```

---

## Task 11: LLM Cost Tracker (pure)

**Files:**
- Create: `src/irc/llm/cost_tracker.py`
- Create: `tests/llm/test_cost_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_cost_tracker.py
from __future__ import annotations
from irc.llm.cost_tracker import CostEntry, append_cost, redact_secret


def test_append_cost_returns_new_list_immutable():
    entries: list[CostEntry] = []
    e1 = CostEntry(
        task="news_summary", provider="deepseek", model="deepseek-chat",
        prompt_tokens=120, completion_tokens=80, latency_ms=540,
        ts="2026-05-07T15:00:00+08:00",
    )
    out = append_cost(entries, e1)
    assert len(out) == 1
    assert entries == []  # input unchanged


def test_redact_secret_keeps_last_4():
    assert redact_secret("sk-abcdef1234") == "sk-***1234"
    assert redact_secret("xyz") == "***"
    assert redact_secret("") == ""
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/llm/test_cost_tracker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/llm/cost_tracker.py`**

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CostEntry:
    task: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    ts: str  # ISO 8601 with offset


def append_cost(history: list[CostEntry], entry: CostEntry) -> list[CostEntry]:
    """Pure: returns history + entry as a NEW list (caller does not mutate)."""
    return [*history, entry]


def redact_secret(secret: str) -> str:
    """Mask all but last 4 characters of an API key for safe logging."""
    if not secret:
        return ""
    if len(secret) <= 4:
        return "***"
    return f"{secret[:3]}***{secret[-4:]}"
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/llm/test_cost_tracker.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/llm/cost_tracker.py tests/llm/test_cost_tracker.py
git commit -m "feat(llm/cost_tracker): immutable cost log + secret redaction"
```

---

## Task 12: LLM HTTP Client

**Files:**
- Create: `src/irc/llm/http_client.py`
- Create: `tests/llm/test_http_client.py`

- [ ] **Step 1: Write the failing test (uses respx for HTTP mocking)**

```python
# tests/llm/test_http_client.py
from __future__ import annotations
import pytest
import respx
import httpx
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


@pytest.fixture
def route_deepseek() -> ResolvedRoute:
    return ResolvedRoute(
        task="news_summary",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )


@respx.mock
def test_call_chat_happy_path(route_deepseek, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )
    )
    resp = call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=10)
    assert isinstance(resp, ChatResponse)
    assert resp.text == "Hello"
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 5


@respx.mock
def test_call_chat_429_raises(route_deepseek, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    respx.post("https://api.deepseek.com/v1/chat/completions").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(httpx.HTTPStatusError):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)


def test_call_chat_missing_key_raises(route_deepseek, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        call_chat(route_deepseek, messages=[{"role": "user", "content": "hi"}], timeout_s=5)
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/llm/test_http_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/llm/http_client.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
import os
import time
from typing import Any
import httpx
from irc.llm.gateway import ResolvedRoute


@dataclass(frozen=True)
class ChatResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw: dict[str, Any]


def _resolve_key(env_name: str) -> str:
    val = os.environ.get(env_name, "")
    if not val:
        raise RuntimeError(f"missing required env var: {env_name}")
    return val


def call_chat(
    route: ResolvedRoute,
    messages: list[dict[str, str]],
    timeout_s: float = 30.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatResponse:
    """Make a single chat-completions call. Raises httpx.HTTPStatusError on 4xx/5xx."""
    api_key = _resolve_key(route.api_key_env)
    payload: dict[str, Any] = {
        "model": route.model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    url = f"{route.base_url.rstrip('/')}/v1/chat/completions"
    started = time.perf_counter()
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    resp.raise_for_status()
    body = resp.json()
    return ChatResponse(
        text=body["choices"][0]["message"]["content"],
        prompt_tokens=int(body.get("usage", {}).get("prompt_tokens", 0)),
        completion_tokens=int(body.get("usage", {}).get("completion_tokens", 0)),
        latency_ms=latency_ms,
        raw=body,
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/llm/test_http_client.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/llm/http_client.py tests/llm/test_http_client.py
git commit -m "feat(llm/http_client): OpenAI-compatible chat call with timeout + tokens"
```

---

## Task 13: LLM Live Integration Test (env-gated)

**Files:**
- Create: `tests/llm/test_live_smoke.py`

- [ ] **Step 1: Write env-gated live test**

```python
# tests/llm/test_live_smoke.py
"""Live smoke tests for the LLM gateway. Skipped unless RUN_LIVE_LLM_TESTS=1
AND the relevant API key env vars are set. Used to verify production credentials
and provider URL mapping. Do not run in CI by default."""
from __future__ import annotations
import os
import pytest

from irc.config_loader import load_yaml
from irc.llm.gateway import resolve_route
from irc.llm.http_client import call_chat
from pathlib import Path


_RUN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1"
_HAS_DS = bool(os.environ.get("DEEPSEEK_API_KEY"))
_HAS_OR = bool(os.environ.get("OPENROUTER_API_KEY"))


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_deepseek_chat():
    cfg_path = Path(__file__).resolve().parents[2] / "src/irc/templates/config/llm.yaml"
    # bypass repo-relative resolver: load via direct schema
    import yaml
    from irc.schemas.llm import LLMConfig
    cfg = LLMConfig.model_validate(yaml.safe_load(cfg_path.read_text()))
    route = resolve_route("news_summary", cfg)
    resp = call_chat(route, messages=[{"role": "user", "content": "Reply with the single word: pong"}], timeout_s=30)
    assert "pong" in resp.text.lower()


@pytest.mark.skipif(not (_RUN and _HAS_OR), reason="set RUN_LIVE_LLM_TESTS=1 + OPENROUTER_API_KEY")
def test_live_openrouter_claude():
    cfg_path = Path(__file__).resolve().parents[2] / "src/irc/templates/config/llm.yaml"
    import yaml
    from irc.schemas.llm import LLMConfig
    cfg = LLMConfig.model_validate(yaml.safe_load(cfg_path.read_text()))
    route = resolve_route("memo_audit", cfg)
    resp = call_chat(route, messages=[{"role": "user", "content": "Reply with: pong"}], timeout_s=30)
    assert "pong" in resp.text.lower()
```

- [ ] **Step 2: Run, verify skip without env**

Run: `uv run pytest tests/llm/test_live_smoke.py -v`
Expected: 2 skipped.

- [ ] **Step 3: (Optional, manual) Run with live keys**

Run:
```bash
RUN_LIVE_LLM_TESTS=1 uv run pytest tests/llm/test_live_smoke.py -v
```
Expected: 2 passed (if both keys are valid). Confirms DeepSeek + OpenRouter credentials work.

- [ ] **Step 4: Commit**

```bash
git add tests/llm/test_live_smoke.py
git commit -m "test(llm): env-gated live smoke tests for DeepSeek + OpenRouter"
```

---

## Task 14: CLI Skeleton (click)

**Files:**
- Create: `src/irc/cli.py`
- Create: `src/irc/commands/__init__.py`
- Create: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write `src/irc/commands/__init__.py` (empty)**

```python
# src/irc/commands/__init__.py
```

- [ ] **Step 2: Write the failing CLI smoke test**

```python
# tests/test_cli_smoke.py
from __future__ import annotations
from click.testing import CliRunner
from irc.cli import main


def test_cli_help_lists_subcommands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "config", "freshness"):
        assert cmd in result.output


def test_cli_config_help():
    result = CliRunner().invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.output
```

- [ ] **Step 3: Run, verify failure**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/irc/cli.py`**

```python
from __future__ import annotations
import click


@click.group(help="Investment Research Copilot")
def main() -> None:
    """Entry point for the `irc` CLI."""


@main.group(help="Configuration management.")
def config() -> None:
    pass


@main.command(help="Initialize repo with default inputs/ and config/.")
@click.option("--repo-root", type=click.Path(file_okay=False), default=".",
              help="Repo root (defaults to cwd).")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing files.")
def init(repo_root: str, force: bool) -> None:
    from irc.commands.init_cmd import run_init
    rc = run_init(repo_root=repo_root, force=force)
    raise SystemExit(rc)


@config.command("validate", help="Validate all YAML inputs and configs against schemas.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def config_validate(repo_root: str) -> None:
    from irc.commands.validate_cmd import run_validate
    rc = run_validate(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Show data freshness summary.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def freshness(repo_root: str) -> None:
    from irc.commands.freshness_cmd import run_freshness
    rc = run_freshness(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/cli.py src/irc/commands/__init__.py tests/test_cli_smoke.py
git commit -m "feat(cli): click-based skeleton with init / config validate / freshness"
```

---

## Task 15: `irc init` Command

**Files:**
- Create: `src/irc/commands/init_cmd.py`
- Create: `tests/commands/__init__.py`
- Create: `tests/commands/test_init_cmd.py`

- [ ] **Step 1: Write empty `tests/commands/__init__.py`**

```python
# tests/commands/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/commands/test_init_cmd.py
from __future__ import annotations
from pathlib import Path
import pytest
from irc.commands.init_cmd import run_init


def test_init_creates_inputs_and_config(tmp_path: Path):
    rc = run_init(repo_root=str(tmp_path), force=False)
    assert rc == 0
    assert (tmp_path / "inputs/account.yaml").exists()
    assert (tmp_path / "inputs/preferences.yaml").exists()
    assert (tmp_path / "config/llm.yaml").exists()
    assert (tmp_path / "config/scoring.yaml").exists()
    assert (tmp_path / "config/gold_drivers.yaml").exists()
    assert (tmp_path / "config/discovery.yaml").exists()
    assert (tmp_path / "config/valuation_buckets.yaml").exists()
    assert (tmp_path / "config/triggers.yaml").exists()
    assert (tmp_path / "config/overrides.yaml").exists()
    assert (tmp_path / "config/macro_view.yaml").exists()
    for name in ("qdii_us", "qdii_hk", "cn_funds", "gold"):
        assert (tmp_path / f"config/universe/{name}.yaml").exists()


def test_init_does_not_overwrite_unless_force(tmp_path: Path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/account.yaml").write_text("# user-modified", encoding="utf-8")
    rc = run_init(repo_root=str(tmp_path), force=False)
    assert rc == 0
    assert (tmp_path / "inputs/account.yaml").read_text() == "# user-modified"


def test_init_force_overwrites(tmp_path: Path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/account.yaml").write_text("# user-modified", encoding="utf-8")
    rc = run_init(repo_root=str(tmp_path), force=True)
    assert rc == 0
    assert "broker" in (tmp_path / "inputs/account.yaml").read_text()
```

- [ ] **Step 3: Run, verify failure**

Run: `uv run pytest tests/commands/test_init_cmd.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/irc/commands/init_cmd.py`**

```python
from __future__ import annotations
from importlib import resources
from pathlib import Path


_TEMPLATE_FILES: tuple[str, ...] = (
    "inputs/account.yaml",
    "inputs/preferences.yaml",
    "config/llm.yaml",
    "config/scoring.yaml",
    "config/gold_drivers.yaml",
    "config/discovery.yaml",
    "config/valuation_buckets.yaml",
    "config/triggers.yaml",
    "config/overrides.yaml",
    "config/macro_view.yaml",
    "config/universe/qdii_us.yaml",
    "config/universe/qdii_hk.yaml",
    "config/universe/cn_funds.yaml",
    "config/universe/gold.yaml",
)


def _read_template(rel_path: str) -> str:
    """Read a packaged template by its relative path under irc/templates/."""
    parts = rel_path.split("/")
    pkg = "irc.templates" + "".join(f".{p}" for p in parts[:-1])
    leaf = parts[-1]
    return resources.files(pkg).joinpath(leaf).read_text(encoding="utf-8")


def run_init(repo_root: str, force: bool) -> int:
    """Copy packaged templates into the repo root. Returns exit code."""
    root = Path(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    for rel in _TEMPLATE_FILES:
        dest = root / rel
        if dest.exists() and not force:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_read_template(rel), encoding="utf-8")
        written.append(rel)
    print(f"wrote {len(written)} files; skipped {len(skipped)} existing.")
    if skipped:
        print(f"  skipped (use --force to overwrite): {', '.join(skipped)}")
    return 0
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/commands/test_init_cmd.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/init_cmd.py tests/commands/__init__.py tests/commands/test_init_cmd.py
git commit -m "feat(cli/init): copy packaged templates into repo root with --force option"
```

---

## Task 16: `irc config validate` Command

**Files:**
- Create: `src/irc/commands/validate_cmd.py`
- Create: `tests/commands/test_validate_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_validate_cmd.py
from __future__ import annotations
from pathlib import Path
import yaml
from irc.commands.init_cmd import run_init
from irc.commands.validate_cmd import run_validate


def test_validate_passes_after_init(tmp_path: Path):
    assert run_init(str(tmp_path), force=False) == 0
    rc = run_validate(repo_root=str(tmp_path))
    assert rc == 0


def test_validate_fails_on_corrupted_yaml(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    (tmp_path / "inputs/preferences.yaml").write_text("not: valid: yaml: :", encoding="utf-8")
    rc = run_validate(repo_root=str(tmp_path))
    assert rc != 0


def test_validate_fails_on_schema_violation(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    raw = yaml.safe_load((tmp_path / "config/scoring.yaml").read_text())
    raw["factor_weights"]["risk"] = 0.99  # break sum
    (tmp_path / "config/scoring.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    rc = run_validate(repo_root=str(tmp_path))
    assert rc != 0
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/commands/test_validate_cmd.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/commands/validate_cmd.py`**

```python
from __future__ import annotations
from pathlib import Path
import sys
from irc.config_loader import load_repo_configs


def run_validate(repo_root: str) -> int:
    root = Path(repo_root)
    try:
        bundle = load_repo_configs(root)
    except Exception as exc:  # noqa: BLE001 — surface every config error to user
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    n_inst = (
        len(bundle.universe_qdii_us.instruments)
        + len(bundle.universe_qdii_hk.instruments)
        + len(bundle.universe_cn_funds.instruments)
        + len(bundle.universe_gold.instruments)
    )
    print(
        "OK: all 14 YAML files validated.\n"
        f"  scoring weights version: {bundle.scoring.weights_version}\n"
        f"  universe size: {n_inst} instruments\n"
        f"  llm tasks configured: {len(bundle.llm.tasks)}"
    )
    return 0
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/commands/test_validate_cmd.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/validate_cmd.py tests/commands/test_validate_cmd.py
git commit -m "feat(cli/validate): load all 14 YAMLs through schemas; non-zero on any failure"
```

---

## Task 17: `irc freshness` Command (skeleton — no manifest yet)

**Files:**
- Create: `src/irc/commands/freshness_cmd.py`
- Create: `tests/commands/test_freshness_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_freshness_cmd.py
from __future__ import annotations
from pathlib import Path
import json
from irc.commands.freshness_cmd import run_freshness


def test_freshness_prints_no_manifest(tmp_path: Path, capsys):
    rc = run_freshness(repo_root=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "no manifest" in out.lower()


def test_freshness_summarizes_existing_manifest(tmp_path: Path, capsys):
    manifest_dir = tmp_path / "data/_manifest"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "openbb.json").write_text(json.dumps({
        "source": "openbb",
        "last_run_at": "2026-05-07T12:00:00+08:00",
        "schema_version": "v1",
    }), encoding="utf-8")
    rc = run_freshness(repo_root=str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "openbb" in out
    assert "2026-05-07" in out
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/commands/test_freshness_cmd.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/commands/freshness_cmd.py`**

```python
from __future__ import annotations
from pathlib import Path
import json


def run_freshness(repo_root: str) -> int:
    root = Path(repo_root)
    manifest_dir = root / "data" / "_manifest"
    if not manifest_dir.exists():
        print("no manifest yet — run `irc ingest` once data ingestion ships in Plan 2.")
        return 0
    files = sorted(manifest_dir.glob("*.json"))
    if not files:
        print("no manifest entries — manifest dir is empty.")
        return 0
    print(f"{'source':<16} {'last_run_at':<32} {'schema_version'}")
    for f in files:
        m = json.loads(f.read_text(encoding="utf-8"))
        print(f"{m.get('source','?'):<16} {m.get('last_run_at','?'):<32} {m.get('schema_version','?')}")
    return 0
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/commands/test_freshness_cmd.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/freshness_cmd.py tests/commands/test_freshness_cmd.py
git commit -m "feat(cli/freshness): summary stub reads data/_manifest/*.json (Plan 2-ready)"
```

---

## Task 18: End-to-End Smoke Test (CLI flow)

**Files:**
- Modify: `tests/test_cli_smoke.py:1-22` (extend with full flow)

- [ ] **Step 1: Extend `tests/test_cli_smoke.py` with end-to-end tests**

Append to the end of `tests/test_cli_smoke.py`:

```python
from pathlib import Path


def test_cli_init_then_validate_then_freshness(tmp_path: Path):
    runner = CliRunner()
    r1 = runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(main, ["config", "validate", "--repo-root", str(tmp_path)])
    assert r2.exit_code == 0, r2.output
    assert "OK" in r2.output
    r3 = runner.invoke(main, ["freshness", "--repo-root", str(tmp_path)])
    assert r3.exit_code == 0, r3.output
    assert "no manifest" in r3.output.lower()


def test_cli_init_force_after_modification(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(main, ["init", "--repo-root", str(tmp_path)])
    pref = tmp_path / "inputs/preferences.yaml"
    pref.write_text("# corrupted\n", encoding="utf-8")
    r = runner.invoke(main, ["config", "validate", "--repo-root", str(tmp_path)])
    assert r.exit_code != 0
    runner.invoke(main, ["init", "--repo-root", str(tmp_path), "--force"])
    r2 = runner.invoke(main, ["config", "validate", "--repo-root", str(tmp_path)])
    assert r2.exit_code == 0
```

- [ ] **Step 2: Run, verify pass**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: 4 passed (2 original + 2 new).

- [ ] **Step 3: Run the entire test suite**

Run: `uv run pytest -v`
Expected: ~30+ tests, all pass (live LLM tests skipped without env vars).

- [ ] **Step 4: Run live LLM smoke (optional, manual gate)**

Run:
```bash
RUN_LIVE_LLM_TESTS=1 uv run pytest tests/llm/test_live_smoke.py -v
```
Expected: 2 passed (validates real DeepSeek + OpenRouter credentials).

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli_smoke.py
git commit -m "test(cli): end-to-end init → validate → freshness flow"
```

---

## Task 19: Update README with Real Quickstart

**Files:**
- Modify: `README.md` (full rewrite)

- [ ] **Step 1: Rewrite `README.md`**

```markdown
# Investment Research Copilot

Weekly research-and-recommendation system for gold + Mainland China funds + Mainland China ETFs + HK ETFs (via QDII proxy) + US ETFs (via QDII proxy).

> **Status:** Plan 1 of 4 — foundation only. CLI scaffolding and config validation work. Data ingestion, scoring, and memo generation arrive in Plans 2–4.

## Design references

- MVP design: [docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md](docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md)
- Future Roadmap: [docs/superpowers/specs/2026-05-07-investment-research-copilot-roadmap.md](docs/superpowers/specs/2026-05-07-investment-research-copilot-roadmap.md)

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repo>
cd investment-research-copilot
uv sync --all-extras
cp .env.example .env
# Edit .env to fill DEEPSEEK_API_KEY and OPENROUTER_API_KEY.

uv run irc init                        # writes inputs/ + config/ defaults
uv run irc config validate             # validates all 14 YAML files
uv run irc freshness                   # data manifest summary (empty until Plan 2)
```

## Tests

```bash
uv run pytest                                       # unit + integration (~30 tests)
RUN_LIVE_LLM_TESTS=1 uv run pytest tests/llm/test_live_smoke.py
                                                    # verify live API credentials
```

## Layout

- `src/irc/` — Python package; mirror of design spec §5.A.
- `tests/` — mirrors `src/irc/`.
- `inputs/`, `config/` — generated by `irc init`; user-editable.
- `docs/superpowers/specs/` — design + roadmap.
- `docs/superpowers/plans/` — implementation plans (one per milestone).

## Configuration files

After `irc init` you will have:

- `inputs/account.yaml` — your real holdings + venues.
- `inputs/preferences.yaml` — risk band, asset-class targets, currency tolerance, capital plan.
- `config/llm.yaml` — task → (provider, model) routing.
- `config/scoring.yaml`, `config/gold_drivers.yaml`, `config/discovery.yaml`,
  `config/valuation_buckets.yaml`, `config/triggers.yaml` — tunable parameters.
- `config/overrides.yaml`, `config/macro_view.yaml` — your sovereignty layer.
- `config/universe/*.yaml` — candidate pools.

Edit any of these and re-run `irc config validate`.

## Conventions

- Functional programming: pure stages, immutable configs, I/O confined to wrappers.
- TDD: every feature begins with a failing test.
- Files < 200 lines; functions < 20 lines.
- Every secret in `.env`; YAML configs only reference env names.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): real quickstart + plan-1 status callout"
```

---

## Task 20: Final Plan-1 Tag

- [ ] **Step 1: Run the full test suite once more**

Run: `uv run pytest`
Expected: all green (live LLM tests skipped is fine).

- [ ] **Step 2: Confirm `irc` works end-to-end**

Run:
```bash
uv run irc init --repo-root /tmp/irc-smoke
uv run irc config validate --repo-root /tmp/irc-smoke
uv run irc freshness --repo-root /tmp/irc-smoke
rm -rf /tmp/irc-smoke
```
Expected: each command exits 0; `validate` prints "OK: all 14 YAML files validated."

- [ ] **Step 3: Tag the milestone**

```bash
git tag -a plan-1-foundation -m "Plan 1 complete: foundation (configs + LLM gateway + CLI)"
```

- [ ] **Step 4: Print summary**

You now have:
- A Python package `irc` with proper packaging via `pyproject.toml`.
- 10 pydantic schemas covering inputs + 8 config types + universe.
- A config loader that returns an immutable `ConfigBundle`.
- An LLM gateway that can call DeepSeek and OpenRouter through OpenAI-compatible HTTP.
- A `irc` CLI with `init`, `config validate`, and `freshness` subcommands.
- ~30 unit/integration tests, all green.
- Live smoke tests gated by `RUN_LIVE_LLM_TESTS=1`.

**Next:** Plan 2 — Data layer (OpenBB + AKShare clients) + DuckDB persistence + Discovery 5-step funnel + Scoring 5-factor framework. Drafting that plan is the next step after this milestone is approved.

---

## Self-Review Notes

**Spec coverage check** (against `docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md`):

| Spec section | Plan 1 task |
|---|---|
| §2.A inputs/account.yaml schema | Task 3 |
| §2.A inputs/preferences.yaml schema | Task 3 |
| §2.D LLM gateway providers + tasks | Tasks 4, 9, 10, 11, 12, 13 |
| §2.E secrets via .env | Task 2 |
| §3 scoring config (10/25/20/25/20) | Task 5 |
| §3.C gold drivers config | Task 5 |
| §3.A discovery filters | Task 6 |
| §4.F valuation buckets 5 levels | Task 6 |
| §4.G triggers config | Task 6 |
| §3.E user sovereignty (overrides + macro_view) | Task 6 |
| §4.H QDII universe | Task 8 |
| §5.A directory tree | All tasks |
| §5.D CLI subset (init / config validate / freshness) | Tasks 14, 15, 16, 17 |
| §5.G config files (12) | Task 8 |
| §6.F input validation | Task 16 |
| FP constraints (CLAUDE.md) | All tasks (frozen dataclasses, pure functions, < 200 LoC files) |

**Out of Plan 1 (deferred to Plans 2–4):** all data ingestion, scoring, memo synthesis, eval framework — by design.

**Placeholder scan:** every step contains either explicit code, an explicit command, or an explicit verification expectation. No "TBD" / "implement later" / "similar to" left in the plan.

**Type consistency check:**
- `ResolvedRoute` (Task 9) is consumed unchanged by `call_chat` (Task 12).
- `ChatResponse` (Task 12) carries fields used directly in the live test (Task 13).
- `ConfigBundle` (Task 7) is used by `validate_cmd` (Task 16).
- `_TEMPLATE_FILES` in `init_cmd` (Task 15) matches the 14 templates created in Task 8.
- `LLMConfig.tasks` requires both `memo_synthesis` and `memo_audit` (Task 4); the default `llm.yaml` template (Task 8) provides both.

No mismatched names found.

---

**End of Plan 1.**
