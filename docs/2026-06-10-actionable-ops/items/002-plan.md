# Item 002 — Local scheduler + notifier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the headless `irc` pipeline run unattended on macOS via launchd and notify the operator (macOS notification always + optional Feishu webhook) only when there is something to do or something went wrong, driven by a pure, table-tested outcome classifier.

**Architecture:** A new `irc notify-status` Click subcommand reads today's `outputs/<china-today>/` artifacts + a wrapper-supplied exit code into a frozen `RunOutcome`, calls the pure `classify_run_outcome(...) -> NotificationDecision`, then dispatches the decision to macOS (`osascript`) and an env-gated Feishu webhook. Two checked-in launchd plists run thin fail-fast wrapper scripts (`irc run` → capture `$rc` → `irc notify-status`). All logic in `src/irc/notify/` is pure; every effect (file read, clock, `osascript`, HTTP POST) lives at the command edge or in the wrapper.

**Tech Stack:** Python 3.12 · Click · pydantic-settings (untouched) · `httpx` (already vendored, for Feishu POST) · `respx` (httpx test mock, already in dev deps) · `pyyaml` (holiday file) · launchd / `plutil` / `osascript` (macOS) · pytest · ruff (line-length 100, py312).

---

## Binding conventions (apply to every task)

- **TDD.** Red → green → refactor for ALL pure logic (`classify_run_outcome`, `should_skip_daily`, `format_macos`, `format_feishu`, the `RunOutcome` builder helpers). Write the failing test FIRST, run it, see it fail, then implement.
- **Tests mirror source.** `src/irc/notify/classify.py` → `tests/notify/test_classify.py`; `src/irc/commands/notify_cmd.py` → `tests/commands/test_notify_cmd.py`.
- **Targeted pytest only.** Run the specific test file/node, never the full suite (the full suite is ~18 min and not green on `main`).
- **Effects at edges.** Pure functions receive every input as an argument — they never read env, clock, or filesystem. `osascript`/`httpx` calls live in thin wrappers in `notify_cmd.py`.
- **Frozen dataclasses, immutability.** `RunOutcome`, `NotificationDecision` are `@dataclass(frozen=True)`. No argument mutation; transforms return new values.
- **Size budget.** Files < 200 lines, functions < 20 lines (ideal). Extract helpers rather than nest > 3 levels.
- **Secrets via env name only.** `IRC_FEISHU_WEBHOOK_URL` read from `os.environ` at the command edge — never a CLI arg, never a `Settings` field, never logged in full.
- **No VERSION bump.** Accumulate under CHANGELOG `[Unreleased]`.
- **Lint.** `uv run ruff check src tests` must pass on every new file.
- **Commit after each green task.** Stay on branch `autodev/actionable-ops-feature` (do not create a new branch, do not push).

---

## File structure (locked before tasks)

```
src/irc/notify/
  __init__.py        # empty package marker
  types.py           # frozen RunOutcome, NotificationDecision; Severity / RunKind literals
  classify.py        # PURE classify_run_outcome(outcome) -> NotificationDecision
  calendar.py        # PURE should_skip_daily(today, holidays) -> bool
  message.py         # PURE format_macos(decision) -> (title, body); format_feishu(decision) -> dict

src/irc/commands/
  notify_cmd.py      # EDGE: read artifacts → RunOutcome; classify; dispatch (osascript, httpx POST)

src/irc/cli.py       # MODIFY: register `notify-status` subcommand

ops/launchd/
  com.irc.daily.plist
  com.irc.weekly-full.plist
  run-daily.sh
  run-weekly-full.sh
  install.sh
  uninstall.sh
  README.md

config/
  cn_market_holidays.yaml   # OPTIONAL static holiday list (committed as an empty-list template)

tests/notify/
  __init__.py
  test_types.py
  test_classify.py
  test_calendar.py
  test_message.py

tests/commands/
  test_notify_cmd.py

CHANGELOG.md          # MODIFY: add [Unreleased] entry
```

Reasoning for the split: `types.py` holds frozen data (no logic), `classify.py` / `calendar.py` / `message.py` are each one pure responsibility (decision precedence / skip predicate / payload formatting), and `notify_cmd.py` is the only file allowed to touch the clock, filesystem, `osascript`, or `httpx`. This keeps every pure module table-testable without mocks and each file well under 200 lines.

---

## Task 1: `notify` package — frozen value types

**Files:**
- Create: `src/irc/notify/__init__.py`
- Create: `src/irc/notify/types.py`
- Test: `tests/notify/__init__.py`, `tests/notify/test_types.py`

- [ ] **Step 1: Create the test package marker**

Create `tests/notify/__init__.py` as an empty file:

```python
```

- [ ] **Step 2: Write the failing test for the value types**

Create `tests/notify/test_types.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from irc.notify.types import NotificationDecision, RunOutcome


def _outcome(**overrides) -> RunOutcome:
    base = dict(
        run_kind="daily",
        last_exit_code=0,
        today_dir_exists=True,
        pipeline_halted=False,
        stale_ingest=False,
        actionable_buy_count=0,
        trim_count=0,
        exit_count=0,
        review_count=0,
    )
    base.update(overrides)
    return RunOutcome(**base)


def test_run_outcome_is_frozen():
    outcome = _outcome()
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.last_exit_code = 1  # type: ignore[misc]


def test_run_outcome_allows_null_sell_counts():
    outcome = _outcome(trim_count=None, exit_count=None, review_count=None)
    assert outcome.trim_count is None
    assert outcome.exit_count is None
    assert outcome.review_count is None


def test_notification_decision_is_frozen():
    decision = NotificationDecision(
        should_notify=True, severity="action", title="t", body="b"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.title = "x"  # type: ignore[misc]
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/notify/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.notify'`.

- [ ] **Step 4: Create the package marker**

Create `src/irc/notify/__init__.py` as an empty file:

```python
```

- [ ] **Step 5: Implement the value types**

Create `src/irc/notify/types.py`:

