from __future__ import annotations

from pathlib import Path

import yaml

from irc.narrative.schemas import BasketStock, NarrativeBasket


def _narratives_dir(repo_root: Path) -> Path:
    return repo_root / "config" / "narratives"


def available_narratives(repo_root: Path) -> tuple[str, ...]:
    d = _narratives_dir(repo_root)
    if not d.exists():
        return ()
    return tuple(sorted(p.stem for p in d.glob("*.yaml")))


def _parse_basket(raw: list) -> tuple[BasketStock, ...]:
    if not isinstance(raw, list):
        raise ValueError("basket must be a list of {symbol, name_cn, metal}")
    return tuple(
        BasketStock(
            symbol=str(item["symbol"]),
            name_cn=str(item["name_cn"]),
            metal=str(item.get("metal", "")),
        )
        for item in raw
    )


def load_narrative_basket(name: str, repo_root: Path) -> NarrativeBasket:
    """I/O edge: read + validate config/narratives/<name>.yaml -> NarrativeBasket.

    Missing config raises FileNotFoundError naming the available narratives."""
    path = _narratives_dir(repo_root) / f"{name}.yaml"
    if not path.exists():
        avail = ", ".join(available_narratives(repo_root)) or "(none)"
        raise FileNotFoundError(
            f"narrative config not found: {path}. Available: {avail}"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    thresholds = raw.get("thresholds", {})
    return NarrativeBasket(
        narrative_id=str(raw["narrative_id"]),
        display_name_cn=str(raw.get("display_name_cn", "")),
        display_name_en=str(raw.get("display_name_en", "")),
        thesis_cn=str(raw.get("thesis_cn", "")),
        basket=_parse_basket(raw.get("basket", [])),
        industries_sw=tuple(str(x) for x in raw.get("industries_sw", [])),
        min_basket_weight_pct=float(thresholds.get("min_basket_weight_pct", 15.0)),
        min_overlap_count=int(thresholds.get("min_overlap_count", 2)),
        top_n=int(raw.get("top_n", 15)),
    )
