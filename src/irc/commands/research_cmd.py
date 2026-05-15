from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv

from irc.config_loader import load_repo_configs
from irc.llm.gateway import resolve_route
from irc.research.pipeline import run_research_pipeline
from irc.research.search.factory import build_extractor, build_providers
from irc.settings import Settings


_DEFAULT_THEMES: tuple[str, ...] = (
    "us_monetary", "us_fiscal_politics",
    "cn_monetary", "cn_equity_property_policy",
    "geopolitics", "gold_drivers", "holdings_sector",
)


def run_research(repo_root: str, themes: tuple[str, ...] | None = None) -> int:
    root = Path(repo_root)
    load_dotenv(root / ".env")
    settings = Settings()
    providers = build_providers(settings)
    if not providers:
        print(
            "ERROR: research cannot run — no search provider keys configured. "
            "Set TAVILY_API_KEY, BRAVE_API_KEY, or BOCHA_API_KEY in .env."
        )
        return 2
    extractor = build_extractor(settings)
    bundle = load_repo_configs(root)
    route = resolve_route("research_synth", bundle.llm)
    return run_research_pipeline(
        repo_root=root,
        themes=themes if themes is not None else _DEFAULT_THEMES,
        providers=providers,
        extractor=extractor,
        route=route,
    )