```python
"""Frozen value types for the outcome notifier.

`RunOutcome` carries every input the pure classifier needs — the command edge
reads the clock, filesystem, and exit code and packs them here so
`classify_run_outcome` stays deterministic and mock-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["failed", "halted", "stale", "action", "clean"]
RunKind = Literal["daily", "weekly"]


@dataclass(frozen=True)
class RunOutcome:
    """Everything the classifier needs, gathered at the command edge.

    Sell-side counts are `int | None`: `None` (JSON null) means signals were
    never derived (pre-001 / stale artifact) — unknown, NOT zero (ADR 0015).
    """

    run_kind: RunKind
    last_exit_code: int
    today_dir_exists: bool
    pipeline_halted: bool
    stale_ingest: bool
    actionable_buy_count: int
    trim_count: int | None
    exit_count: int | None
    review_count: int | None


@dataclass(frozen=True)
class NotificationDecision:
    """The pure classifier's verdict; the dispatcher renders + sends it."""

    should_notify: bool
    severity: Severity
    title: str
    body: str
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/notify/test_types.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/irc/notify tests/notify`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add src/irc/notify/__init__.py src/irc/notify/types.py tests/notify/__init__.py tests/notify/test_types.py
git commit -m "feat(notify): frozen RunOutcome + NotificationDecision value types (item 002)"
```

**Verification gate (Task 1):** `uv run pytest tests/notify/test_types.py -v` is green AND `uv run ruff check src/irc/notify tests/notify` passes. Do not proceed otherwise.

---

## Task 2: pure `classify_run_outcome` — the classifier core

**Files:**
- Create: `src/irc/notify/classify.py`
- Test: `tests/notify/test_classify.py`

Precedence (highest first), per spec §Classification + ADR 0016 §4/§5:
0. `today_dir_exists is False` ⇒ `failed` (run never started).
1. `last_exit_code in {1,2,3,4,5}` ⇒ `failed` (named by exit-code class).
2. `pipeline_halted` ⇒ `halted`.
3. `stale_ingest` ⇒ `stale`.
4. any of `trim/exit/review_count is None` ⇒ `action` (sell-side UNKNOWN — re-run `irc opportunity`).
5. `actionable_buy_count > 0` OR `(trim+exit+review) > 0` ⇒ `action` (rollup body).
6. else ⇒ `clean`.

`should_notify` is True for `failed | halted | stale | action`. For `clean` it is the caller-supplied `notify_on_clean` flag (the classifier receives it as a parameter — it never reads env).

- [ ] **Step 1: Write the failing tests (exhaustive table)**

Create `tests/notify/test_classify.py`:

```python
from __future__ import annotations

import pytest

from irc.notify.classify import classify_run_outcome
from irc.notify.types import RunOutcome


def _outcome(**overrides) -> RunOutcome:
    base = dict(
        run_kind="daily",
        last_exit_code=0,
        today_dir_exists=True,
        pipeline_halted=False,
        stale_ingest=False,
        actionable_buy_count=0,
        trim_count=0,
        exit_count=0,
        review_count=0,
    )
    base.update(overrides)
    return RunOutcome(**base)


def test_missing_today_dir_is_failed_even_at_exit_zero():
    decision = classify_run_outcome(_outcome(today_dir_exists=False, last_exit_code=0))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert "never produced output" in decision.body


@pytest.mark.parametrize(
    "code,label",
    [(1, "runtime"), (2, "config"), (3, "fetch-budget"), (4, "lock"), (5, "spend-gate")],
)
def test_nonzero_exit_codes_are_failed_and_named(code, label):
    decision = classify_run_outcome(_outcome(last_exit_code=code))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert label in decision.title.lower()


def test_pipeline_halted_is_halted():
    decision = classify_run_outcome(_outcome(pipeline_halted=True))
    assert decision.severity == "halted"
    assert decision.should_notify is True


def test_stale_ingest_is_stale():
    decision = classify_run_outcome(_outcome(stale_ingest=True))
    assert decision.severity == "stale"
    assert decision.should_notify is True


def test_null_sell_counts_are_action_unknown():
    decision = classify_run_outcome(
        _outcome(trim_count=None, exit_count=None, review_count=None)
    )
    assert decision.severity == "action"
    assert decision.should_notify is True
    assert "unknown" in decision.body.lower()
    assert "irc opportunity" in decision.body
    # never rendered as 0 or "healthy"
    assert "0" not in decision.body.replace("irc opportunity", "")
    assert "healthy" not in decision.body.lower()


def test_single_null_among_sell_counts_is_action_unknown():
    decision = classify_run_outcome(_outcome(trim_count=None, exit_count=0, review_count=0))
    assert decision.severity == "action"
    assert "unknown" in decision.body.lower()


def test_buys_only_is_action():
    decision = classify_run_outcome(_outcome(actionable_buy_count=2))
    assert decision.severity == "action"
    assert "2" in decision.body


def test_sell_signals_only_is_action():
    decision = classify_run_outcome(_outcome(trim_count=1, exit_count=0, review_count=0))
    assert decision.severity == "action"
    assert "trim" in decision.body.lower()


def test_buys_and_sell_signals_rollup():
    decision = classify_run_outcome(
        _outcome(actionable_buy_count=2, trim_count=1, exit_count=1, review_count=0)
    )
    assert decision.severity == "action"
    body = decision.body.lower()
    assert "2" in body and "buy" in body
    assert "trim" in body and "exit" in body


def test_all_zero_is_clean():
    decision = classify_run_outcome(_outcome())
    assert decision.severity == "clean"


def test_clean_notify_on_clean_true_notifies():
    decision = classify_run_outcome(_outcome(), notify_on_clean=True)
    assert decision.severity == "clean"
    assert decision.should_notify is True


def test_clean_notify_on_clean_false_suppresses():
    decision = classify_run_outcome(_outcome(), notify_on_clean=False)
    assert decision.severity == "clean"
    assert decision.should_notify is False


def test_failed_precedence_beats_halted_and_action():
    # exit 1 AND a positive buy count AND halted: failed wins.
    decision = classify_run_outcome(
        _outcome(last_exit_code=1, pipeline_halted=True, actionable_buy_count=3)
    )
    assert decision.severity == "failed"


def test_halted_precedence_beats_stale_and_action():
    decision = classify_run_outcome(
        _outcome(pipeline_halted=True, stale_ingest=True, actionable_buy_count=3)
    )
    assert decision.severity == "halted"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/notify/test_classify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.notify.classify'`.

- [ ] **Step 3: Implement the classifier**

Create `src/irc/notify/classify.py`:

