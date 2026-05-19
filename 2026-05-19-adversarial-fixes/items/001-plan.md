# 001 — Plan

## Steps

1. New module `src/irc/research/relevance.py`:
   - `normalize_keywords(raw)` → frozenset (strip / lowercase / drop empty).
   - `source_is_relevant(citation, keywords)` → bool (substring match
     against title + URL; empty keywords passes through).
   - `filter_relevant_citations(citations, keywords)` → tuple.
2. `src/irc/research/theme_research.py`:
   - Add `build_holdings_query(keywords)` — builds the concrete
     holdings_sector query from named assets.
   - Add `_query_for_with_context(theme, holdings_keywords)`.
   - Extend `build_theme_reports` with `holdings_keywords: tuple[str, ...]`.
   - After building the holdings_sector report, apply the relevance
     filter. If filter drops everything, mark the report failed so the
     quality gate (item 003) sees the degradation.
3. `src/irc/research/pipeline.py`:
   - Thread `holdings_keywords` through `run_research_pipeline`.
4. `src/irc/commands/research_cmd.py`:
   - Add `_ASSET_CLASS_KEYWORDS` table.
   - Add `_derive_holdings_keywords(bundle)` from preferences.
5. Tests:
   - `tests/research/test_relevance.py`
   - `tests/research/test_holdings_query.py`
