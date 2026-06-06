from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import yaml
from irc.io_utils import atomic_write_text
from irc.schemas.spend import SpendBalancesConfig, SpendPricingConfig
from irc.spend.types import UsageProfile

PRICING_FILE = "config/spend_pricing.yaml"
BALANCES_FILE = "config/spend_balances.yaml"
CONSUMPTION_FILE = "data/spend/consumption.json"
USAGE_PROFILE_FILE = "data/spend/usage_profile.json"


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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"corrupt consumption at {path}: {exc}") from exc


def load_usage_profile_raw(
    repo_root: Path, *, filename: str = USAGE_PROFILE_FILE,
) -> dict[str, Any]:
    path = Path(repo_root) / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"corrupt usage profile at {path}: {exc}") from exc


def write_usage_profile(
    repo_root: Path, profile: UsageProfile, *, filename: str = USAGE_PROFILE_FILE,
) -> None:
    rows = {
        t.task: {"avg_calls_per_run": t.avg_calls_per_run,
                 "avg_prompt_tokens": t.avg_prompt_tokens,
                 "avg_completion_tokens": t.avg_completion_tokens,
                 "samples": t.samples}
        for t in profile.tasks.values()
    }
    atomic_write_text(Path(repo_root) / filename, json.dumps(rows, indent=2, sort_keys=True))


def write_consumption(
    repo_root: Path, consumption: dict[str, Any], *, filename: str = CONSUMPTION_FILE,
) -> None:
    atomic_write_text(
        Path(repo_root) / filename, json.dumps(consumption, indent=2, sort_keys=True),
    )