```python
"""PURE outcome classifier. No file, clock, or env access — every input
arrives on `RunOutcome`. Precedence is locked by ADR 0016 §4/§5 + spec
§Classification.
"""
from __future__ import annotations

from irc.notify.types import NotificationDecision, RunOutcome

_EXIT_LABELS: dict[int, str] = {
    1: "runtime error",
    2: "config error",
    3: "fetch-budget exceeded",
    4: "lock conflict",
    5: "spend-gate stop",
}

_ALWAYS_NOTIFY = {"failed", "halted", "stale", "action"}


def classify_run_outcome(
    outcome: RunOutcome, *, notify_on_clean: bool = True
) -> NotificationDecision:
    """Map a RunOutcome to a NotificationDecision in fixed precedence."""
    severity, title, body = _decide(outcome)
    should_notify = severity in _ALWAYS_NOTIFY or (
        severity == "clean" and notify_on_clean
    )
    return NotificationDecision(
        should_notify=should_notify, severity=severity, title=title, body=body
    )


def _decide(outcome: RunOutcome) -> tuple[str, str, str]:
    if not outcome.today_dir_exists:
        return ("failed", "IRC run failed — no output",
                "No outputs/<today>/ — the scheduled run never produced output.")
    if outcome.last_exit_code in _EXIT_LABELS:
        label = _EXIT_LABELS[outcome.last_exit_code]
        return ("failed", f"IRC run failed — {label}",
                f"Exit {outcome.last_exit_code}. See PIPELINE_HALTED.md / the run log.")
    if outcome.pipeline_halted:
        return ("halted", "IRC run halted",
                "PIPELINE_HALTED.md present — the pipeline stopped mid-run.")
    if outcome.stale_ingest:
        return ("stale", "IRC data stale",
                "STALE_INGEST.md present — report may be built on old inputs.")
    if _any_sell_unknown(outcome):
        return ("action", "IRC: sell-side state UNKNOWN",
                "Sell-side state unknown (stale artifact) — re-run `irc opportunity`.")
    if _has_action(outcome):
        return ("action", "IRC: action required", _rollup_body(outcome))
    return ("clean", "IRC run clean", "Run completed; nothing actionable.")


def _any_sell_unknown(outcome: RunOutcome) -> bool:
    return None in (outcome.trim_count, outcome.exit_count, outcome.review_count)


def _has_action(outcome: RunOutcome) -> bool:
    sells = (outcome.trim_count or 0) + (outcome.exit_count or 0) + (outcome.review_count or 0)
    return outcome.actionable_buy_count > 0 or sells > 0


def _rollup_body(outcome: RunOutcome) -> str:
    parts: list[str] = []
    if outcome.actionable_buy_count > 0:
        parts.append(f"{outcome.actionable_buy_count} buys")
    for count, label in (
        (outcome.trim_count, "trim"),
        (outcome.exit_count, "exit"),
        (outcome.review_count, "review"),
    ):
        if count:
            parts.append(f"{count} {label}")
    return " · ".join(parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/notify/test_classify.py -v`
Expected: PASS (all parametrized cases green — ~19 passed).

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/irc/notify/classify.py tests/notify/test_classify.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/notify/classify.py tests/notify/test_classify.py
git commit -m "feat(notify): pure classify_run_outcome with locked precedence (item 002)"
```

**Verification gate (Task 2):** `uv run pytest tests/notify/test_classify.py -v` green; ruff clean. Covers AC1, AC2, AC3.

---

## Task 3: pure trading-day predicate + pure message formatters

**Files:**
- Create: `src/irc/notify/calendar.py`
- Create: `src/irc/notify/message.py`
- Test: `tests/notify/test_calendar.py`, `tests/notify/test_message.py`

### 3a — `should_skip_daily` (pure predicate)

- [ ] **Step 1: Write the failing test**

Create `tests/notify/test_calendar.py`:

```python
from __future__ import annotations

from datetime import date

from irc.notify.calendar import should_skip_daily


def test_weekday_not_in_holidays_does_not_skip():
    # 2026-06-10 is a Wednesday.
    assert should_skip_daily(date(2026, 6, 10), set()) is False


def test_saturday_skips():
    # 2026-06-13 is a Saturday.
    assert should_skip_daily(date(2026, 6, 13), set()) is True


def test_sunday_skips():
    # 2026-06-14 is a Sunday.
    assert should_skip_daily(date(2026, 6, 14), set()) is True


def test_weekday_in_holidays_skips():
    holiday = date(2026, 10, 1)  # Thursday — CN National Day
    assert should_skip_daily(holiday, {holiday}) is True


def test_empty_holidays_only_skips_weekends():
    assert should_skip_daily(date(2026, 10, 1), set()) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/notify/test_calendar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.notify.calendar'`.

- [ ] **Step 3: Implement the predicate**

Create `src/irc/notify/calendar.py`:

```python
"""PURE trading-day skip predicate. The clock + YAML read are the edge
(notify_cmd / the wrapper); this function takes the date and holiday set as
arguments. ADR 0016 §6.
"""
from __future__ import annotations

from datetime import date

_SATURDAY = 5  # date.weekday(): Mon=0 … Sun=6


def should_skip_daily(today: date, holidays: frozenset[date] | set[date]) -> bool:
    """True on Saturday/Sunday or when `today` is a supplied holiday."""
    return today.weekday() >= _SATURDAY or today in holidays
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/notify/test_calendar.py -v`
Expected: PASS (5 passed).

### 3b — `format_macos` / `format_feishu` (pure formatters)

- [ ] **Step 5: Write the failing test**

Create `tests/notify/test_message.py`:

```python
from __future__ import annotations

from irc.notify.message import format_feishu, format_macos
from irc.notify.types import NotificationDecision


def _decision(severity: str, title: str, body: str) -> NotificationDecision:
    return NotificationDecision(should_notify=True, severity=severity, title=title, body=body)


def test_format_macos_returns_title_and_body():
    decision = _decision("failed", "IRC run failed — fetch-budget exceeded", "Exit 3.")
    title, body = format_macos(decision)
    assert title == "IRC run failed — fetch-budget exceeded"
    assert body == "Exit 3."


def test_format_macos_escapes_double_quotes():
    # osascript string literals are double-quoted; embedded quotes must be escaped.
    decision = _decision("action", 'say "hi"', 'body "x"')
    title, body = format_macos(decision)
    assert '\\"' in title
    assert '\\"' in body


def test_format_feishu_payload_shape_is_text_message():
    decision = _decision("action", "IRC: action required", "2 buys · 1 trim")
    payload = format_feishu(decision)
    assert payload == {
        "msg_type": "text",
        "content": {"text": "[ACTION] IRC: action required\n2 buys · 1 trim"},
    }


def test_format_feishu_severity_tag_uppercased():
    decision = _decision("stale", "IRC data stale", "STALE_INGEST.md present.")
    payload = format_feishu(decision)
    assert payload["content"]["text"].startswith("[STALE] ")
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `uv run pytest tests/notify/test_message.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.notify.message'`.

