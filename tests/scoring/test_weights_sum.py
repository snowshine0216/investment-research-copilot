"""Regression test: production scoring weights must sum to 1.0.

Adversarial-review item 011 (2026-05-19): the scoring weights were
rebalanced for long-horizon DCA. This guards against accidental
drift where weights stop summing to 1.0 (which silently rescales every
composite score and breaks the action thresholds).
"""
from __future__ import annotations

from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
# Source of truth lives in the template tree; the runtime config/ is a
# user-specific copy emitted by `irc init` and is gitignored.
_SCORING_YAML = _REPO_ROOT / "src" / "irc" / "templates" / "config" / "scoring.yaml"


def test_production_weights_sum_to_one() -> None:
    cfg = yaml.safe_load(_SCORING_YAML.read_text(encoding="utf-8"))
    weights = cfg["factor_weights"]
    total = sum(float(w) for w in weights.values())
    # Use exact equality on a small denominator-of-100 fraction.
    assert abs(total - 1.0) < 1e-9, (
        f"factor_weights sum to {total}, not 1.0 — adjust before merging"
    )


def test_valuation_weight_floor_for_dca() -> None:
    cfg = yaml.safe_load(_SCORING_YAML.read_text(encoding="utf-8"))
    weights = cfg["factor_weights"]
    assert float(weights["valuation_cost"]) >= 0.25, (
        "DCA long-horizon strategy requires valuation_cost >= 0.25 "
        "(see 2026-05-19-adversarial-fixes/items/011-spec.md)"
    )


def test_thesis_news_weight_ceiling() -> None:
    cfg = yaml.safe_load(_SCORING_YAML.read_text(encoding="utf-8"))
    weights = cfg["factor_weights"]
    assert float(weights["thesis_news"]) <= 0.10, (
        "thesis_news weight must stay <= 0.10 until the news relevance "
        "pipeline is trusted (see items/001-spec.md, items/002-spec.md)"
    )


def test_weights_version_is_dated() -> None:
    cfg = yaml.safe_load(_SCORING_YAML.read_text(encoding="utf-8"))
    assert cfg["weights_version"].startswith("2026-05-19-")
