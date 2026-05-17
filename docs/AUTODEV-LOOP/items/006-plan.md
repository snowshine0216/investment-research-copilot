# Item 006 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/006-spec.md`. Base branch: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-006-news-cause-codes`.

**Goal:** Replace the single `missing_recent_news` evidence-gap code with three typed codes (`news_search_empty`, `news_llm_failed`, `news_stage_skipped`) so operators can act on the actual cause.

**Architecture:** Replace `_theme_report_usable() -> bool` with `_classify_theme_report() -> Literal["usable", "search_empty", "llm_failed"]`. The two emission sites in `thesis_evidence.py` and the one in `states.py` switch on the classifier output (plus the `is None` check) to choose the right code.

---

## Task 1: Add the classifier in `thesis_evidence.py`

**Files:** `src/irc/opportunity/thesis_evidence.py:120-121`

### Step 1.1: Write the failing test
- [ ] Add to `tests/opportunity/test_thesis_evidence.py`:

```python
from irc.opportunity.thesis_evidence import _classify_theme_report
from irc.research.theme_research import ThemeReport


def _r(failure_reason: str = "", report_md: str = "body") -> ThemeReport:
    return ThemeReport(theme="t", query="q", locale="en",
                       report_md=report_md, citations=[],
                       failure_reason=failure_reason)


def test_classify_usable_report():
    assert _classify_theme_report(_r()) == "usable"


def test_classify_search_empty():
    assert _classify_theme_report(_r(failure_reason="no sources to synthesize from")) == "search_empty"


def test_classify_search_empty_via_provider_no_results():
    # bocha/tavily/brave emit "no results", dispatch may forward this verbatim
    assert _classify_theme_report(_r(failure_reason="bocha: no results")) == "search_empty"


def test_classify_llm_failed_on_arbitrary_exception_text():
    assert _classify_theme_report(_r(failure_reason="ChatCompletionError: 429 rate limit")) == "llm_failed"


def test_classify_llm_failed_on_unrecognized_failure():
    # Any failure_reason that doesn't match the search-empty pattern is treated as LLM/synth-side
    assert _classify_theme_report(_r(failure_reason="something else")) == "llm_failed"


def test_classify_treats_empty_body_with_no_failure_as_search_empty():
    # ThemeReport with empty report_md but no failure_reason — only happens when
    # the synthesizer returned an empty string for an unknown reason; treat as
    # search-empty (closer to user-actionable than llm_failed).
    assert _classify_theme_report(_r(report_md="")) == "search_empty"
```

### Step 1.2: Run test, expect failure
- [ ] Run: `uv run pytest tests/opportunity/test_thesis_evidence.py -k classify_theme_report -v`
- [ ] Expected: 6 FAILs (function not defined).

### Step 1.3: Implement the classifier
- [ ] In `src/irc/opportunity/thesis_evidence.py`, replace the `_theme_report_usable` block (lines 120-121) with:

```python
# Substring patterns that indicate a search-side failure (zero hits, provider
# unavailable). Anything else with a failure_reason is treated as LLM/synth side.
# Pattern-match is intentionally permissive — failure_reasons are free-text
# concatenations from providers, dispatch, and synthesize.py.
_SEARCH_EMPTY_PATTERNS: tuple[str, ...] = (
    "no sources to synthesize from",
    "no results",
    "missing 'results'",
    "missing 'webPages",
)


def _classify_theme_report(report: ThemeReport | None) -> str:
    """Classify a ThemeReport into one of:
      - "usable": has body and no failure_reason.
      - "search_empty": search returned zero/empty results.
      - "llm_failed": LLM synthesis raised, or any other non-search failure.

    Returns "search_empty" if the report has an empty body with no failure_reason
    (treat as user-actionable rather than internal error).
    Does NOT cover the report-is-None case — that's "stage_skipped" and the
    caller checks for it before classifying.
    """
    if report is None:
        # Defensive — callers should check is-None first. Treat as stage_skipped.
        return "stage_skipped"
    reason = (report.failure_reason or "").lower()
    if reason:
        for pat in _SEARCH_EMPTY_PATTERNS:
            if pat in reason:
                return "search_empty"
        return "llm_failed"
    if not report.report_md or not report.report_md.strip():
        return "search_empty"
    return "usable"


def _theme_report_usable(report: ThemeReport | None) -> bool:
    """Back-compat shim: True iff classifier says 'usable'."""
    return _classify_theme_report(report) == "usable"
```

