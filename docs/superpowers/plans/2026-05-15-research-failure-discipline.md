# Research Failure Discipline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the pipeline from producing decision-grade output when research evidence is silently broken. Make every eval report FAIL when its input is missing, halt the pipeline on critical research failures, surface every upstream error to console regardless of `DEBUG`, and add `freshness_days` so time-sensitive theme queries return dated news instead of homepages.

**Architecture:**
1. Replace the "missing input → emit PASS" path in every eval runner with a shared `missing_input_report(...)` helper that emits `overall: FAIL` with exit code 2.
2. Promote `run_research` from "always returns 0" to "returns 2 when research is unusable" using a new `research_quality_gate` (locale coverage, success rate, citation validity, provider availability), then let `run_cmd._runners_map["research"]` halt the pipeline like every other stage.
3. Plumb `freshness_days` from `theme_research` configuration through `provider_results` → each provider's existing-but-unused freshness param.
4. Convert every silently-swallowed exception in `search/dispatch.py` and `search/jina_reader.py` into a `_log.warning(...)` call so failures surface at the default INFO threshold (current default already shows WARNING, but the failures never reach the logger today).

**Tech Stack:** Python 3.13, pydantic, rich, pytest, ruff. No new dependencies.

---

## File Structure

**New files:**
- `evals/_shared/missing_input.py` — single source of truth for "input missing → FAIL" reports.
- `src/irc/research/quality_gate.py` — pure function that decides whether research output is usable.
- `tests/evals/test_missing_input_helper.py`
- `tests/research/test_quality_gate.py`
- `tests/research/test_dispatch_logging.py`

**Modified files (eval runners — same surgical change each):**
- `evals/research/runner.py:18-36` — swap `_pass_report()` for `missing_input_report(...)`, return 2.
- `evals/allocation/runner.py:26-30`
- `evals/architecture/runner.py:18-22`
- `evals/discovery/runner.py:20-24`
- `evals/gold_score/runner.py:18-22`
- `evals/memo/runner.py:24-28`
- `evals/news/runner.py:18-22`
- `evals/opportunity/runner.py:65-68`
- `evals/queries/runner.py:22-26`
- `evals/scoring/runner.py:52-56`
- `evals/trade_plan/runner.py:22-26`
- `evals/triggers/runner.py:13-17` — entire body is unconditional PASS today; rewrite.
- Delete `_pass_report()` from each runner once unused.

**Modified files (research pipeline & dispatch):**
- `src/irc/research/theme_research.py:73, 100-115` — accept and forward `freshness_days`; defaults per-theme.
- `src/irc/research/pipeline.py` — return non-zero when `quality_gate` fails.
- `src/irc/research/search/dispatch.py:55, 89, 122-128` — log failures via `_log.warning(...)`.
- `src/irc/research/search/jina_reader.py:30-67` — log failures via `_log.warning(...)`.
- `src/irc/research/persistence.py:23-29` — include `overall` derived from quality_gate (not just "warn if any failure").
- `src/irc/commands/research_cmd.py` — call new gate, propagate non-zero exit.
- `src/irc/commands/run_cmd.py:34-37` — emit halt message that references the failed quality_gate reasons.
- `.env.example` — drop dead `LDR_*` keys (already removed from docs).

---

## Task 1: Shared "missing input → FAIL" helper

**Files:**
- Create: `evals/_shared/missing_input.py`
- Test: `tests/evals/test_missing_input_helper.py`

- [ ] **Step 1: Write failing test**

```python
# tests/evals/test_missing_input_helper.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)


def test_missing_input_report_marks_fail_with_reason():
    report = missing_input_report(
        stage="research",
        reason="data/research/research_status.json is missing",
        based_on_path="data/research/research_status.json",
    )
    assert report.overall == "FAIL"
    assert report.stage == "research"
    assert report.based_on == ["data/research/research_status.json"]
    assert report.metrics == []
    # ran_at must be ISO-8601 in +08:00 (Beijing) to match other runners.
    assert report.ran_at.endswith("+08:00")


def test_eval_rc_fail_is_two_to_match_existing_convention():
    # Existing runners return 2 for FAIL, 1 for WARN, 0 for PASS.
    assert EVAL_RC_FAIL == 2


def test_write_missing_input_report_emits_json_with_fail_overall(tmp_path: Path):
    report = missing_input_report(
        stage="triggers",
        reason="trigger watch data unavailable",
        based_on_path=None,
    )
    out = write_missing_input_report(tmp_path, report, date_str="2026-05-15")
    assert out.exists()
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert body["stage"] == "triggers"
    # based_on may be empty list, never absent.
    assert body["based_on"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_missing_input_helper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals._shared.missing_input'`

- [ ] **Step 3: Implement the helper**

```python
# evals/_shared/missing_input.py
"""Shared 'eval input missing' report builder.

Replaces the historical 'missing input → PASS' pattern in every runner.
A missing input file means the upstream stage did not run (or crashed before
writing). Treating that as PASS lets broken pipelines look healthy. We treat
it as FAIL with exit code 2 so the CLI returns non-zero and dashboards turn red.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals._shared.report_schema import StageReport, report_to_dict
from irc.io_utils import atomic_write_text


EVAL_RC_PASS = 0
EVAL_RC_WARN = 1
EVAL_RC_FAIL = 2

_TZ = timezone(timedelta(hours=8))


def missing_input_report(
    *,
    stage: str,
    reason: str,
    based_on_path: str | None,
) -> StageReport:
    """Build a FAIL StageReport indicating the eval's input was absent.

    `based_on_path` is the file the eval would have read. We include it in
    `based_on` even when missing so reviewers can see what was expected.
    """
    based_on = [based_on_path] if based_on_path else []
    return StageReport(
        stage=stage,
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=based_on,
        metrics=[],
        overall="FAIL",
        notes=reason,
    )


def write_missing_input_report(
    repo_root: Path, report: StageReport, *, date_str: str | None = None,
) -> Path:
    """Write the FAIL report under outputs/<date>/evals/<stage>/report.json.

    `date_str` defaults to today in Beijing time; tests override it.
    """
    if date_str is None:
        date_str = datetime.now(_TZ).date().isoformat()
    out_dir = repo_root / "outputs" / date_str / "evals" / report.stage
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "report.json"
    atomic_write_text(
        out, json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)
    )
    return out
```

