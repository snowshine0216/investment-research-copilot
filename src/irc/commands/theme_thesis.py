from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_VALID_VALUES: frozenset[str] = frozenset(
    {"intact", "under_pressure", "falsified", "evidence_insufficient"}
)


def load_theme_thesis(repo_root: Path) -> dict[str, str]:
    """Load `config/opportunity/theme_thesis.yaml`.

    Missing file => empty dict (everything degrades to evidence_insufficient).
    Unknown state values raise ValueError so the user notices typos.
    """
    path = repo_root / "config" / "opportunity" / "theme_thesis.yaml"
    if not path.exists():
        return {}
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    themes = raw.get("themes") or {}
    if not isinstance(themes, dict):
        raise ValueError(
            f"{path}: 'themes' must be a mapping of theme -> state"
        )
    out: dict[str, str] = {}
    for theme, state in themes.items():
        if state not in _VALID_VALUES:
            raise ValueError(
                f"{path}: theme '{theme}' has invalid state '{state}'. "
                f"Valid values: {sorted(_VALID_VALUES)}"
            )
        out[str(theme)] = str(state)
    return out
