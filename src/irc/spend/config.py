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