- [ ] **Step 4: Check whether `notes` field exists on StageReport; add if not**

Run: `grep -n "notes" evals/_shared/report_schema.py`

If `notes` is not on `StageReport`, add it as an optional empty string:

```python
# evals/_shared/report_schema.py — only the relevant lines shown
@dataclass(frozen=True)
class StageReport:
    stage: str
    ran_at: str
    based_on: list[str]
    metrics: list[MetricReport]
    overall: str
    notes: str = ""  # add this line if missing
    config_versions: dict[str, str] = field(default_factory=dict)
```

Make sure `report_to_dict` includes `notes` in its output dict. If `report_to_dict` builds the dict explicitly, add `"notes": r.notes`. If it uses `asdict(...)`, no change needed.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_missing_input_helper.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add evals/_shared/missing_input.py tests/evals/test_missing_input_helper.py evals/_shared/report_schema.py
git commit -m "feat(evals): add missing_input_report helper that emits FAIL instead of PASS"
```

---

## Task 2: Swap research runner to use the FAIL helper

**Files:**
- Modify: `evals/research/runner.py:18-36, 87-91`
- Test: `tests/evals/test_research_runner.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/evals/test_research_runner.py
from __future__ import annotations

import json
from pathlib import Path

from evals.research.runner import run


def test_research_runner_fails_when_status_file_missing(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2, "missing input must be FAIL (rc=2), not PASS"
    report_path = next((tmp_path / "outputs").rglob("evals/research/report.json"))
    body = json.loads(report_path.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert body["based_on"] == ["data/research/research_status.json"]


def test_research_runner_fails_when_status_file_unreadable(tmp_path: Path):
    p = tmp_path / "data" / "research"
    p.mkdir(parents=True)
    (p / "research_status.json").write_text("this is not json", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == 2
    report_path = next((tmp_path / "outputs").rglob("evals/research/report.json"))
    body = json.loads(report_path.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert "unreadable" in body["notes"]


def test_research_runner_returns_pass_when_themes_all_succeed(tmp_path: Path):
    p = tmp_path / "data" / "research"
    p.mkdir(parents=True)
    themes = [
        {"theme": t, "citation_count": 4, "failure_reason": ""}
        for t in (
            "us_monetary", "us_fiscal_politics", "cn_monetary",
            "cn_equity_property_policy", "geopolitics", "gold_drivers", "holdings_sector",
        )
    ]
    (p / "research_status.json").write_text(json.dumps({"themes": themes}), encoding="utf-8")
    rc = run(tmp_path)
    assert rc == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_research_runner.py -v`
Expected: 2 failures — the missing-input tests assert rc==2 but current code returns 0.

- [ ] **Step 3: Modify runner to use missing_input_report**

Edit `evals/research/runner.py`. Replace lines 18-36 (the two `if not status_file.exists()` / `except` blocks that build `_pass_report`) with:

```python
def run(repo_root: Path) -> int:
    status_file = repo_root / "data" / "research" / "research_status.json"
    if not status_file.exists():
        report = missing_input_report(
            stage="research",
            reason="data/research/research_status.json is missing — research stage did not run",
            based_on_path="data/research/research_status.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"research eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    try:
        body = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report = missing_input_report(
            stage="research",
            reason=f"research_status.json unreadable: {exc}",
            based_on_path="data/research/research_status.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"research eval: {report.overall} (status file unreadable)")
        return EVAL_RC_FAIL
    themes: list[dict] = body.get("themes", [])
    # … rest of function unchanged …
```

Update the top imports:

```python
from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)
```

Delete the local `_pass_report` definition at the bottom of the file (lines 87-91).

- [ ] **Step 4: Run all research eval tests**

Run: `uv run pytest tests/evals/test_research_runner.py tests/evals/test_research_metrics.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add evals/research/runner.py tests/evals/test_research_runner.py
git commit -m "fix(evals/research): emit FAIL with rc=2 when status file missing or unreadable"
```

---

## Task 3: Apply the same fix to the other ten input-driven eval runners

For each runner below, do exactly the same 4-step swap. Steps 1-3 are identical to Task 2; only the `stage`, `based_on_path`, and reason string change.

**Runners to update (with their status-file path):**

| Runner | Input file (the `based_on_path`) |
|---|---|
| `evals/allocation/runner.py` | `outputs/allocation/allocation.json` |
| `evals/architecture/runner.py` | (output dir, no single file — see Step 3 below) |
| `evals/discovery/runner.py` | `outputs/discovery/watchlist.json` |
| `evals/gold_score/runner.py` | `outputs/gold_score/gold_score.json` |
| `evals/memo/runner.py` | `outputs/memo/memo.md` |
| `evals/news/runner.py` | `outputs/news/articles.json` |
| `evals/opportunity/runner.py` | `outputs/<date>/opportunity_report.json` |
| `evals/queries/runner.py` | `outputs/queries/queries.json` |
| `evals/scoring/runner.py` | `outputs/<date>/scoring.json` |
| `evals/trade_plan/runner.py` | `outputs/trade_plan/trades.json` |

- [ ] **Step 1: Write a failing test per runner**

For each runner, add to its existing test file (or create one under `tests/evals/test_<stage>_runner.py`):

```python
# Example template — fill in <STAGE> and <PATH> per runner
from pathlib import Path
import json
from evals.<STAGE>.runner import run


def test_<STAGE>_runner_fails_when_input_missing(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2
    report = next((tmp_path / "outputs").rglob("evals/<STAGE>/report.json"))
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
```

- [ ] **Step 2: Run new tests, confirm they fail with rc=0**

Run: `uv run pytest tests/evals/ -v -k "fails_when_input_missing"`
Expected: 10 failures (all currently return 0).

- [ ] **Step 3: Patch each runner**

In each runner, replace the `if not <input>.exists(): report = _pass_report(); … return 0` block with the same `missing_input_report(...)` pattern from Task 2, then delete `_pass_report()` once unused.

**Special case — `evals/architecture/runner.py`:** the check is `if not out_dir.exists()`, where `out_dir = repo_root / "outputs"`. Use:

```python
if not out_dir.exists():
    report = missing_input_report(
        stage="architecture",
        reason="outputs/ directory missing — pipeline has not produced any artifacts",
        based_on_path="outputs/",
    )
    write_missing_input_report(repo_root, report)
    print(f"architecture eval: {report.overall} (no outputs yet)")
    return EVAL_RC_FAIL
```

**Special case — `evals/opportunity/runner.py:65-68`:** missing-input handling is inside `_locate_inputs(...)`; the `if target_dir is None` branch currently prints `f"opportunity eval: PASS (no input file)"` and returns 0. Build the FAIL report there with `based_on_path=None` and stage=`"opportunity"`.

**Special case — `evals/scoring/runner.py`:** `if source is None` is the entry point at line 52. Use the same pattern; `based_on_path` is `"outputs/<date>/scoring.json (or latest)"`.

- [ ] **Step 4: Run full eval test suite**

Run: `uv run pytest tests/evals/ -v`
Expected: all pass, including the 10 new `fails_when_input_missing` tests.

- [ ] **Step 5: Commit**

```bash
git add evals/ tests/evals/
git commit -m "fix(evals): emit FAIL rc=2 when input missing across all stage runners"
```

---

## Task 4: Rewrite the unconditional-PASS `triggers` eval

`evals/triggers/runner.py` currently *always* returns PASS regardless of pipeline state — there is no input check at all. Until we wire real trigger metrics, the eval should FAIL loudly so it cannot mask absent functionality.

**Files:**
- Modify: `evals/triggers/runner.py:11-22`
- Test: `tests/evals/test_triggers_runner.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/evals/test_triggers_runner.py
from __future__ import annotations
import json
from pathlib import Path
from evals.triggers.runner import run


def test_triggers_runner_fails_when_no_trigger_data(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2
    report = next((tmp_path / "outputs").rglob("evals/triggers/report.json"))
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert "not yet implemented" in body["notes"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_triggers_runner.py -v`
Expected: FAIL — current runner returns 0.

- [ ] **Step 3: Rewrite the runner**

Replace `evals/triggers/runner.py` body with:

```python
from __future__ import annotations
from pathlib import Path
from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)


def run(repo_root: Path) -> int:
    # Triggers eval has no metrics implemented yet. Returning PASS would mask
    # missing functionality — fail loudly until the metric module lands.
    report = missing_input_report(
        stage="triggers",
        reason="trigger evaluation not yet implemented; emitting FAIL to avoid masking absent functionality",
        based_on_path=None,
    )
    write_missing_input_report(repo_root, report)
    print(f"triggers eval: {report.overall} (not implemented)")
    return EVAL_RC_FAIL
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/evals/test_triggers_runner.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add evals/triggers/runner.py tests/evals/test_triggers_runner.py
git commit -m "fix(evals/triggers): FAIL until real metrics implemented (was unconditional PASS)"
```

---

## Task 5: Surface every search-provider failure to console

Today, when Bocha returns 403, when Tavily times out, when Jina fails to extract a URL, the failure is captured into a `SearchResult.failure_reason` or `ExtractedPage.failure_reason` string and recorded into `research_status.json`. Nothing is printed at the moment of failure, so the user can't see the bocha quota error until they grep the status file.

**Files:**
- Modify: `src/irc/research/search/dispatch.py:24-67, 70-104, 105-128`
- Modify: `src/irc/research/search/jina_reader.py:30-67`
- Test: `tests/research/test_dispatch_logging.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/research/test_dispatch_logging.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from irc.research.search.dispatch import provider_results, extract_top_pages
from irc.research.search.types import (
    ContentExtractor, ExtractedPage, Locale, SearchHit, SearchProvider, SearchResult,
)


@dataclass
class _StubProvider:
    name: str = "stub"
    locale: Locale = Locale.ZH

    def search(self, query: str, **_: Any) -> SearchResult:
        return SearchResult(
            query=query, locale=self.locale, provider=self.name,
            failure_reason="http 403: quota exhausted",
        )


def test_provider_results_logs_failure_at_warning(caplog):
    caplog.set_level(logging.WARNING, logger="irc.research.search.dispatch")
    out = provider_results("q", Locale.ZH, (_StubProvider(),))
    assert out[0].failure_reason
    # The failure must be visible to the console even when DEBUG=false.
    messages = [r.getMessage() for r in caplog.records]
    assert any("stub" in m and "403" in m for m in messages), messages


class _StubExtractor:
    name: str = "stub"

    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        raise RuntimeError("boom")


def test_extract_top_pages_logs_exceptions_at_warning(caplog):
    caplog.set_level(logging.WARNING, logger="irc.research.search.dispatch")
    hits = (SearchHit(title="t", url="https://x", snippet=""),)
    out = extract_top_pages(hits, _StubExtractor())
    assert out[0].failure_reason.startswith("extractor raised")
    messages = [r.getMessage() for r in caplog.records]
    assert any("https://x" in m and "boom" in m for m in messages), messages
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_dispatch_logging.py -v`
Expected: 2 failures — no log records currently captured.

- [ ] **Step 3: Add logging to dispatch.py**

Edit `src/irc/research/search/dispatch.py`. Add at top:

```python
import logging
_log = logging.getLogger(__name__)
```

In `provider_results`, immediately after appending a failed `SearchResult` (both the `failure_reason`-bearing return from `provider.search` and the exception-catch branch), log it:

```python
def provider_results(
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    *,
    max_results: int = 10,
    freshness_days: int | None = None,
    include_domains: tuple[str, ...] = (),
) -> tuple[SearchResult, ...]:
    out: list[SearchResult] = []
    for provider in providers:
        if provider.locale != locale:
            continue
        try:
            result = provider.search(
                query,
                max_results=max_results,
                freshness_days=freshness_days,
                include_domains=include_domains,
            )
        except Exception as exc:
            _log.warning(
                "search provider %s raised on query %r: %s",
                provider.name, query, exc,
            )
            out.append(SearchResult(
                query=query, locale=locale, provider=provider.name,
                failure_reason=f"provider raised: {exc}",
            ))
            continue
        if result.failure_reason:
            _log.warning(
                "search provider %s failed on query %r: %s",
                provider.name, query, result.failure_reason,
            )
        out.append(result)
    return tuple(out)
```

In `extract_top_pages`, add a `_log.warning` before constructing the failed `ExtractedPage`:

```python
def extract_top_pages(
    hits: tuple[SearchHit, ...],
    extractor: ContentExtractor,
    *,
    top_k: int = 5,
    timeout_s: int = 20,
) -> tuple[ExtractedPage, ...]:
    out: list[ExtractedPage] = []
    for hit in hits[:top_k]:
        try:
            page = extractor.extract(hit.url, timeout_s=timeout_s)
        except Exception as exc:
            _log.warning(
                "extractor %s raised on %s: %s", extractor.name, hit.url, exc,
            )
            page = ExtractedPage(
                url=hit.url, title=hit.title, markdown="",
                fetched_at_iso=datetime.now(tz=timezone.utc).isoformat(),
                failure_reason=f"extractor raised: {exc}",
            )
        if page.failure_reason:
            _log.warning(
                "extractor %s failed on %s: %s",
                extractor.name, hit.url, page.failure_reason,
            )
        out.append(page)
    return tuple(out)
```

- [ ] **Step 4: Add logging to JinaReader**

Edit `src/irc/research/search/jina_reader.py`. Add at top:

```python
import logging
_log = logging.getLogger(__name__)
```

Inside `extract(...)`, replace each `return ExtractedPage(..., failure_reason=...)` branch with a call that logs first. Centralize via a helper:

```python
def _fail(self, *, url: str, now: str, reason: str) -> ExtractedPage:
    _log.warning("jina_reader failed on %s: %s", url, reason)
    return ExtractedPage(
        url=url, title="", markdown="", fetched_at_iso=now, failure_reason=reason,
    )
```

And replace each of the four `return ExtractedPage(... failure_reason=...)` callsites in `extract()` with `return self._fail(url=url, now=now, reason="…")`. Keep the success branch untouched.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/research/test_dispatch_logging.py tests/research/ -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/irc/research/search/dispatch.py src/irc/research/search/jina_reader.py tests/research/test_dispatch_logging.py
git commit -m "feat(research/search): log every provider and extractor failure at WARNING"
```

**Why this is enough for the `DEBUG=false` requirement:** `irc.observability.console.setup_logging` already pins the root logger at `INFO` when `debug=False` and `DEBUG` when `debug=True`. `_log.warning(...)` is above both thresholds and prints either way. The reason these failures were invisible was not the log level — it's that no one ever called the logger. Steps 3-4 fix that.

---

## Task 6: Plumb `freshness_days` so theme queries get news, not homepages

Every theme query asks for "this past week" or "recent", but `provider_results(...)` is called without `freshness_days`. Tavily and Brave only enable their news/freshness filters when this is set, so both currently fall back to generic web search → homepages and category pages.

**Files:**
- Modify: `src/irc/research/theme_research.py:73, 95-115`
- Test: `tests/research/test_theme_research.py` (extend)

- [ ] **Step 1: Write failing test**

Add to `tests/research/test_theme_research.py`:

```python
# tests/research/test_theme_research.py — append
from typing import Any
from dataclasses import dataclass
from irc.research.search.types import ContentExtractor, ExtractedPage, Locale, SearchHit, SearchProvider, SearchResult
from irc.research.theme_research import build_theme_reports, FRESHNESS_DAYS_BY_THEME


@dataclass
class _RecordingProvider:
    name: str = "tavily"
    locale: Locale = Locale.EN
    seen: list[dict] | None = None

    def __post_init__(self):
        self.seen = []

    def search(self, query: str, *, max_results: int = 10,
               freshness_days: int | None = None,
               include_domains: tuple[str, ...] = (),
               exclude_domains: tuple[str, ...] = ()) -> SearchResult:
        self.seen.append({"query": query, "freshness_days": freshness_days})
        return SearchResult(query=query, locale=self.locale, provider=self.name)


class _NoopExtractor:
    name = "noop"
    def extract(self, url: str, *, timeout_s: int = 20) -> ExtractedPage:
        return ExtractedPage(url=url, title="", markdown="x", fetched_at_iso="2026-05-15T00:00:00+00:00")


def test_build_theme_reports_passes_freshness_per_theme(monkeypatch):
    provider = _RecordingProvider()

    # Synthesize-call shim: skip the LLM by patching synthesize_report.
    from irc.research import theme_research
    monkeypatch.setattr(
        theme_research, "synthesize_report",
        lambda **kw: type("R", (), {"report_md": "", "citations": [], "failure_reason": ""})(),
    )

    build_theme_reports(
        themes=("us_monetary", "gold_drivers"),
        providers=(provider,),
        extractor=_NoopExtractor(),
        route=object(),  # not used because synthesize_report is patched
    )

    by_query = {call["query"]: call["freshness_days"] for call in provider.seen}
    # us_monetary is a weekly news theme → 7-day freshness
    assert by_query["What did the Fed say or do this past week? Cite primary sources."] == 7
    # gold_drivers is broader-window per the per-theme map
    assert by_query[
        "Recent moves in real yields, USD, central bank gold purchases, ETF flows; cite primary sources."
    ] == FRESHNESS_DAYS_BY_THEME["gold_drivers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_theme_research.py::test_build_theme_reports_passes_freshness_per_theme -v`
Expected: FAIL — `FRESHNESS_DAYS_BY_THEME` is undefined and providers see `freshness_days=None`.

- [ ] **Step 3: Add the per-theme map and forward it**

Edit `src/irc/research/theme_research.py`. Near the top, alongside `_THEME_QUERIES`, add:

```python
FRESHNESS_DAYS_BY_THEME: dict[str, int] = {
    "us_monetary": 7,
    "us_fiscal_politics": 7,
    "cn_monetary": 7,
    "cn_equity_property_policy": 14,
    "geopolitics": 7,
    "gold_drivers": 30,
    "holdings_sector": 14,
}
_DEFAULT_FRESHNESS_DAYS = 14
```

Modify `_build_one` to take a freshness arg and pass it through:

```python
def _build_one(
    theme: str,
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    max_hits: int,
    top_pages: int,
    freshness_days: int,
) -> ThemeReport:
    try:
        matched = providers_for_locale(locale, providers)
    except ValueError as exc:
        return ThemeReport(
            theme=theme, query=query, locale=locale.value,
            report_md="", citations=[], failure_reason=str(exc),
            provider_failures=(),
        )
    raw_results = provider_results(
        query, locale, matched, max_results=max_hits, freshness_days=freshness_days,
    )
    # … unchanged below …
```

And `build_theme_reports`:

```python
def build_theme_reports(
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    max_hits: int = 8,
    top_pages: int = 5,
) -> list[ThemeReport]:
    from irc.observability import progress_iter

    out: list[ThemeReport] = []
    for theme in progress_iter(themes, "research", total=len(themes)):
        out.append(_build_one(
            theme=theme,
            query=_query_for(theme),
            locale=theme_locale(theme),
            providers=providers,
            extractor=extractor,
            route=route,
            max_hits=max_hits,
            top_pages=top_pages,
            freshness_days=FRESHNESS_DAYS_BY_THEME.get(theme, _DEFAULT_FRESHNESS_DAYS),
        ))
    return out
```

- [ ] **Step 4: Run the focused test**

Run: `uv run pytest tests/research/test_theme_research.py -v`
Expected: all pass, including the new freshness test.

- [ ] **Step 5: Commit**

```bash
git add src/irc/research/theme_research.py tests/research/test_theme_research.py
git commit -m "feat(research): pass per-theme freshness_days so providers return dated news"
```

---

## Task 7: Build the research quality gate

A pure function that takes the list of `ThemeReport`s and decides whether the research output is good enough to feed downstream stages. Returns a typed verdict the pipeline can act on.

**Files:**
- Create: `src/irc/research/quality_gate.py`
- Test: `tests/research/test_quality_gate.py`

- [ ] **Step 1: Write failing test**

```python
# tests/research/test_quality_gate.py
from __future__ import annotations
from irc.research.quality_gate import QualityVerdict, evaluate_research_quality
from irc.research.theme_research import ThemeReport
from irc.research.synthesize import Citation


def _ok(theme: str, locale: str = "en", n: int = 4) -> ThemeReport:
    return ThemeReport(
        theme=theme, query="q", locale=locale, report_md="x",
        citations=[Citation(index=i + 1, title="t", url=f"https://x/{i}") for i in range(n)],
        failure_reason="",
    )


def _failed(theme: str, locale: str = "en", reason: str = "no sources") -> ThemeReport:
    return ThemeReport(
        theme=theme, query="q", locale=locale, report_md="",
        citations=[], failure_reason=reason,
    )


def test_passes_when_all_themes_succeed():
    reports = [_ok(t) for t in ("us_monetary", "cn_monetary")]
    v = evaluate_research_quality(reports)
    assert v.passed
    assert v.exit_code == 0


def test_fails_when_entire_locale_dead():
    # All zh themes failed → zh locale unusable → critical.
    reports = [
        _ok("us_monetary", locale="en"),
        _failed("cn_monetary", locale="zh", reason="bocha 403 quota"),
        _failed("cn_equity_property_policy", locale="zh", reason="bocha 403 quota"),
        _failed("holdings_sector", locale="zh", reason="bocha 403 quota"),
    ]
    v = evaluate_research_quality(reports)
    assert not v.passed
    assert v.exit_code == 2
    assert "zh" in "\n".join(v.reasons).lower()


def test_fails_when_success_rate_below_floor():
    reports = [_failed(t) for t in ("us_monetary", "cn_monetary", "geopolitics")] + [_ok("gold_drivers")]
    v = evaluate_research_quality(reports)
    assert not v.passed
    # 1/4 = 25% success — below the 50% floor.
    assert any("success rate" in r.lower() for r in v.reasons)


def test_warns_when_success_rate_in_warn_band():
    # 5/7 = ~71%, between 50% (fail) and 80% (warn).
    reports = [_ok(t) for t in ("us_monetary", "us_fiscal_politics", "geopolitics", "gold_drivers", "cn_monetary")]
    reports += [_failed("cn_equity_property_policy"), _failed("holdings_sector")]
    v = evaluate_research_quality(reports)
    assert v.passed  # warn does not block
    assert v.exit_code == 0
    assert v.warning
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_quality_gate.py -v`
Expected: FAIL — `quality_gate` module does not exist.

- [ ] **Step 3: Implement the gate**

```python
# src/irc/research/quality_gate.py
"""Quality gate for the research stage output.

A pure function. Given a list of ThemeReports, decide whether the output is
good enough to drive downstream decisions. Two thresholds:
  - FAIL if any whole locale is dead (every theme of that locale failed)
  - FAIL if overall success rate < 0.5
  - WARN if success rate < 0.8 (does not block, but surfaced)

WARN does not stop the pipeline. FAIL stops it (exit code 2).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from irc.research.theme_research import ThemeReport


_FAIL_SUCCESS_FLOOR = 0.5
_WARN_SUCCESS_FLOOR = 0.8


@dataclass(frozen=True)
class QualityVerdict:
    passed: bool        # False → halt the pipeline
    warning: bool       # True → run completed but quality is degraded
    exit_code: int      # 0 PASS or WARN; 2 FAIL
    reasons: tuple[str, ...]


def evaluate_research_quality(reports: list[ThemeReport]) -> QualityVerdict:
    if not reports:
        return QualityVerdict(
            passed=False, warning=False, exit_code=2,
            reasons=("no theme reports were produced",),
        )

    reasons: list[str] = []

    # Locale liveness: if every theme of a locale failed, that whole locale is dead.
    by_locale: dict[str, list[ThemeReport]] = defaultdict(list)
    for r in reports:
        by_locale[r.locale].append(r)
    for locale, items in by_locale.items():
        if items and all(r.failure_reason for r in items):
            reasons.append(
                f"all {len(items)} {locale} themes failed; downstream analysis cannot "
                f"draw on {locale}-language evidence"
            )

    successes = sum(1 for r in reports if not r.failure_reason)
    rate = successes / len(reports)

    if rate < _FAIL_SUCCESS_FLOOR:
        reasons.append(
            f"success rate {rate:.0%} is below the {_FAIL_SUCCESS_FLOOR:.0%} floor"
        )

    if reasons:
        return QualityVerdict(
            passed=False, warning=False, exit_code=2, reasons=tuple(reasons),
        )

    if rate < _WARN_SUCCESS_FLOOR:
        return QualityVerdict(
            passed=True, warning=True, exit_code=0,
            reasons=(
                f"success rate {rate:.0%} is below the {_WARN_SUCCESS_FLOOR:.0%} "
                "warn threshold (run continues)",
            ),
        )

    return QualityVerdict(passed=True, warning=False, exit_code=0, reasons=())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/research/test_quality_gate.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/research/quality_gate.py tests/research/test_quality_gate.py
git commit -m "feat(research): add quality_gate that fails on dead locale or <50% success"
```

---

## Task 8: Wire the gate into `run_research` so it can halt the pipeline

**Files:**
- Modify: `src/irc/research/pipeline.py`
- Modify: `src/irc/commands/research_cmd.py`
- Test: `tests/research/test_pipeline.py` (extend), `tests/commands/test_research_cmd.py` (extend)

- [ ] **Step 1: Write failing test**

Extend `tests/research/test_pipeline.py`:

```python
# tests/research/test_pipeline.py — append
import json
from pathlib import Path
from irc.research.pipeline import run_research_pipeline
from irc.research.theme_research import ThemeReport


class _FakeProvider:
    name = "fake"
    locale = None
    def search(self, *a, **kw):
        raise NotImplementedError


class _FakeExtractor:
    name = "fake"
    def extract(self, *a, **kw):
        raise NotImplementedError


def test_run_research_pipeline_returns_2_when_quality_gate_fails(tmp_path, monkeypatch):
    # Patch build_theme_reports to return all-failed zh themes.
    from irc.research import pipeline as p

    def _all_failed(themes, **_):
        return [
            ThemeReport(theme=t, query="q", locale="zh", report_md="",
                        citations=[], failure_reason="bocha 403")
            for t in themes
        ]
    monkeypatch.setattr(p, "build_theme_reports", _all_failed)

    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("cn_monetary", "cn_equity_property_policy"),
        providers=(),
        extractor=_FakeExtractor(),
        route=object(),
    )
    assert rc == 2
    # Status file must still be written so downstream debugging works.
    status = json.loads((tmp_path / "data" / "research" / "research_status.json").read_text())
    assert len(status["themes"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_pipeline.py -v -k "quality_gate_fails"`
Expected: FAIL — current pipeline returns 0.

- [ ] **Step 3: Modify pipeline to consult the gate**

Edit `src/irc/research/pipeline.py`:

```python
from __future__ import annotations
import logging
from pathlib import Path

from irc.llm._types import ResolvedRoute
from irc.research.quality_gate import evaluate_research_quality
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.research.persistence import write_research_outputs
from irc.research.theme_research import build_theme_reports

_log = logging.getLogger(__name__)


def run_research_pipeline(
    repo_root: Path,
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
) -> int:
    """Run all theme research; persist outputs; return rc per the quality gate.

    0 = pass (or warn, run continues); 2 = fail (caller should halt).
    """
    out_dir = repo_root / "data" / "research"
    reports = build_theme_reports(
        themes=themes, providers=providers, extractor=extractor, route=route,
    )
    write_research_outputs(out_dir, reports)

    verdict = evaluate_research_quality(reports)
    for reason in verdict.reasons:
        if verdict.passed:
            _log.warning("research quality WARN: %s", reason)
        else:
            _log.error("research quality FAIL: %s", reason)
    if not verdict.passed:
        print("ERROR: research quality gate failed — see warnings above for details")
    return verdict.exit_code
```

- [ ] **Step 4: Surface the verdict from `research_cmd.run_research`**

Edit `src/irc/commands/research_cmd.py` — only the final `return` changes; it already returns whatever `run_research_pipeline` returns, so the only edit is to make sure the early-exit "no providers configured" branch ALSO returns 2 (today it returns 0, which would let the pipeline continue with no research):

```python
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
    return run_research_pipeline(
        repo_root=root,
        themes=themes if themes is not None else _DEFAULT_THEMES,
        providers=providers,
        extractor=extractor,
        route=route,
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/research/ tests/commands/test_research_cmd.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/irc/research/pipeline.py src/irc/commands/research_cmd.py tests/research/test_pipeline.py
git commit -m "feat(research): halt pipeline (rc=2) when quality gate fails or no providers configured"
```

---

## Task 9: Confirm `run_cmd` halts on the new non-zero rc

`src/irc/commands/run_cmd.py:run_pipeline` already halts on any non-zero stage rc — it calls `write_halted(...)` and returns. With Task 8 in place, a research-quality FAIL automatically stops the pipeline before discover/score/memo run. We verify this with an integration test rather than changing `run_cmd`.

**Files:**
- Test: `tests/commands/test_run_cmd_research_halt.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/commands/test_run_cmd_research_halt.py
from __future__ import annotations
import os
from pathlib import Path

import pytest


def test_run_pipeline_halts_at_research_when_gate_fails(tmp_path, monkeypatch):
    # Stub the prior stages to succeed (rc=0) and research to fail (rc=2);
    # later stages must NOT be called.
    from irc.commands import run_cmd

    called: list[str] = []

    def _ok(repo_root: str) -> int:
        called.append("ingest"); return 0

    def _research_fail(repo_root: str) -> int:
        called.append("research"); return 2

    def _later(name: str):
        def _fn(repo_root: str) -> int:
            called.append(name); return 0
        return _fn

    monkeypatch.setattr(run_cmd, "run_ingest", _ok)
    monkeypatch.setattr(run_cmd, "run_research", _research_fail)
    monkeypatch.setattr(run_cmd, "run_discover", _later("discover"))
    monkeypatch.setattr(run_cmd, "run_score", _later("score"))
    monkeypatch.setattr(run_cmd, "run_gold", _later("gold"))
    monkeypatch.setattr(run_cmd, "run_allocate", _later("allocate"))
    monkeypatch.setattr(run_cmd, "run_plan", _later("plan"))
    monkeypatch.setattr(run_cmd, "run_memo", _later("memo"))
    os.environ["RESEARCH_ENABLED"] = "true"

    rc = run_cmd.run_pipeline(str(tmp_path))

    assert rc == 2
    assert called == ["ingest", "research"]
    halt = tmp_path / "outputs" / next(iter(os.listdir(tmp_path / "outputs"))) / "PIPELINE_HALTED.md"
    assert halt.exists()
    body = halt.read_text(encoding="utf-8")
    assert "research" in body
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_run_cmd_research_halt.py -v`
Expected: pass (no code change required — Tasks 7-8 already make this work).

If it fails because `run_cmd` imports the runners by name and patching them via the module fails, switch the test to monkey-patch `run_cmd._runners_map` directly:

```python
monkeypatch.setattr(run_cmd, "_runners_map", lambda: {
    "ingest": _ok, "research": _research_fail,
    "discover": _later("discover"), "score": _later("score"),
    "gold": _later("gold"), "allocate": _later("allocate"),
    "plan": _later("plan"), "memo": _later("memo"),
})
```

- [ ] **Step 3: Commit**

```bash
git add tests/commands/test_run_cmd_research_halt.py
git commit -m "test(run_cmd): verify pipeline halts when research returns rc=2"
```

---

## Task 10: Print research stage summary to console

When research finishes, print a one-screen summary so the user sees at a glance which themes passed, which failed, and why. Today the only signal is the per-theme `_log.warning` lines from Task 5 and the JSON file.

**Files:**
- Modify: `src/irc/research/pipeline.py`
- Test: `tests/research/test_pipeline.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/research/test_pipeline.py`:

```python
def test_run_research_pipeline_prints_summary(tmp_path, monkeypatch, capsys):
    from irc.research import pipeline as p
    from irc.research.theme_research import ThemeReport

    def _mixed(themes, **_):
        return [
            ThemeReport(theme="us_monetary", query="q", locale="en", report_md="x",
                        citations=[], failure_reason=""),
            ThemeReport(theme="cn_monetary", query="q", locale="zh", report_md="",
                        citations=[], failure_reason="bocha 403"),
        ]
    monkeypatch.setattr(p, "build_theme_reports", _mixed)

    p.run_research_pipeline(
        repo_root=tmp_path, themes=("us_monetary", "cn_monetary"),
        providers=(), extractor=object(), route=object(),
    )
    out = capsys.readouterr().err + capsys.readouterr().out
    # User must see both the OK and the failing theme by name.
    assert "us_monetary" in out
    assert "cn_monetary" in out
    assert "bocha 403" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_pipeline.py -k "prints_summary" -v`
Expected: FAIL.

- [ ] **Step 3: Add a summary printer**

Append to `src/irc/research/pipeline.py`:

```python
def _print_summary(reports: list) -> None:
    from irc.observability import console
    ok = [r for r in reports if not r.failure_reason]
    failed = [r for r in reports if r.failure_reason]
    console.print(
        f"research summary: {len(ok)} ok / {len(failed)} failed "
        f"(total {len(reports)})"
    )
    for r in failed:
        console.print(f"  ✗ {r.theme} [{r.locale}] — {r.failure_reason}")
    for r in ok:
        console.print(f"  ✓ {r.theme} [{r.locale}] — {len(r.citations)} citations")
```

Call it in `run_research_pipeline` right after `write_research_outputs(...)`:

```python
    write_research_outputs(out_dir, reports)
    _print_summary(reports)
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/research/test_pipeline.py -k "prints_summary" -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/research/pipeline.py tests/research/test_pipeline.py
git commit -m "feat(research): print per-theme pass/fail summary at end of stage"
```

---

## Task 11: Print eval summary line for each stage (status visible without grepping)

The shared eval-runner contract already calls `print(f"<stage> eval: {overall}")`. With the missing-input changes, that line now prints `FAIL` when input is gone. Add a top-level `eval --all` summary so the user sees aggregate health.

**Files:**
- Modify: `src/irc/commands/eval_cmd.py:27-45`
- Test: `tests/commands/test_eval_cmd.py` (new or extend)

- [ ] **Step 1: Write failing test**

```python
# tests/commands/test_eval_cmd.py
from __future__ import annotations
from pathlib import Path

import pytest

from irc.commands.eval_cmd import run_eval


def test_run_eval_all_prints_summary(tmp_path, capsys):
    # No inputs anywhere → every eval should FAIL (rc=2).
    rc = run_eval(str(tmp_path), stage=None, all_stages=True)
    captured = capsys.readouterr()
    assert rc == 2
    # Summary line must enumerate per-stage status.
    assert "eval summary:" in captured.out.lower()
    assert "fail" in captured.out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_eval_cmd.py -v`
Expected: FAIL — no summary line printed today.

- [ ] **Step 3: Modify `run_eval`**

Replace the `all_stages` branch of `run_eval` in `src/irc/commands/eval_cmd.py`:

```python
def run_eval(repo_root: str, stage: str | None, all_stages: bool) -> int:
    root = Path(repo_root)
    if all_stages:
        stages = (
            "data", "news", "research", "discovery", "scoring",
            "gold_score", "allocation", "trade_plan",
            "memo", "queries", "triggers", "architecture", "opportunity",
        )
        by_stage: dict[str, int] = {}
        for s in stages:
            try:
                rc = _get_runner(s)(root)
            except Exception as e:
                print(f"eval {s} failed: {e}")
                rc = 2
            by_stage[s] = rc
        _print_eval_summary(by_stage)
        return max(by_stage.values())
    # … existing single-stage branch unchanged …


def _print_eval_summary(by_stage: dict[str, int]) -> None:
    def label(rc: int) -> str:
        return {0: "PASS", 1: "WARN", 2: "FAIL"}.get(rc, f"rc={rc}")
    print("eval summary:")
    for stage, rc in by_stage.items():
        print(f"  {label(rc):4} {stage}")
    worst = max(by_stage.values())
    print(f"overall: {label(worst)}")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/commands/test_eval_cmd.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/eval_cmd.py tests/commands/test_eval_cmd.py
git commit -m "feat(eval): print per-stage and overall summary for `eval --all`"
```

---

## Task 12: Drop dead `LDR_*` keys from `.env.example`

The `LDR_*` entries were removed from docs in commit 9a14b01, but `.env.example` and likely `.env` still list them. They mislead anyone configuring the project that "Local Deep Research" is part of the research stack — it isn't, no code reads those keys.

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Audit**

Run: `grep -n "LDR_" .env.example`
Expected: 5 lines.

- [ ] **Step 2: Verify no code reads them**

Run: `grep -rn "LDR_" src/ tests/ evals/`
Expected: zero matches outside of `.env.example`. If matches exist, stop and re-scope this task.

- [ ] **Step 3: Remove the lines**

Edit `.env.example`. Delete the five `LDR_*` lines and any preceding comment block that introduces them.

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "chore: drop dead LDR_* keys from .env.example (Local Deep Research is removed)"
```

---

## Task 13: Update CHANGELOG and README

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md` (only if it documents the eval behavior)

- [ ] **Step 1: Add CHANGELOG entry under the next-version heading**

Append under the unreleased / next-version section of `CHANGELOG.md`:

```markdown
### Changed
- **Eval discipline:** Every stage eval now returns `FAIL` (exit code 2) when its
  input file is missing or unreadable, instead of the previous silent `PASS`.
  Affects 12 runners: allocation, architecture, discovery, gold_score, memo,
  news, opportunity, queries, research, scoring, trade_plan, triggers.
- **Research pipeline halt:** The pipeline now stops at the research stage when
  the quality gate fails (an entire locale dead, or success rate < 50%). Halt
  reason and remediation are written to `outputs/<date>/PIPELINE_HALTED.md`.
- **Search-provider visibility:** Every Tavily/Brave/Bocha/Jina failure is now
  logged at `WARNING` (visible without `DEBUG=true`), and the research stage
  prints a per-theme pass/fail summary at the end.
- **Time-filtered search:** Theme queries now pass `freshness_days` per theme
  (7-30 days) so providers return dated news articles instead of homepages.
- **`eval --all` summary:** Prints per-stage and overall PASS/WARN/FAIL.

### Removed
- Dead `LDR_*` entries from `.env.example` (LDR was deprecated upstream).
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for research failure discipline"
```

---

## Self-Review Notes (already applied)

- **Spec coverage:** All four user-stated requirements covered — (a) all eval false-pass fixed in Tasks 2-4, (b) every silent failure logged in Task 5, (c) `freshness_days` plumbed in Task 6, (d) critical research halts pipeline via Tasks 7-9.
- **Type consistency:** `QualityVerdict.exit_code`, `EVAL_RC_FAIL`, and the `_runners_map` rc contract all converge on the same `0 / 1 / 2` triplet.
- **Placeholder scan:** Every step contains the actual code or command; no TBDs.
- **Why we don't introduce a zh fallback provider in this plan:** That's a separate scope (adding a new search backend, picking one with comparable mainland coverage to Bocha, testing it). This plan makes the bocha-dead failure mode loud and pipeline-halting, which is the user's immediate ask. Adding a fallback provider is a natural follow-up — file a separate plan.