### Step 1.4: Run tests
- [ ] Run: `uv run pytest tests/opportunity/test_thesis_evidence.py -v`
- [ ] Expected: new 6 PASS, all existing tests still PASS (the shim preserves prior behavior).

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/opportunity/thesis_evidence.py tests/opportunity/test_thesis_evidence.py
git commit -m "feat(opportunity): _classify_theme_report distinguishes search_empty vs llm_failed"
```

---

## Task 2: Emit the three typed codes at the two `missing_recent_news` sites

**Files:** `src/irc/opportunity/thesis_evidence.py:221-222`, `src/irc/opportunity/states.py:330`

### Step 2.1: Write the failing test
- [ ] Add to `tests/opportunity/test_thesis_evidence.py`:

```python
from irc.opportunity.thesis_evidence import derive_thesis_from_evidence


def test_news_stage_skipped_when_theme_report_is_none():
    _, _, _, gaps = derive_thesis_from_evidence(None, None, asset_class="cn_etf")
    assert "news_stage_skipped" in gaps
    assert "missing_recent_news" not in gaps


def test_news_search_empty_when_no_sources():
    r = ThemeReport(theme="t", query="q", locale="en", report_md="", citations=[],
                    failure_reason="no sources to synthesize from")
    _, _, _, gaps = derive_thesis_from_evidence(None, r, asset_class="cn_etf")
    assert "news_search_empty" in gaps
    assert "missing_recent_news" not in gaps


def test_news_llm_failed_on_synth_exception():
    r = ThemeReport(theme="t", query="q", locale="en", report_md="", citations=[],
                    failure_reason="429 rate limit")
    _, _, _, gaps = derive_thesis_from_evidence(None, r, asset_class="cn_etf")
    assert "news_llm_failed" in gaps
    assert "missing_recent_news" not in gaps
```

### Step 2.2: Run tests, expect failure
- [ ] Run: `uv run pytest tests/opportunity/test_thesis_evidence.py -k "news_stage_skipped or news_search_empty or news_llm_failed" -v`
- [ ] Expected: 3 FAILs — code still emits `missing_recent_news`.

### Step 2.3: Replace the emission at `thesis_evidence.py:221-222`
- [ ] In `derive_thesis_from_evidence`, find the block:

```python
    if not _theme_report_usable(theme_report):
        gaps.append("missing_recent_news")
```

Replace with:

```python
    if theme_report is None:
        gaps.append("news_stage_skipped")
    else:
        news_status = _classify_theme_report(theme_report)
        if news_status == "search_empty":
            gaps.append("news_search_empty")
        elif news_status == "llm_failed":
            gaps.append("news_llm_failed")
        # else 'usable' → no gap added
```

### Step 2.4: Replace the emission at `states.py:330`
- [ ] In `src/irc/opportunity/states.py`, find the block (around line 330):

```python
        refined = _refined_table_gap(inp.asset_class)
        legacy = ("missing_constituent_snapshot", "missing_recent_news")
        thesis_gaps = legacy + ((refined,) if refined is not None else ())
```

Replace with:

```python
        refined = _refined_table_gap(inp.asset_class)
        # Table-fallback path runs only when neither snapshot nor theme_report
        # was provided, so the news side is unambiguously stage_skipped.
        legacy = ("missing_constituent_snapshot", "news_stage_skipped")
        thesis_gaps = legacy + ((refined,) if refined is not None else ())
```

### Step 2.5: Run tests
- [ ] Run: `uv run pytest tests/opportunity/ -v`
- [ ] Expected: new tests PASS; existing tests should also PASS but if any assert on the literal `"missing_recent_news"` they need updating to the new codes. Update those assertions case-by-case.

### Step 2.6: Verify no consumer still grep'd for `missing_recent_news`
- [ ] Run: `grep -rn '"missing_recent_news"' src/ tests/`
- [ ] Expected: zero hits in src/. If any hits in tests/ surface, update those tests to assert against the appropriate typed code.

### Step 2.7: Commit
- [ ] Run:

```bash
git add src/irc/opportunity/thesis_evidence.py src/irc/opportunity/states.py tests/opportunity/
git commit -m "feat(opportunity): emit news_stage_skipped / news_search_empty / news_llm_failed"
```

---

## Task 3: Full-suite verification

### Step 3.1: Run all tests
- [ ] Run: `uv run pytest -q -x`
- [ ] Expected: all PASS.

### Step 3.2: Ruff
- [ ] Run: `uv run ruff check src/irc/opportunity/ tests/opportunity/`
- [ ] Expected: no new findings.
