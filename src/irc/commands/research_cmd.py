from __future__ import annotations
from pathlib import Path
from irc.research.pipeline import run_research_pipeline


_DEFAULT_THEMES: tuple[str, ...] = (
    "us_monetary", "us_fiscal_politics",
    "cn_monetary", "cn_equity_property_policy",
    "geopolitics", "gold_drivers", "holdings_sector",
)


def run_research(repo_root: str) -> int:
    return run_research_pipeline(
        repo_root=Path(repo_root), themes=_DEFAULT_THEMES, time_budget_s=120,
    )
