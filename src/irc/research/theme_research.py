from __future__ import annotations
from dataclasses import dataclass
from irc.research.ldr_client import run_research, LDRCitation


@dataclass(frozen=True)
class ThemeReport:
    theme: str
    query: str
    report_md: str
    citations: list[LDRCitation]
    failure_reason: str


_THEME_QUERIES: dict[str, str] = {
    "us_monetary":               "What did the Fed say or do this past week? Cite primary sources.",
    "us_fiscal_politics":        "Recent US fiscal / political news affecting markets, with citations.",
    "cn_monetary":                "PBoC actions and statements this week with primary sources.",
    "cn_equity_property_policy": "China equity / property regulatory news with primary sources.",
    "geopolitics":                "Material geopolitical events (Russia-Ukraine, Middle East, Taiwan) this week with primary sources.",
    "gold_drivers":               "Recent moves in real yields, USD, central bank gold purchases, ETF flows; cite primary sources.",
    "holdings_sector":            "News for sectors held in user portfolio; cite primary sources.",
}


def build_theme_reports(themes: tuple[str, ...], time_budget_s: int = 90) -> list[ThemeReport]:
    from irc.observability import progress_iter

    out: list[ThemeReport] = []
    for theme in progress_iter(themes, "research", total=len(themes)):
        query = _THEME_QUERIES.get(theme, f"Research summary for {theme}")
        res = run_research(query=query, time_budget_s=time_budget_s)
        out.append(ThemeReport(
            theme=theme, query=query,
            report_md=res.report_md, citations=res.citations,
            failure_reason=res.failure_reason,
        ))
    return out
