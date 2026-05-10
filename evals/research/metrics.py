from __future__ import annotations

_REQUIRED_THEMES = (
    "macro", "sector_rotation", "credit", "commodity",
    "geopolitics", "rates", "equity_valuation",
)


def theme_coverage(reports: list[dict]) -> int:
    """Count how many of the 7 required themes have at least one pull."""
    covered = {r.get("theme") for r in reports if r.get("theme")}
    return sum(1 for t in _REQUIRED_THEMES if t in covered)


def ldr_citation_validity(reports: list[dict], sample_size: int = 5) -> float:
    """Sample up to sample_size LDR reports and return fraction with valid citations."""
    ldr = [r for r in reports if r.get("type") == "ldr"]
    if not ldr:
        return 1.0
    sample = ldr[:sample_size]
    valid = sum(1 for r in sample if r.get("citations"))
    return valid / len(sample)
