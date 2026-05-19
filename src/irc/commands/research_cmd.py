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


# Asset-class → human keywords used to build the holdings_sector query
# and to filter its citations. Adversarial review §A1 demands the query
# include concrete hooks (sector codes, fund-house names) so the
# search engine cannot fall back to tokenizing ``用户``/``研究``.
_ASSET_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gold":           ("黄金", "gold", "央行购金", "real yield"),
    "cn_equity_fund": ("沪深300", "中证", "A股", "股票基金"),
    "cn_etf":         ("中证", "沪深300", "ETF"),
    "cn_bond_fund":   ("国债", "信用债", "债基", "10Y", "CGB"),
    "hk_etf":         ("港股", "恒生", "Hang Seng"),
    "us_etf":         ("标普500", "纳斯达克100", "S&P 500", "Nasdaq 100"),
}


def _derive_holdings_keywords(bundle) -> tuple[str, ...]:
    """Collect keywords from the user's preferences asset-class targets.

    Anything with a non-zero target weight contributes its keywords. We
    don't read the account.yaml holdings list directly — preferences
    captures the strategic target which is what research should track.
    """
    targets = getattr(bundle, "preferences", None)
    if targets is None:
        return ()
    cls_targets = getattr(targets, "asset_class_targets", {})
    seen: list[str] = []
    for cls, t in cls_targets.items():
        center = float(getattr(t, "center", 0.0) or 0.0)
        if center <= 0:
            continue
        for kw in _ASSET_CLASS_KEYWORDS.get(str(cls), ()):
            if kw not in seen:
                seen.append(kw)
    return tuple(seen)


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
    holdings_keywords = _derive_holdings_keywords(bundle)
    return run_research_pipeline(
        repo_root=root,
        themes=themes if themes is not None else _DEFAULT_THEMES,
        providers=providers,
        extractor=extractor,
        route=route,
        holdings_keywords=holdings_keywords,
    )
