# 001 — Theme research query relevance

## Why

`data/research/holdings_sector.md` is filled with results about "用户研究
软件行业" (User Research Software industry) — the query token "用户研究"
matched literal industry-report pages on `chinabgao.com`. The current
generic query `"用户组合涉及行业的最新新闻和研报要点"` provides no concrete
hook to the actual portfolio holdings.

The adversarial review (§A1) demands: query terms must reflect the
instrument's `lookthrough_target`, sector code, or named holdings — not
its display name; AND a relevance filter must reject sources whose
extracted entities don't intersect.

## What changes

1. In `src/irc/research/theme_research.py`:
   - Add a `holdings_context` parameter (or per-theme override) so the
     query for `holdings_sector` is built from concrete sector codes and
     fund names of the user's actual holdings, e.g.

         "近期 黄金/医疗保健/沪深300/标普500/红利 等行业的政策与基本面要点"

   - Source of `holdings_context`: the orchestrator pipeline already
     knows the user's holdings (from `inputs/account.yaml` and the
     opportunity_report). Pass a `(sector_codes, lookthrough_targets)`
     tuple into the research runner.
2. Add a relevance filter (pure function) in a new
   `src/irc/research/relevance.py`:

```python
def source_is_relevant(
    citation: Citation,
    keywords: frozenset[str],   # sector codes, lookthrough names, fund houses
) -> bool:
    """A source is relevant if its title or summary mentions any of the
    user's holdings, sectors, or fund managers (case-insensitive, both
    locales). Returns True when keywords is empty (no opinion)."""
```

3. In `theme_research.py`, after fetching citations for
   `holdings_sector` (and any theme that loads `holdings_context`),
   filter out citations failing `source_is_relevant`. If the filter
   drops every citation, set `failure_reason="no relevant sources after
   filter"` so the quality gate (item 003) can downgrade.

## Acceptance criteria

- `holdings_sector` query is derived from concrete sector codes / holding
  names, not the static placeholder.
- `data/research/holdings_sector.md` from a re-run contains only
  citations whose title or summary mentions a user holding / sector
  code / fund manager — or the report is flagged as failed.
- New unit tests cover `source_is_relevant` positive / negative paths
  and the empty-keywords pass-through.

## Tests to add

- `tests/research/test_relevance.py`: title contains "医疗保健" with
  keywords {"healthcare", "医疗"} → True; title is about traffic sensors
  → False; empty keywords → True (no opinion).
- `tests/research/test_holdings_query.py`: passing a holdings_context
  with `{"healthcare", "gold"}` builds a query string that mentions both.
