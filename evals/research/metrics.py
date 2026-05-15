from __future__ import annotations

_REQUIRED_THEMES = (
    "us_monetary", "us_fiscal_politics", "cn_monetary",
    "cn_equity_property_policy", "geopolitics", "gold_drivers", "holdings_sector",
)


def theme_coverage(themes: list[dict]) -> int:
    """Count how many of the 7 required themes appear in the status themes list."""
    covered = {r.get("theme") for r in themes if r.get("theme")}
    return sum(1 for theme in _REQUIRED_THEMES if theme in covered)


def research_success_rate(themes: list[dict]) -> float:
    """Fraction of themes that completed without failure_reason."""
    if not themes:
        return 1.0
    ok = sum(1 for r in themes if not r.get("failure_reason"))
    return ok / len(themes)


def research_citation_validity(themes: list[dict]) -> float:
    """Fraction of successful themes that have at least one citation."""
    successful = [r for r in themes if not r.get("failure_reason")]
    if not successful:
        return 1.0
    ok = sum(1 for r in successful if int(r.get("citation_count") or 0) > 0)
    return ok / len(successful)


def research_failure_visibility(themes: list[dict]) -> float:
    """Fraction of failed themes that have a non-empty failure_reason string."""
    failed = [r for r in themes if r.get("failure_reason")]
    if not failed:
        return 1.0
    visible = sum(1 for r in failed if str(r.get("failure_reason", "")).strip())
    return visible / len(failed)
