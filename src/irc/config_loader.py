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
