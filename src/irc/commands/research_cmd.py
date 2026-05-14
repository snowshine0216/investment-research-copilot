from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from irc.research.pipeline import run_research_pipeline


_DEFAULT_THEMES: tuple[str, ...] = (
    "us_monetary", "us_fiscal_politics",
    "cn_monetary", "cn_equity_property_policy",
    "geopolitics", "gold_drivers", "holdings_sector",
)
_DEFAULT_TIMEOUT_S = 300


def run_research(repo_root: str) -> int:
    root = Path(repo_root)
    load_dotenv(root / ".env")
    time_budget_s = int(os.environ.get("LDR_TIMEOUT_S", _DEFAULT_TIMEOUT_S))
    return run_research_pipeline(
        repo_root=root, themes=_DEFAULT_THEMES, time_budget_s=time_budget_s,
    )
