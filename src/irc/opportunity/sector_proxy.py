from __future__ import annotations


_THEME_TO_INDEX_PROXY: dict[str, str] = {
    # Sector themes that have a clean broad-index proxy in _TARGET_REGISTRY.
    # Only include mappings where the proxy genuinely represents the theme.
    "dividend": "中证红利",
    "broad": "沪深300",
    "soe": "沪深300",  # SOE reform funds tend to track broad indices
}


def proxy_target_for_theme(theme: str | None) -> str | None:
    """Return the proxy snapshot target name for a sector theme, or None if unmapped."""
    if not theme:
        return None
    return _THEME_TO_INDEX_PROXY.get(theme)