- [ ] **Step 7: Implement the formatters**

Create `src/irc/notify/message.py`:

```python
"""PURE message formatters. `format_macos` returns the (title, body) pair the
`osascript` edge interpolates; `format_feishu` returns the JSON payload dict the
HTTP edge POSTs. No I/O here.
"""
from __future__ import annotations

from typing import Any

from irc.notify.types import NotificationDecision


def _escape(text: str) -> str:
    """Escape backslashes then double-quotes for an AppleScript string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def format_macos(decision: NotificationDecision) -> tuple[str, str]:
    """Return (title, body) with AppleScript double-quotes escaped."""
    return _escape(decision.title), _escape(decision.body)


def format_feishu(decision: NotificationDecision) -> dict[str, Any]:
    """Return a Feishu `text` webhook payload tagged with the severity."""
    text = f"[{decision.severity.upper()}] {decision.title}\n{decision.body}"
    return {"msg_type": "text", "content": {"text": text}}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/notify/test_calendar.py tests/notify/test_message.py -v`
Expected: PASS (9 passed total).

- [ ] **Step 9: Lint**

Run: `uv run ruff check src/irc/notify/calendar.py src/irc/notify/message.py tests/notify/test_calendar.py tests/notify/test_message.py`
Expected: `All checks passed!`

- [ ] **Step 10: Commit**

```bash
git add src/irc/notify/calendar.py src/irc/notify/message.py tests/notify/test_calendar.py tests/notify/test_message.py
git commit -m "feat(notify): pure should_skip_daily + macOS/Feishu formatters (item 002)"
```

**Verification gate (Task 3):** both test files green; ruff clean. Covers AC4, AC6 (formatter half), AC7 (payload-shape half).

---

## Task 4: `irc notify-status` command edge + CLI registration

**Files:**
- Create: `src/irc/commands/notify_cmd.py`
- Modify: `src/irc/cli.py` (append a `notify-status` command after the `eval` command, ~line 314)
- Create: `config/cn_market_holidays.yaml`
- Test: `tests/commands/test_notify_cmd.py`

The command edge: resolve today via UTC+8 `_china_today()` (NO latest-dir fallback — Resolved Q3), build `RunOutcome` from disk, classify, dispatch. `osascript` via `subprocess`; Feishu via `httpx`; both wrapped so a transport failure logs + sets a non-zero exit WITHOUT raising (AC8). The webhook URL is read from `os.environ["IRC_FEISHU_WEBHOOK_URL"]` only and never logged in full (AC7).

- [ ] **Step 1: Write the failing tests for the edge (pure helpers + dispatch, no real I/O)**

Create the test package marker if absent — check first:

Run: `ls tests/commands/__init__.py 2>/dev/null && echo EXISTS || echo MISSING`
If MISSING, create `tests/commands/__init__.py` as an empty file. (If it already exists, skip.)

Create `tests/commands/test_notify_cmd.py`:

