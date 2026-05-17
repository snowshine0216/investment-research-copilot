# Item 006 — Split `missing_recent_news` into typed causes

## Problem

`missing_recent_news` is emitted by `src/irc/opportunity/thesis_evidence.py:120-121, 221-222` whenever a `theme_report` is `None` or unusable. "Unusable" covers three distinct failure modes today, all collapsed into one code:
1. Search provider returned 0 hits (`failure_reason="no_results"`).
2. LLM synthesis failed (`failure_reason="llm_error"`).
3. Research stage didn't run at all (`theme_report is None`, e.g. `RESEARCH_ENABLED=false`).

Operators can't act on a single code — "is it the search budget, the LLM credentials, or did I forget to enable the stage?" requires reading logs.

## Approach

Replace `missing_recent_news` with three distinct codes:
- `news_search_empty` — theme_report exists but `failure_reason` indicates the search returned no usable results.
- `news_llm_failed` — theme_report exists but `failure_reason` indicates LLM synthesis failed.
- `news_stage_skipped` — theme_report is `None` (the research stage didn't run for this theme).

The existing `_theme_report_usable()` helper at `thesis_evidence.py:120-121` becomes a classifier returning one of `{usable, search_empty, llm_failed}`. The call site at `thesis_evidence.py:221-222` and `states.py:306` chooses the appropriate code based on the classifier output plus a `is_none` check.

## Acceptance criteria

- `evidence_gaps` no longer contains `"missing_recent_news"`. Instead it contains exactly one of `news_search_empty` / `news_llm_failed` / `news_stage_skipped`.
- The failure_reason taxonomy in `research/theme_research.py` is documented (a module-level constant tuple or enum so the classifier doesn't string-match on free text).
- A test verifies each of the three cases produces the right code.

## Files (expected)

- `src/irc/research/theme_research.py` — define the failure_reason taxonomy as named constants (if not already).
- `src/irc/opportunity/thesis_evidence.py:120-121, 221-222` — replace `_theme_report_usable` returning bool with a classifier returning a typed code.
- `src/irc/opportunity/states.py:306` — update to use the classifier.
- `tests/opportunity/` — add regression tests for all three code paths.

## Non-goals

- Changing the research-stage retry behavior.
- Refactoring the search-provider abstraction.
- Adding new failure_reasons beyond what already exists.
