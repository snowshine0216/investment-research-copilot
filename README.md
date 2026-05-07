# Investment Research Copilot

Weekly research-and-recommendation system for gold + Mainland China funds + Mainland China ETFs + HK ETFs (via QDII proxy) + US ETFs (via QDII proxy). Outputs Markdown research memos with full source provenance.

See `docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md` for the design spec.

## Quick start

```bash
uv sync --all-extras
cp .env.example .env             # then fill DEEPSEEK_API_KEY + OPENROUTER_API_KEY
uv run irc init                  # writes inputs/ + config/ defaults
uv run irc config validate       # checks all YAML
```

## Tests

```bash
uv run pytest
```