```python
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import respx
from click.testing import CliRunner

from irc.cli import main
from irc.commands import notify_cmd
from irc.notify.types import NotificationDecision


def _write_outputs(root: Path, date_str: str, summary: dict) -> Path:
    out = root / "outputs" / date_str
    out.mkdir(parents=True)
    report = {"overall_status": "ok", "summary": summary}
    (out / "decision_report.json").write_text(json.dumps(report), encoding="utf-8")
    return out


# ---- pure-ish builder helpers (no network/osascript) ----

def test_load_holidays_absent_file_is_empty_set(tmp_path: Path):
    assert notify_cmd._load_holidays(tmp_path) == set()


def test_load_holidays_reads_yaml_list(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "cn_market_holidays.yaml").write_text(
        "- 2026-10-01\n- 2026-10-02\n", encoding="utf-8"
    )
    from datetime import date

    holidays = notify_cmd._load_holidays(tmp_path)
    assert date(2026, 10, 1) in holidays
    assert date(2026, 10, 2) in holidays


def test_build_outcome_missing_today_dir(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2099, 1, 1))
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.today_dir_exists is False


def test_build_outcome_reads_summary_counts(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    _write_outputs(
        tmp_path, "2026-06-10",
        {"actionable_buy_count": 2, "trim_count": 1, "exit_count": 0, "review_count": 0},
    )
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.today_dir_exists is True
    assert outcome.actionable_buy_count == 2
    assert outcome.trim_count == 1


def test_build_outcome_preserves_null_sell_counts(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    _write_outputs(
        tmp_path, "2026-06-10",
        {"actionable_buy_count": 0, "trim_count": None, "exit_count": None, "review_count": None},
    )
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.trim_count is None


def test_build_outcome_detects_halt_and_stale(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    out = _write_outputs(tmp_path, "2026-06-10", {"actionable_buy_count": 0})
    (out / "PIPELINE_HALTED.md").write_text("halt", encoding="utf-8")
    (out / "STALE_INGEST.md").write_text("stale", encoding="utf-8")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.pipeline_halted is True
    assert outcome.stale_ingest is True


# ---- dispatch: both channels stubbed (AC8) ----

def test_dispatch_continues_when_macos_fails(monkeypatch, caplog):
    decision = NotificationDecision(True, "action", "t", "b")
    monkeypatch.setattr(
        notify_cmd, "_send_macos",
        lambda d: (_ for _ in ()).throw(RuntimeError("osascript boom")),
    )
    posted = {}
    monkeypatch.setattr(notify_cmd, "_send_feishu", lambda d, url: posted.update(sent=True))
    monkeypatch.setenv("IRC_FEISHU_WEBHOOK_URL", "https://hook.example/abc")
    with caplog.at_level(logging.WARNING):
        rc = notify_cmd._dispatch(decision)
    assert rc != 0  # transport failure => non-zero
    assert posted == {"sent": True}  # feishu still attempted


def test_dispatch_feishu_skipped_when_env_unset(monkeypatch):
    decision = NotificationDecision(True, "action", "t", "b")
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: None)
    called = {"feishu": False}
    monkeypatch.setattr(
        notify_cmd, "_send_feishu", lambda d, url: called.__setitem__("feishu", True)
    )
    monkeypatch.delenv("IRC_FEISHU_WEBHOOK_URL", raising=False)
    rc = notify_cmd._dispatch(decision)
    assert rc == 0
    assert called["feishu"] is False


def test_dispatch_skips_everything_when_should_not_notify(monkeypatch):
    decision = NotificationDecision(False, "clean", "t", "b")
    called = {"macos": False}
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: called.__setitem__("macos", True))
    monkeypatch.setattr(notify_cmd, "_send_feishu", lambda d, url: None)
    rc = notify_cmd._dispatch(decision)
    assert rc == 0
    assert called["macos"] is False


# ---- Feishu URL never logged in full (AC7) ----

@respx.mock
def test_feishu_post_does_not_log_full_url(caplog):
    url = "https://open.feishu.cn/hook/SECRET-TOKEN-1234"
    respx.post(url).mock(return_value=httpx.Response(200, json={"code": 0}))
    decision = NotificationDecision(True, "action", "t", "b")
    with caplog.at_level(logging.INFO):
        notify_cmd._send_feishu(decision, url)
    for record in caplog.records:
        assert "SECRET-TOKEN-1234" not in record.getMessage()


# ---- CLI smoke (AC5) ----

def test_notify_status_help_lists_options():
    result = CliRunner().invoke(main, ["notify-status", "--help"])
    assert result.exit_code == 0
    for opt in ("--run-kind", "--last-exit-code", "--repo-root", "--notify-on-clean"):
        assert opt in result.output


def test_notify_status_clean_suppressed_exits_zero_no_network(tmp_path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: None)  # avoid real osascript
    monkeypatch.delenv("IRC_FEISHU_WEBHOOK_URL", raising=False)
    _write_outputs(
        tmp_path, "2026-06-10",
        {"actionable_buy_count": 0, "trim_count": 0, "exit_count": 0, "review_count": 0},
    )
    result = CliRunner().invoke(
        main,
        ["notify-status", "--run-kind", "daily", "--last-exit-code", "0",
         "--repo-root", str(tmp_path), "--no-notify-on-clean"],
    )
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/commands/test_notify_cmd.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.commands.notify_cmd'` (and the CLI smoke tests fail because the subcommand isn't registered).

- [ ] **Step 3: Implement the command edge**

> **Amendment (drift review, 2026-06-10):** `httpx` logs `request.url` at INFO via its
> own `"httpx"` logger, which propagates to the root logger. Because `setup_logging()`
> sets root to INFO (writing to stderr → launchd `StandardErrorPath`), the full Feishu
> webhook URL (including the secret token) would appear in log files. Fix: add
> `logging.getLogger("httpx").setLevel(logging.WARNING)` at the top of `_send_feishu`
> (or once at module level). The AC7 test must assert over ALL log records (not just the
> `"irc.commands.notify_cmd"` logger) to verify the httpx logger emits nothing containing
> the token.

Create `src/irc/commands/notify_cmd.py`:

```python
"""EDGE: read today's artifacts → RunOutcome → classify → dispatch.

All effects live here: `_china_today` (clock), `_build_outcome`/`_load_holidays`
(filesystem), `_send_macos` (osascript via subprocess), `_send_feishu` (httpx
POST). The pure logic is imported from `irc.notify`. A transport failure logs
and sets a non-zero return WITHOUT raising — a broken notifier must never mask
the underlying run result (ADR 0016 / AC8).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from irc.notify.classify import classify_run_outcome
from irc.notify.message import format_feishu, format_macos
from irc.notify.types import NotificationDecision, RunOutcome

_log = logging.getLogger(__name__)
_TRUE = {"1", "true", "yes", "on"}
_FEISHU_ENV = "IRC_FEISHU_WEBHOOK_URL"
_CLEAN_ENV = "IRC_NOTIFY_ON_CLEAN"


def _china_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _load_holidays(root: Path) -> set[date]:
    """Read config/cn_market_holidays.yaml (flat YYYY-MM-DD list). Absent ⇒ {}."""
    path = root / "config" / "cn_market_holidays.yaml"
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return {date.fromisoformat(str(item)) for item in raw}


def _build_outcome(root: Path, *, run_kind: str, last_exit_code: int) -> RunOutcome:
    """Gather today's on-disk artifacts into a frozen RunOutcome (no fallback)."""
    out_dir = root / "outputs" / _china_today().isoformat()
    if not out_dir.exists():
        return RunOutcome(
            run_kind=run_kind, last_exit_code=last_exit_code, today_dir_exists=False,
            pipeline_halted=False, stale_ingest=False, actionable_buy_count=0,
            trim_count=0, exit_count=0, review_count=0,
        )
    summary = _read_summary(out_dir / "decision_report.json")
    return RunOutcome(
        run_kind=run_kind,
        last_exit_code=last_exit_code,
        today_dir_exists=True,
        pipeline_halted=(out_dir / "PIPELINE_HALTED.md").exists(),
        stale_ingest=(out_dir / "STALE_INGEST.md").exists(),
        actionable_buy_count=int(summary.get("actionable_buy_count", 0) or 0),
        trim_count=summary.get("trim_count", 0),
        exit_count=summary.get("exit_count", 0),
        review_count=summary.get("review_count", 0),
    )


def _read_summary(path: Path) -> dict:
    """Return decision_report.json's `summary`; {} when absent/malformed."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("summary", {}) or {}
    except json.JSONDecodeError:
        _log.warning("could not parse decision_report.json — summary defaulted")
        return {}


def _send_macos(decision: NotificationDecision) -> None:
    """Issue a macOS user notification via osascript (effect)."""
    title, body = format_macos(decision)
    script = f'display notification "{body}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def _send_feishu(decision: NotificationDecision, url: str) -> None:
    """POST the Feishu payload (effect). Logs host only — never the full URL."""
    payload = format_feishu(decision)
    _log.info("posting Feishu notification to host=%s", urlsplit(url).hostname or "?")
    resp = httpx.post(url, json=payload, timeout=10.0)
    resp.raise_for_status()


def _resolve_notify_on_clean(flag: bool | None) -> bool:
    """CLI flag wins; else IRC_NOTIFY_ON_CLEAN env; else default True."""
    if flag is not None:
        return flag
    raw = os.environ.get(_CLEAN_ENV, "").strip().lower()
    return raw in _TRUE if raw else True


def _dispatch(decision: NotificationDecision) -> int:
    """Send both channels independently. Returns 0 on full success, 1 if any
    channel failed. Never raises — a broken channel must not block the other."""
    if not decision.should_notify:
        return 0
    rc = 0
    try:
        _send_macos(decision)
    except Exception:  # noqa: BLE001 — degrade-never-crash (ADR 0016 / AC8)
        _log.warning("macOS notification failed", exc_info=True)
        rc = 1
    url = os.environ.get(_FEISHU_ENV, "").strip()
    if url:
        try:
            _send_feishu(decision, url)
        except Exception:  # noqa: BLE001 — degrade-never-crash
            _log.warning("Feishu notification failed", exc_info=True)
            rc = 1
    return rc


def run_notify_status(
    *, repo_root: str, run_kind: str, last_exit_code: int, notify_on_clean: bool | None,
) -> int:
    """Read artifacts → classify → dispatch. Returns the dispatch exit code."""
    root = Path(repo_root)
    outcome = _build_outcome(root, run_kind=run_kind, last_exit_code=last_exit_code)
    decision = classify_run_outcome(
        outcome, notify_on_clean=_resolve_notify_on_clean(notify_on_clean)
    )
    _log.info("notify-status severity=%s notify=%s", decision.severity, decision.should_notify)
    return _dispatch(decision)
```

- [ ] **Step 4: Register the subcommand in `src/irc/cli.py`**

Append the following AFTER the `eval` command (the last command in the file, currently ending at line 314). Insert at end of file:

```python


@main.command("notify-status", help="Classify the last scheduled run's outcome and notify (macOS + optional Feishu).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--run-kind", type=click.Choice(["daily", "weekly"]), required=True,
              help="Which scheduled cadence produced this run.")
@click.option("--last-exit-code", "last_exit_code", type=int, required=True,
              help="The pipeline process exit code captured by the launchd wrapper.")
@click.option("--notify-on-clean/--no-notify-on-clean", "notify_on_clean", default=None,
              help="Emit a quiet notification on a clean run (env: IRC_NOTIFY_ON_CLEAN; default on).")
def notify_status(
    repo_root: str, run_kind: str, last_exit_code: int, notify_on_clean: bool | None,
) -> None:
    from irc.commands.notify_cmd import run_notify_status
    rc = run_notify_status(
        repo_root=repo_root, run_kind=run_kind,
        last_exit_code=last_exit_code, notify_on_clean=notify_on_clean,
    )
    raise SystemExit(rc)
```

- [ ] **Step 5: Create the holiday template**

Create `config/cn_market_holidays.yaml`:

```yaml
# CN market holidays (non-trading weekdays) — user-maintained, refreshed yearly.
# Flat list of YYYY-MM-DD strings. Absent file ⇒ weekend-only skip (ADR 0016 §6).
# Example (uncomment + update each year):
# - 2026-10-01  # National Day
# - 2026-10-02
[]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/commands/test_notify_cmd.py -v`
Expected: PASS (all helper, dispatch, AC7-log, and CLI-smoke tests green).

- [ ] **Step 7: Confirm the existing CLI smoke test still passes**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: PASS (registration did not break the group).

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/irc/commands/notify_cmd.py src/irc/cli.py tests/commands/test_notify_cmd.py`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/irc/commands/notify_cmd.py src/irc/cli.py config/cn_market_holidays.yaml tests/commands/test_notify_cmd.py
git commit -m "feat(notify): irc notify-status command edge + CLI registration (item 002)"
```

**Verification gate (Task 4):** `tests/commands/test_notify_cmd.py` and `tests/test_cli_smoke.py` green; ruff clean. Covers AC5, AC6 (osascript edge wiring), AC7, AC8, plus Resolved Q3 (UTC+8, no fallback).

---

## Task 5: launchd plists + wrapper / install / uninstall scripts

**Files:**
- Create: `ops/launchd/com.irc.daily.plist`
- Create: `ops/launchd/com.irc.weekly-full.plist`
- Create: `ops/launchd/run-daily.sh`
- Create: `ops/launchd/run-weekly-full.sh`
- Create: `ops/launchd/install.sh`
- Create: `ops/launchd/uninstall.sh`
- Create: `ops/launchd/README.md`

These are validated with `plutil -lint` (plists) and `bash -n` (scripts; `shellcheck` is absent on this machine per AC10 — note it and skip). The plists ship with a `__REPO_ROOT__` placeholder that `install.sh` templates to the absolute repo path at install time (so the checked-in file carries no machine-specific path).

- [ ] **Step 1: Create the daily plist**

Create `ops/launchd/com.irc.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.irc.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>__REPO_ROOT__/ops/launchd/run-daily.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>__REPO_ROOT__</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>__REPO_ROOT__/outputs/_logs/launchd-daily.out.log</string>
  <key>StandardErrorPath</key>
  <string>__REPO_ROOT__/outputs/_logs/launchd-daily.err.log</string>
</dict>
</plist>
```

Note: `Weekday` 1–5 = Mon–Fri; `StartCalendarInterval` fires in the machine's local timezone (no TZ field exists). 17:30 ≈ 17:30 China time on a UTC+8 machine; a non-UTC+8 operator edits `Hour`/`Minute` (ops README documents this). The daily wrapper additionally short-circuits on weekends/holidays before spending budget.

- [ ] **Step 2: Create the weekly plist**

Create `ops/launchd/com.irc.weekly-full.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.irc.weekly-full</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>__REPO_ROOT__/ops/launchd/run-weekly-full.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>__REPO_ROOT__</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>6</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>__REPO_ROOT__/outputs/_logs/launchd-weekly.out.log</string>
  <key>StandardErrorPath</key>
  <string>__REPO_ROOT__/outputs/_logs/launchd-weekly.err.log</string>
</dict>
</plist>
```

Note: `Weekday` 6 = Saturday; 09:00 machine-local. Weekly is unconditional (no trading-day skip).

- [ ] **Step 3: Validate both plists**

Run: `plutil -lint ops/launchd/com.irc.daily.plist ops/launchd/com.irc.weekly-full.plist`
Expected:
```
ops/launchd/com.irc.daily.plist: OK
ops/launchd/com.irc.weekly-full.plist: OK
```

(The `__REPO_ROOT__` placeholder is a valid plist string, so `plutil -lint` passes pre-templating.)

- [ ] **Step 4: Create the daily wrapper**

Create `ops/launchd/run-daily.sh`:

```bash
#!/bin/bash
# Daily launchd wrapper: skip non-trading days, run the FULL pipeline, notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

# Trading-day gate (UTC+8): skip Sat/Sun and dates listed in the holiday YAML.
TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"
DOW="$(TZ='Asia/Shanghai' date +%u)"  # 1=Mon … 7=Sun
HOLIDAYS_FILE="config/cn_market_holidays.yaml"
if [ "$DOW" -ge 6 ]; then
  echo "[$TODAY] weekend — skipping daily run."
  exit 0
fi
if [ -f "$HOLIDAYS_FILE" ] && grep -q "$TODAY" "$HOLIDAYS_FILE"; then
  echo "[$TODAY] CN holiday — skipping daily run."
  exit 0
fi

rc=0
uv run irc run || rc=$?
uv run irc notify-status --run-kind daily --last-exit-code "$rc"
```

- [ ] **Step 5: Create the weekly wrapper**

Create `ops/launchd/run-weekly-full.sh`:

```bash
#!/bin/bash
# Weekly launchd wrapper: unconditional FULL pipeline (Saturday), then notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

rc=0
uv run irc run || rc=$?
uv run irc notify-status --run-kind weekly --last-exit-code "$rc"
```

Note: `uv run irc run || rc=$?` captures the exit code without tripping `set -e`; the subsequent `notify-status` line is the only place the outcome is classified. The wrapper does NOT gate on `notify-status`'s own exit (a broken notifier must not mask the run result — Resolved Q7).

- [ ] **Step 6: Create the install script**

Create `ops/launchd/install.sh`:

```bash
#!/bin/bash
# Idempotent install: template the repo path into the plists, copy to
# ~/Library/LaunchAgents, then bootout-then-bootstrap each LaunchAgent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$REPO_ROOT/ops/launchd"
DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.daily" "com.irc.weekly-full")

mkdir -p "$DEST_DIR"
mkdir -p "$REPO_ROOT/outputs/_logs"

for label in "${LABELS[@]}"; do
  src="$SRC_DIR/$label.plist"
  dest="$DEST_DIR/$label.plist"
  sed "s#__REPO_ROOT__#$REPO_ROOT#g" "$src" > "$dest"
  plutil -lint "$dest"
  # Idempotent: ignore "not found" on first install.
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$dest"
  echo "installed $label"
done

echo "Done. Inspect with: launchctl print gui/$UID_NUM/com.irc.daily"
```

- [ ] **Step 7: Create the uninstall script**

Create `ops/launchd/uninstall.sh`:

```bash
#!/bin/bash
# Idempotent uninstall: bootout each LaunchAgent and remove its plist.
set -euo pipefail

DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.daily" "com.irc.weekly-full")

for label in "${LABELS[@]}"; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$DEST_DIR/$label.plist"
  echo "removed $label"
done

echo "Done."
```

- [ ] **Step 8: Syntax-check every script with `bash -n` (shellcheck is absent)**

Run: `for s in ops/launchd/*.sh; do echo "== $s =="; bash -n "$s" && echo OK; done`
Expected: each script prints `OK` with no syntax error.

Also confirm shellcheck is genuinely absent (AC10 allows skipping with a note):

Run: `command -v shellcheck >/dev/null 2>&1 && shellcheck ops/launchd/*.sh || echo "shellcheck not on PATH — skipped per AC10"`
Expected: `shellcheck not on PATH — skipped per AC10`

- [ ] **Step 9: Mark scripts executable**

Run: `chmod +x ops/launchd/*.sh && ls -l ops/launchd/*.sh`
Expected: each `.sh` shows `-rwxr-xr-x` (executable bit set).

- [ ] **Step 10: Write the ops README**

Create `ops/launchd/README.md`:

````markdown
# IRC local scheduler (launchd) — ops runbook

Two user LaunchAgents run the `irc` pipeline unattended and notify on outcome
(macOS notification always; optional Feishu webhook). Architecture: ADR 0016.

| Label | Schedule (machine-local) | Command | Trading-day gate |
|---|---|---|---|
| `com.irc.daily` | Mon–Fri 17:30 | full `irc run` | skips weekends + `config/cn_market_holidays.yaml` |
| `com.irc.weekly-full` | Sat 09:00 | full `irc run` | none (unconditional) |

Both wrappers run the **full** `irc run` (NOT a short `ingest → opportunity →
decision` chain — `irc decision` requires `score`/`allocate`/`plan`/`memo`
artifacts, ADR 0016 §2), capture `$?`, then call `irc notify-status`.

## Install

```bash
bash ops/launchd/install.sh
```

Idempotent: re-running boots out the existing agent first, then bootstraps the
freshly-templated plist. `RunAtLoad=false`, so install never triggers an
immediate run — the first run is at the next scheduled fire.

## Uninstall

```bash
bash ops/launchd/uninstall.sh
```

## Timezone assumption (machine-local)

`StartCalendarInterval` has **no timezone field** — it fires in the machine's
local zone. The 17:30 / Sat-09:00 targets assume the machine is on **UTC+8**
(China), so 17:30 ≈ post-NAV. The pipeline's internal date resolution always
uses UTC+8 (`_china_today`) regardless. **If your machine is NOT on UTC+8,**
edit `Hour`/`Minute` in `com.irc.daily.plist` / `com.irc.weekly-full.plist`
before installing.

## Holiday calendar

`config/cn_market_holidays.yaml` is a flat user-maintained list of
`YYYY-MM-DD` strings (refresh yearly). **Absent ⇒ weekend-only skip.** The
daily wrapper greps it before spending any paid-API budget.

## Feishu webhook (optional)

Set `IRC_FEISHU_WEBHOOK_URL` in your `.env`. Unset ⇒ macOS-only. The URL is
read from the env var by name only, never passed as a CLI arg, never logged in
full.

## Logs

| File | Content |
|---|---|
| `outputs/_logs/launchd-daily.out.log` / `.err.log` | daily job stdout/stderr |
| `outputs/_logs/launchd-weekly.out.log` / `.err.log` | weekly job stdout/stderr |

Inspect a loaded agent: `launchctl print gui/$(id -u)/com.irc.daily`.

## Validation

```bash
plutil -lint ops/launchd/*.plist        # both must print OK
for s in ops/launchd/*.sh; do bash -n "$s"; done   # no syntax errors
# shellcheck if on PATH: shellcheck ops/launchd/*.sh
```
````

- [ ] **Step 11: Commit**

```bash
git add ops/launchd/
git commit -m "feat(notify): launchd plists + wrapper/install/uninstall scripts + ops README (item 002)"
```

**Verification gate (Task 5):** both plists `plutil -lint` → `OK`; every `.sh` passes `bash -n`; all scripts executable; README present. Covers AC9, AC10, AC11 (the manual dry-run procedure is documented in the README).

---

## Task 6: end-to-end manual dry-run + CHANGELOG + final lint

**Files:**
- Modify: `CHANGELOG.md` (under the existing `## [Unreleased]` heading)

- [ ] **Step 1: Manual end-to-end dry run — clean today (AC11)**

This exercises the real `osascript` edge (un-unit-tested). Run against today's actual `outputs/<china-today>/` with Feishu unset:

Run:
```bash
unset IRC_FEISHU_WEBHOOK_URL
uv run irc notify-status --run-kind daily --last-exit-code 0
echo "exit=$?"
```
Expected: a real macOS notification appears (or, if you add `--no-notify-on-clean` and today is clean, none appears); `exit=0`; no network call (Feishu env unset). If today's `outputs/<date>/` is absent you will instead get a `failed`-severity notification ("never produced output") — that is correct (Resolved Q3).

- [ ] **Step 2: Manual dry run — forced failure class (AC11)**

Run:
```bash
uv run irc notify-status --run-kind daily --last-exit-code 3
echo "exit=$?"
```
Expected: a macOS notification titled `IRC run failed — fetch-budget exceeded`; `exit=0` (dispatch succeeded; the *run* failure is reported, not re-raised).

- [ ] **Step 3: Add the CHANGELOG entry**

In `CHANGELOG.md`, under the existing `## [Unreleased]` heading (it is the first `##` after the format preamble), add this as a new subsection immediately below `## [Unreleased]` and above the existing `### Added — Sell surfacing …` block:

```markdown
### Added — Local scheduler + outcome notifier (2026-06-10)

- **The pipeline now runs unattended on macOS and notifies the operator on
  outcome.** A new `irc notify-status --run-kind {daily|weekly} --last-exit-code
  <int>` subcommand reads today's `outputs/<china-today>/` artifacts
  (`decision_report.json` summary counts, `PIPELINE_HALTED.md`, `STALE_INGEST.md`)
  plus a launchd-wrapper-supplied exit code into a frozen `RunOutcome`, calls the
  pure `classify_run_outcome` (`src/irc/notify/`), and dispatches a macOS
  notification (always, via `osascript`) plus an optional Feishu webhook (gated on
  `IRC_FEISHU_WEBHOOK_URL`). Classification precedence (ADR 0016): missing
  today-dir ⇒ `failed`; exit 1–5 ⇒ `failed`; `PIPELINE_HALTED.md` ⇒ `halted`;
  `STALE_INGEST.md` ⇒ `stale`; any `null` sell-side count ⇒ `action` ("sell-side
  state UNKNOWN — re-run `irc opportunity`", never folded into clean per ADR 0015);
  buys-or-sell-signals ⇒ `action`; else `clean` (quiet by default,
  `--no-notify-on-clean` / `IRC_NOTIFY_ON_CLEAN=0` suppresses). Scheduling is via
  two checked-in launchd LaunchAgents (`ops/launchd/`, install/uninstall scripts):
  a Mon–Fri 17:30 daily run (skips weekends + `config/cn_market_holidays.yaml`)
  and a Saturday-morning weekly run, both running the full `irc run`. The
  classifier is pure and table-tested; only `osascript` / the Feishu POST are
  effects; a notifier transport failure logs and exits non-zero without raising.
  `notify-status` never trips the spend gate. See ADR 0016.
```

- [ ] **Step 4: Full-surface lint (AC12)**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 5: Size-budget spot check (AC12)**

Run: `wc -l src/irc/notify/*.py src/irc/commands/notify_cmd.py`
Expected: every file < 200 lines (notify_cmd is the largest, well under 200).

- [ ] **Step 6: Full notify-suite green sweep**

Run: `uv run pytest tests/notify tests/commands/test_notify_cmd.py tests/test_cli_smoke.py -v`
Expected: all green (one consolidated pass over every new test plus the CLI smoke).

- [ ] **Step 7: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(notify): CHANGELOG [Unreleased] entry for local scheduler + notifier (item 002)"
```

**Verification gate (Task 6):** the manual dry-runs produced the expected notifications; `uv run ruff check src tests` clean; the notify suite green; no VERSION bump. Covers AC11, AC12.

---

## Acceptance-criteria coverage map

| AC | Covered by |
|---|---|
| AC1 — classify pure + exhaustively table-tested | Task 2 |
| AC2 — `null` ≠ 0 enforced | Task 2 (`test_null_sell_counts_*`), Task 4 (`test_build_outcome_preserves_null_sell_counts`) |
| AC3 — actionable rollup fires on buys OR sells | Task 2 (`test_buys_only` / `test_sell_signals_only` / `test_buys_and_sell_signals_rollup`) |
| AC4 — `should_skip_daily` pure predicate | Task 3a |
| AC5 — `irc notify-status` registered subcommand w/ options | Task 4 (`test_notify_status_help_lists_options`) |
| AC6 — macOS notification on `should_notify`; formatter tested | Task 3b (`format_macos`) + Task 4 (osascript edge wiring) |
| AC7 — Feishu env-gated, secret-safe, host-only logging | Task 3b (payload shape) + Task 4 (`test_dispatch_feishu_skipped_when_env_unset`, `test_feishu_post_does_not_log_full_url`) |
| AC8 — transport failure never masks run result | Task 4 (`test_dispatch_continues_when_macos_fails`) |
| AC9 — plists valid + lint-clean | Task 5 (`plutil -lint`) |
| AC10 — install/uninstall idempotent; shellcheck-if-available | Task 5 (`bash -n`, shellcheck-skip note, idempotent bootout-then-bootstrap) |
| AC11 — end-to-end dry run | Task 5 README + Task 6 Steps 1–2 |
| AC12 — lint + size budget; no VERSION bump; CHANGELOG | Task 6 |

## Self-review notes

- **Spec coverage:** every AC1–AC12 maps to a task (table above). Resolved Q1 (full `irc run` both cadences) → wrappers in Task 5. Q2 (no spend gate) → `notify_cmd` never imports `preflight_gate`. Q3 (UTC+8, no fallback, missing-dir ⇒ failed) → `_build_outcome` + classifier branch 0. Q4 (one notification) → single `irc run` + single `notify-status` in each wrapper. Q5 (`IRC_FEISHU_WEBHOOK_URL` via `os.environ`) → `_dispatch`, never a `Settings` field. Q6 (machine-local time) → plist comments + README. Q7 (degrade-never-crash) → `_dispatch` try/except.
- **Type consistency:** `RunOutcome` fields are identical across Tasks 1/2/4; `NotificationDecision(should_notify, severity, title, body)` positional order matches the dataclass field order in Task 1 and the test constructors. `classify_run_outcome(outcome, *, notify_on_clean=True)` signature is identical in Tasks 2 and 4. `format_macos` returns `(title, body)`; `format_feishu` returns the `{"msg_type": "text", "content": {"text": ...}}` dict — both consumed unchanged by `notify_cmd`.
- **No placeholders:** every code step contains full content; no TBD.
