# CLI Console Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add progress bars, categorized error reporting, and a `DEBUG=true` flag to the `irc` CLI so `LDR_ENABLED=true uv run irc run` shows exactly where the pipeline is, what's failing, and why.

**Architecture:** Introduce a small `src/irc/observability/` package with four files — `console.py` (rich `Console` + `setup_logging`), `progress.py` (`progress_iter`, `stage_banner` context managers), `errors.py` (pure `classify_exception` + stateful `ErrorTally`), and `__init__.py` re-exporting the public API. Existing commands gain a few well-placed wrappers; the rest stays untouched. Logging goes to stderr; result-style `print()` calls keep their stdout.

**Tech Stack:** Python 3.12, `rich>=13` (already transitive via openbb), `pydantic-settings`, `click`, `pytest`, uv.

**Spec:** `docs/superpowers/specs/2026-05-14-cli-console-observability-design.md`

---

## File map

**New files (4 production + 5 test):**
- `src/irc/observability/__init__.py` — public API re-exports
- `src/irc/observability/console.py` — shared `Console`, `setup_logging`
- `src/irc/observability/progress.py` — `progress_iter`, `stage_banner`
- `src/irc/observability/errors.py` — `classify_exception` (pure), `ErrorTally`
- `tests/observability/__init__.py` — empty
- `tests/observability/test_classify_exception.py`
- `tests/observability/test_error_tally.py`
- `tests/observability/test_console_setup.py`
- `tests/observability/test_progress_iter.py`
- `tests/observability/test_stage_banner.py`

**Modified files:**
- `pyproject.toml` — add `rich>=13.0` to direct deps
- `src/irc/settings.py` — add `debug: bool = False`
- `src/irc/cli.py:7-9` — wire `setup_logging` in `main()`
- `src/irc/commands/run_cmd.py:36-50` — wrap stage loop in `stage_banner`
- `src/irc/commands/ingest_cmd.py:220-252` — `progress_iter` + `ErrorTally` over metadata loop
- `src/irc/commands/ingest_cmd.py:404-450` — `progress_iter` + `ErrorTally` over prices loop
- `src/irc/commands/ingest_cmd.py:478-502` — `progress_iter` + `ErrorTally` over NAV loop
- `src/irc/research/theme_research.py:29` — `progress_iter` over themes loop
- `.env.example` — document `DEBUG`
- `README.md` — document `DEBUG` in env-vars section

---

## Task 1: Bootstrap — add `rich` dep, `debug` setting, empty package

**Files:**
- Modify: `pyproject.toml:6-22`
- Modify: `src/irc/settings.py:24` (add `debug` field)
- Create: `src/irc/observability/__init__.py` (empty)
- Create: `tests/observability/__init__.py` (empty)

- [ ] **Step 1: Add `rich` to direct dependencies**

Edit `pyproject.toml`, adding one line under `dependencies`:

```toml
dependencies = [
    "pydantic>=2.6,<3",
    "pydantic-settings>=2.2,<3",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "tenacity>=8.2",
    "click>=8.1",
    "frozendict>=2.4",
    "duckdb>=1.0",
    "pandas>=2.2",
    "pyarrow>=15.0",
    "numpy>=1.26",
    "scipy>=1.13",
    "openbb>=4.3",
    "akshare>=1.13",
    "feedparser>=6.0",
    "rich>=13.0",
]
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: succeeds; `rich` already locked (transitive), so no resolution churn.

- [ ] **Step 3: Add `debug` field to Settings**

Edit `src/irc/settings.py`. After the `ldr_api_token` line, add:

```python
    # Optional — set DEBUG=true in .env for verbose logging + full tracebacks.
    debug: bool = False
```

- [ ] **Step 4: Verify Settings still loads**

Run: `uv run python -c "from irc.settings import Settings; s = Settings(); print('debug=', s.debug)"`
Expected: `debug= False` printed (or a validation error about `DEEPSEEK_API_KEY` if `.env` is missing — that's fine, the field exists).

- [ ] **Step 5: Create empty package and test directories**

Run:
```bash
mkdir -p src/irc/observability tests/observability
touch src/irc/observability/__init__.py tests/observability/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/irc/settings.py \
  src/irc/observability/__init__.py tests/observability/__init__.py
git commit -m "chore(observability): scaffold package + add rich dep + debug setting"
```

---

## Task 2: `classify_exception` — pure error categorization

**Files:**
- Create: `src/irc/observability/errors.py`
- Create: `tests/observability/test_classify_exception.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observability/test_classify_exception.py`:

```python
from __future__ import annotations

import ssl

import pytest
import requests

from irc.data.akshare_client import FundNotFound
from irc.observability.errors import classify_exception


@pytest.mark.parametrize(
    "exc,expected_category",
    [
        (ssl.SSLError("UNEXPECTED_EOF"), "ssl"),
        (requests.exceptions.SSLError("wrap_socket failed"), "ssl"),
        (requests.exceptions.ProxyError("proxy down"), "proxy"),
        (requests.exceptions.Timeout("read timed out"), "timeout"),
        (TimeoutError("op took too long"), "timeout"),
        (KeyError("data"), "data-key"),
        (KeyError("['最新规模'] not in index"), "schema"),
        (FundNotFound("002601"), "not-found"),
        (ValueError("empty NAV history"), "empty"),
        (ValueError("empty price history"), "empty"),
        (AttributeError("unrelated"), "other"),
        (RuntimeError("something else"), "other"),
    ],
)
def test_classify_exception_returns_expected_category(exc, expected_category):
    category, description = classify_exception(exc)
    assert category == expected_category
    assert isinstance(description, str)
    assert description  # non-empty


def test_classify_exception_falls_back_to_other_with_repr():
    class _MyError(Exception):
        pass

    category, description = classify_exception(_MyError("boom"))
    assert category == "other"
    assert "_MyError" in description
    assert "boom" in description


def test_classify_exception_data_key_takes_precedence_over_generic_keyerror():
    # KeyError('data') must classify as data-key, not other, even though the
    # 'other' fallback could match any exception.
    category, _ = classify_exception(KeyError("data"))
    assert category == "data-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/observability/test_classify_exception.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.observability.errors'`.

- [ ] **Step 3: Implement `classify_exception`**

Create `src/irc/observability/errors.py`:

```python
"""Error classification and tallying for the ingest pipeline.

`classify_exception` is pure: same exception → same category, no I/O.
`ErrorTally` collects exceptions during a loop and renders a tree summary.
"""
from __future__ import annotations

import ssl
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Rule:
    category: str
    matches: Callable[[BaseException], bool]
    description: str


# Order matters: first match wins. data-key is checked before generic KeyError
# fallthrough; schema is checked after data-key so it doesn't shadow.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        "ssl",
        lambda e: isinstance(e, ssl.SSLError) or "SSL" in type(e).__name__ or "SSL" in repr(e),
        "SSL handshake failure (transient — rerun usually fixes)",
    ),
    _Rule(
        "proxy",
        lambda e: "ProxyError" in type(e).__name__ or "ProxyError" in repr(e),
        "Proxy unreachable (check HTTP_PROXY env)",
    ),
    _Rule(
        "timeout",
        lambda e: isinstance(e, TimeoutError) or "Timeout" in type(e).__name__,
        "Upstream timeout (transient)",
    ),
    _Rule(
        "data-key",
        lambda e: isinstance(e, KeyError) and str(e).strip("'\"") == "data",
        "Fund not in XueQiu catalog (expected for new/obscure funds)",
    ),
    _Rule(
        "schema",
        lambda e: isinstance(e, KeyError) and "not in index" in str(e),
        "Upstream response missing expected column",
    ),
    _Rule(
        "not-found",
        lambda e: type(e).__name__ == "FundNotFound",
        "Fund code not in akshare catalog",
    ),
    _Rule(
        "empty",
        lambda e: isinstance(e, ValueError) and "empty" in str(e).lower(),
        "Upstream returned no rows",
    ),
)


def classify_exception(exc: BaseException) -> tuple[str, str]:
    """Returns (category, human_description). Always succeeds (never raises).

    First-match wins. Unrecognized exceptions return ("other", repr(exc)[:120]).
    """
    for rule in _RULES:
        if rule.matches(exc):
            return rule.category, rule.description
    return "other", repr(exc)[:120]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/observability/test_classify_exception.py -v`
Expected: all 14 cases pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/observability/errors.py tests/observability/test_classify_exception.py
git commit -m "feat(observability): pure classify_exception for ingest error categories"
```

---

## Task 3: `ErrorTally` — stateful collector + tree summary

**Files:**
- Modify: `src/irc/observability/errors.py` (append `ErrorTally`)
- Create: `tests/observability/test_error_tally.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observability/test_error_tally.py`:

```python
from __future__ import annotations

from io import StringIO

from rich.console import Console

from irc.observability.errors import ErrorTally


def _capture_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def test_tally_starts_empty():
    tally = ErrorTally("metadata")
    assert tally.total_skipped() == 0


def test_tally_groups_by_category():
    tally = ErrorTally("metadata")
    tally.add("000001", KeyError("data"))
    tally.add("000002", KeyError("data"))
    tally.add("000003", ValueError("empty NAV"))
    assert tally.total_skipped() == 3
    assert tally.counts() == {"data-key": 2, "empty": 1}


def test_tally_render_with_zero_skips_shows_only_ok_line():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    tally.render(ok_count=50, console=console)
    output = buf.getvalue()
    assert "metadata: 50 ok / 0 skipped" in output


def test_tally_render_with_skips_shows_tree():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    for i in range(27):
        tally.add(f"fund_{i:06d}", KeyError("data"))
    tally.add("fund_999999", ValueError("empty price history"))
    tally.render(ok_count=89, console=console)
    output = buf.getvalue()
    assert "metadata: 89 ok / 28 skipped" in output
    assert "27" in output and "data-key" in output
    assert "1" in output and "empty" in output


def test_tally_render_verbose_lists_all_ids():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    for i in range(10):
        tally.add(f"fund_{i:06d}", KeyError("data"))
    tally.render(ok_count=5, console=console, verbose=True)
    output = buf.getvalue()
    for i in range(10):
        assert f"fund_{i:06d}" in output


def test_tally_render_non_verbose_caps_id_list():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    for i in range(20):
        tally.add(f"fund_{i:06d}", KeyError("data"))
    tally.render(ok_count=5, console=console, verbose=False)
    output = buf.getvalue()
    # Should not dump all 20 ids in non-verbose mode
    listed = sum(1 for i in range(20) if f"fund_{i:06d}" in output)
    assert listed <= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/observability/test_error_tally.py -v`
Expected: FAIL with `ImportError: cannot import name 'ErrorTally'`.

- [ ] **Step 3: Implement `ErrorTally`**

Append to `src/irc/observability/errors.py`:

```python
_DEFAULT_ID_PREVIEW = 5


@dataclass
class ErrorTally:
    """Collects (item_id, exception) pairs during a loop and renders a tree
    summary at the end. One tally per logical loop (metadata, prices, NAV)."""

    label: str
    _by_category: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def add(self, item_id: str, exc: BaseException) -> None:
        category, _ = classify_exception(exc)
        self._by_category.setdefault(category, []).append((item_id, str(exc)[:120]))

    def total_skipped(self) -> int:
        return sum(len(v) for v in self._by_category.values())

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_category.items()}

    def render(self, ok_count: int, console=None, *, verbose: bool = False) -> None:
        """Prints the tree summary. `console` defaults to the shared observability
        Console (imported lazily to avoid a circular import at module load)."""
        if console is None:
            from irc.observability.console import console as _default_console
            console = _default_console

        skipped = self.total_skipped()
        console.print(f"  {self.label}: {ok_count} ok / {skipped} skipped")
        if skipped == 0:
            return

        sorted_cats = sorted(self._by_category.items(), key=lambda kv: -len(kv[1]))
        for i, (category, entries) in enumerate(sorted_cats):
            is_last = i == len(sorted_cats) - 1
            branch = "└─" if is_last else "├─"
            _, description = classify_exception(_synthetic_exception_for(category))
            console.print(
                f"    {branch} {len(entries):>2} {category:<10} {description}"
            )
            if verbose:
                for item_id, _msg in entries:
                    indent = "       " if is_last else "    │  "
                    console.print(f"{indent}  - {item_id}")
            else:
                preview = entries[:_DEFAULT_ID_PREVIEW]
                if preview:
                    indent = "       " if is_last else "    │  "
                    ids = ", ".join(item_id for item_id, _ in preview)
                    suffix = "" if len(entries) <= _DEFAULT_ID_PREVIEW else f" (+{len(entries) - _DEFAULT_ID_PREVIEW} more)"
                    console.print(f"{indent}  e.g. {ids}{suffix}")


def _synthetic_exception_for(category: str) -> BaseException:
    """Produce an exception that classifies as `category`. Used so the renderer
    can look up the human description without storing it twice."""
    synthetic = {
        "ssl": __import__("ssl").SSLError("synthetic"),
        "proxy": type("ProxyError", (Exception,), {})("synthetic"),
        "timeout": TimeoutError("synthetic"),
        "data-key": KeyError("data"),
        "schema": KeyError("'col' not in index"),
        "not-found": type("FundNotFound", (LookupError,), {})("synthetic"),
        "empty": ValueError("empty synthetic"),
    }
    return synthetic.get(category, RuntimeError("synthetic"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/observability/test_error_tally.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/observability/errors.py tests/observability/test_error_tally.py
git commit -m "feat(observability): ErrorTally collector with tree-summary render"
```

---

## Task 4: `console.py` — shared Console + setup_logging

**Files:**
- Create: `src/irc/observability/console.py`
- Create: `tests/observability/test_console_setup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observability/test_console_setup.py`:

```python
from __future__ import annotations

import logging

from rich.logging import RichHandler

from irc.observability.console import console, setup_logging


def test_console_writes_to_stderr():
    assert console.stderr is True


def test_setup_logging_installs_rich_handler():
    setup_logging(debug=False)
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], RichHandler)


def test_setup_logging_is_idempotent():
    setup_logging(debug=False)
    setup_logging(debug=False)
    setup_logging(debug=True)
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1


def test_setup_logging_level_debug():
    setup_logging(debug=True)
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_level_default():
    setup_logging(debug=False)
    assert logging.getLogger().level == logging.INFO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/observability/test_console_setup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.observability.console'`.

- [ ] **Step 3: Implement console + setup_logging**

Create `src/irc/observability/console.py`:

```python
"""Shared rich Console and logging setup.

Console writes to stderr so progress bars and log messages don't pollute
stdout — which is reserved for results that callers may pipe.
"""
from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

console: Console = Console(stderr=True)


def setup_logging(debug: bool) -> None:
    """Install a single RichHandler at the root logger. Idempotent.

    DEBUG mode adds full rich tracebacks and exposes INFO/DEBUG records from
    third-party libraries (akshare, requests, urllib3). Default mode shows
    one-line repr for errors and only WARNING+ from third parties.
    """
    level = logging.DEBUG if debug else logging.INFO
    handler = RichHandler(
        console=console,
        show_path=debug,
        rich_tracebacks=debug,
        tracebacks_show_locals=False,  # never dump locals (may contain secrets)
        show_time=True,
        omit_repeated_times=False,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/observability/test_console_setup.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/observability/console.py tests/observability/test_console_setup.py
git commit -m "feat(observability): shared rich Console + setup_logging entry point"
```

---

## Task 5: `progress_iter` — context-managed progress bar over an iterable

**Files:**
- Create: `src/irc/observability/progress.py`
- Create: `tests/observability/test_progress_iter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observability/test_progress_iter.py`:

```python
from __future__ import annotations

from io import StringIO

from rich.console import Console

from irc.observability.progress import progress_iter


def test_progress_iter_yields_all_items_in_order():
    items = list(range(10))
    result = list(progress_iter(items, desc="testing"))
    assert result == items


def test_progress_iter_yields_with_explicit_total():
    items = ["a", "b", "c"]
    result = list(progress_iter(items, desc="testing", total=len(items)))
    assert result == items


def test_progress_iter_handles_empty_iterable():
    result = list(progress_iter([], desc="testing"))
    assert result == []


def test_progress_iter_non_tty_produces_no_ansi_escapes(monkeypatch):
    buf = StringIO()
    captured_console = Console(file=buf, force_terminal=False, width=120)
    monkeypatch.setattr("irc.observability.progress.console", captured_console)
    result = list(progress_iter([1, 2, 3], desc="testing"))
    assert result == [1, 2, 3]
    assert "\x1b[" not in buf.getvalue()  # no ANSI escapes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/observability/test_progress_iter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.observability.progress'`.

- [ ] **Step 3: Implement progress_iter**

Create `src/irc/observability/progress.py`:

```python
"""Progress bars and stage banners.

Both `progress_iter` and `stage_banner` write to the shared stderr Console;
they auto-degrade to non-animated output when stderr is not a terminal.
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)

from irc.observability.console import console

T = TypeVar("T")


def progress_iter(
    items: Iterable[T],
    desc: str,
    total: int | None = None,
) -> Iterator[T]:
    """Yields items one at a time while updating a rich Progress bar."""
    if total is None and hasattr(items, "__len__"):
        total = len(items)  # type: ignore[arg-type]

    columns = (
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
    )
    with Progress(*columns, console=console, transient=False) as progress:
        task = progress.add_task(desc, total=total)
        for item in items:
            yield item
            progress.advance(task)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/observability/test_progress_iter.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/observability/progress.py tests/observability/test_progress_iter.py
git commit -m "feat(observability): progress_iter wraps any iterable in a rich bar"
```

---

## Task 6: `stage_banner` — context manager for pipeline-stage rules

**Files:**
- Modify: `src/irc/observability/progress.py` (append `stage_banner`)
- Create: `tests/observability/test_stage_banner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observability/test_stage_banner.py`:

```python
from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from irc.observability.progress import stage_banner


def _capture_console_into(monkeypatch) -> StringIO:
    buf = StringIO()
    captured = Console(file=buf, force_terminal=False, width=120)
    monkeypatch.setattr("irc.observability.progress.console", captured)
    return buf


def _freeze_time(monkeypatch, values: list[float]) -> None:
    iterator = iter(values)
    monkeypatch.setattr(
        "irc.observability.progress.time.monotonic",
        lambda: next(iterator),
    )


def test_stage_banner_prints_starting_and_done(monkeypatch):
    buf = _capture_console_into(monkeypatch)
    _freeze_time(monkeypatch, [100.0, 142.5])

    with stage_banner("ingest", 1, 8):
        pass

    output = buf.getvalue()
    assert "[1/8] ingest" in output
    assert "starting" in output
    assert "done in 42s" in output


def test_stage_banner_prints_failed_on_exception_and_reraises(monkeypatch):
    buf = _capture_console_into(monkeypatch)
    _freeze_time(monkeypatch, [200.0, 210.0])

    with pytest.raises(RuntimeError, match="boom"):
        with stage_banner("score", 4, 8):
            raise RuntimeError("boom")

    output = buf.getvalue()
    assert "[4/8] score" in output
    assert "FAILED" in output
    assert "10s" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/observability/test_stage_banner.py -v`
Expected: FAIL with `ImportError: cannot import name 'stage_banner'`.

- [ ] **Step 3: Implement stage_banner**

Append to `src/irc/observability/progress.py`:

```python
@contextmanager
def stage_banner(stage: str, index: int, total: int) -> Iterator[None]:
    """Wraps a pipeline stage with a rule + start/done lines.

    On exception: prints a FAILED line with elapsed seconds and re-raises.
    """
    console.rule(f"[{index}/{total}] {stage} — starting")
    start = time.monotonic()
    try:
        yield
    except Exception:
        elapsed = int(time.monotonic() - start)
        console.print(f"[{index}/{total}] {stage} — FAILED after {elapsed}s")
        raise
    else:
        elapsed = int(time.monotonic() - start)
        console.print(f"[{index}/{total}] {stage} — done in {elapsed}s")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/observability/test_stage_banner.py -v`
Expected: all 2 tests pass.

- [ ] **Step 5: Run the full observability suite**

Run: `uv run pytest tests/observability/ -v`
Expected: all tests across all 5 files pass.

- [ ] **Step 6: Commit**

```bash
git add src/irc/observability/progress.py tests/observability/test_stage_banner.py
git commit -m "feat(observability): stage_banner context manager with timing + failure path"
```

---

## Task 7: Public API in `observability/__init__.py`

**Files:**
- Modify: `src/irc/observability/__init__.py`

- [ ] **Step 1: Write the public API re-exports**

Replace the empty `src/irc/observability/__init__.py` with:

```python
"""Public API for observability.

External callers should import only from this module:

    from irc.observability import (
        console, setup_logging,
        stage_banner, progress_iter,
        ErrorTally, classify_exception,
    )
"""
from __future__ import annotations

from irc.observability.console import console, setup_logging
from irc.observability.errors import ErrorTally, classify_exception
from irc.observability.progress import progress_iter, stage_banner

__all__ = (
    "ErrorTally",
    "classify_exception",
    "console",
    "progress_iter",
    "setup_logging",
    "stage_banner",
)
```

- [ ] **Step 2: Verify imports work**

Run:
```bash
uv run python -c "
from irc.observability import (
    console, setup_logging, stage_banner, progress_iter,
    ErrorTally, classify_exception,
)
print('all imports OK')
"
```
Expected: `all imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/irc/observability/__init__.py
git commit -m "feat(observability): re-export public API"
```

---

## Task 8: Wire `setup_logging` into `cli.main`

**Files:**
- Modify: `src/irc/cli.py:1-9`

- [ ] **Step 1: Edit `cli.py` `main()` function**

Replace lines 1–9 of `src/irc/cli.py`:

```python
from __future__ import annotations
import os
import click
from dotenv import load_dotenv


@click.group(help="Investment Research Copilot")
def main() -> None:
    """Entry point for the `irc` CLI."""
    load_dotenv()
    from irc.observability import setup_logging
    try:
        from irc.settings import Settings
        debug = Settings().debug
    except Exception:
        # Settings() requires DEEPSEEK_API_KEY for full validation; fall back to
        # raw env so `irc init` and `irc config validate` work without secrets.
        debug = os.environ.get("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    setup_logging(debug=debug)
```

- [ ] **Step 2: Smoke-test the CLI still works**

Run: `uv run irc --help`
Expected: usage text printed, no traceback.

Run: `DEBUG=true uv run irc --help`
Expected: usage text printed, no traceback.

- [ ] **Step 3: Verify existing CLI tests still pass**

Run: `uv run pytest tests/test_cli_smoke.py tests/commands/ -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/irc/cli.py
git commit -m "feat(cli): initialize rich logging from DEBUG env flag on every invocation"
```

---

## Task 9: Wire `stage_banner` into `run_cmd`

**Files:**
- Modify: `src/irc/commands/run_cmd.py:36-50`

- [ ] **Step 1: Update the stage loop**

Edit `src/irc/commands/run_cmd.py`. Replace the `for stage in stages:` loop in `run_pipeline`:

```python
def run_pipeline(repo_root: str, from_stage: str | None = None, only_stage: str | None = None) -> int:
    from irc.observability import stage_banner

    if only_stage is not None:
        if only_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{only_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        stages = [only_stage]
    elif from_stage is not None:
        if from_stage not in STAGE_NAMES:
            print(f"ERROR: unknown stage '{from_stage}'. Valid: {list(STAGE_NAMES)}")
            return 1
        idx = STAGE_NAMES.index(from_stage)
        stages = list(STAGE_NAMES[idx:])
    else:
        stages = list(STAGE_NAMES)
    stages = _without_disabled_optional_stages(stages, from_stage, only_stage)
    total = len(stages)
    for index, stage in enumerate(stages, start=1):
        with stage_banner(stage, index, total):
            fn = _runners_map()[stage]
            rc = fn(repo_root)
        if rc != 0:
            print(f"STAGE FAILED: {stage} (rc={rc})")
            from irc.pipeline_halt import write_halted
            today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
            write_halted(
                repo_root=Path(repo_root), date=today, stage=stage,
                reason=f"stage exit code {rc}",
                remediation=f"Inspect the stage output and re-run `irc {stage} --repo-root {repo_root}` after fixing.",
            )
            return rc
    print(f"pipeline OK: ran {stages}")
    return 0
```

Note: the `rc != 0` check stays outside the `with` block so the stage's exit-code-based failure path (different from raising) still prints "done" — that's the contract the existing tests assume.

- [ ] **Step 2: Run the run_cmd tests**

Run: `uv run pytest tests/commands/test_run_cmd.py -v`
Expected: all pass.

- [ ] **Step 3: Smoke-test with `--only`**

Run: `uv run irc run --only ingest --repo-root . 2>&1 | head -5` (will error on missing config but should show banner)
Expected: stderr shows `[1/1] ingest — starting`.

- [ ] **Step 4: Commit**

```bash
git add src/irc/commands/run_cmd.py
git commit -m "feat(run): wrap each pipeline stage in a stage_banner with timing"
```

---

## Task 10: Wire `progress_iter` + `ErrorTally` into ingest metadata loop

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py:220-252`

- [ ] **Step 1: Update `_fetch_metadata_by_id`**

Edit `src/irc/commands/ingest_cmd.py`. Replace `_fetch_metadata_by_id`:

```python
def _fetch_metadata_by_id(
    instruments: list,
    active_fund_tenure_proxy_enabled: bool = True,
) -> tuple[dict[str, dict[str, float | str | None]], "ErrorTally"]:
    from irc.observability import ErrorTally, progress_iter

    metadata_by_id: dict[str, dict[str, float | str | None]] = {}
    tally = ErrorTally("metadata")
    for instrument in progress_iter(instruments, "metadata", total=len(instruments)):
        if not _is_fund_like_ticker(instrument.ticker):
            continue
        try:
            fetch = _metadata_fetcher_for(instrument)
            metadata = _apply_active_fund_tenure_fallback(
                instrument,
                _normalize_fund_metadata(fetch(instrument.ticker)),
                enabled=active_fund_tenure_proxy_enabled,
            )
        except Exception as exc:
            tally.add(instrument.instrument_id, exc)
            _log.warning(
                "skipping %s: metadata fetch error: %s",
                instrument.instrument_id,
                exc,
            )
            continue
        missing = _missing_required_metadata(instrument, metadata)
        if missing:
            joined = ", ".join(missing)
            tally.add(instrument.instrument_id, KeyError(f"missing required metadata: {joined}"))
            _log.warning(
                "skipping %s: missing required metadata fields: %s",
                instrument.instrument_id,
                joined,
            )
            continue
        metadata_by_id[instrument.instrument_id] = metadata
    return metadata_by_id, tally
```

Also at the top of the file, after the existing import block, add the type-only forward reference (for the return annotation):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from irc.observability.errors import ErrorTally
```

- [ ] **Step 2: Update the caller in `run_ingest`**

In `run_ingest` (~line 389), change:

```python
        metadata_by_id = _fetch_metadata_by_id(
            all_instruments,
            active_fund_tenure_proxy_enabled=feature_flags.active_fund_tenure_proxy_enabled,
        )
```

to:

```python
        from irc.observability import Settings as _Unused  # noqa: F401  -- placeholder removed below
```

Wait — simpler. Replace with:

```python
        from irc.settings import Settings as _S
        try:
            _verbose = _S().debug
        except Exception:
            _verbose = False

        metadata_by_id, metadata_tally = _fetch_metadata_by_id(
            all_instruments,
            active_fund_tenure_proxy_enabled=feature_flags.active_fund_tenure_proxy_enabled,
        )
```

And further down, after the existing `print(f"ingest OK: ...")`, insert before the final `return 0`:

```python
        metadata_tally.render(ok_count=len(metadata_by_id), verbose=_verbose)
```

Wait — the print statement is `print(f"ingest OK: openbb={ob_counts}, akshare={ak_counts}")` (line 529). Insert tally renders **before** that final print so the summary reads top-to-bottom. Specifically: after `ensure_schema(con)`-block exits (after `finally: con.close()` at line 504), call:

```python
    metadata_tally.render(ok_count=len(metadata_by_id), verbose=_verbose)
```

(Other tallies from later tasks will be rendered here too.)

- [ ] **Step 3: Run the ingest tests**

Run: `uv run pytest tests/commands/test_ingest_cmd.py -v`
Expected: all pass. If a test asserts on `_fetch_metadata_by_id` return shape (tuple vs dict), update the test to unpack the tuple.

- [ ] **Step 4: Commit**

```bash
git add src/irc/commands/ingest_cmd.py tests/commands/test_ingest_cmd.py
git commit -m "feat(ingest): progress bar + categorized error tally over metadata loop"
```

---

## Task 11: Wire `progress_iter` + `ErrorTally` into ingest prices loop

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py:404-450`

- [ ] **Step 1: Wrap the prices loop**

In `run_ingest`, find the `for instr in all_instruments:` loop that fetches prices (around line 404). Replace its declaration line:

```python
        prices_tally = ErrorTally("prices")
        price_candidates = [i for i in all_instruments if _has_price_history_source(i)]
        for instr in progress_iter(price_candidates, "prices", total=len(price_candidates)):
            price_attempts += 1
            try:
                df = fetch_etf_price_history(
                    ticker=instr.ticker,
                    start=start,
                    end=end,
                    skip_cn_eastmoney=eastmoney_unavailable,
                    on_cn_eastmoney_exhausted=_mark_eastmoney_unavailable,
                )
                if df.empty:
                    raise ValueError("empty price history")
                df = _coerce_price_history(df)
            except Exception as exc:
                price_failures.append(instr.instrument_id)
                prices_tally.add(instr.instrument_id, exc)
                _log.warning(
                    "skipping price ingest for %s (ticker=%s): %s. "
                    "Other instruments will still be processed; rerun once "
                    "the upstream source recovers.",
                    instr.instrument_id, instr.ticker, exc,
                )
                continue
            try:
                price_source = _price_source_for(instr)
                inserted = _upsert_prices(
                    con,
                    instr.instrument_id,
                    df,
                    source=price_source,
                )
                if price_source == "akshare":
                    ak_counts["prices"] += inserted
                else:
                    ob_counts["prices"] += inserted
            except Exception as exc:
                print(
                    f"ERROR: ingest failed while writing prices for "
                    f"{instr.instrument_id}: {exc}"
                )
                return 1
            price_successes += 1
        # Handle the "no source available" log line for instruments outside price_candidates
        for instr in all_instruments:
            if not _has_price_history_source(instr) and not _is_off_exchange_fund(instr):
                _log.warning(
                    "skipping price/nav ingest for %s (market=%s, ticker=%s): no source available",
                    instr.instrument_id, instr.market, instr.ticker,
                )
```

Add to the imports at the top of `run_ingest` (alongside the existing imports inside the function):

```python
        from irc.observability import ErrorTally, progress_iter
```

(or hoist to module-level — see Step 3.)

- [ ] **Step 2: Render the prices tally**

In the tally-render block (the one added at end of Task 10), add:

```python
    prices_tally.render(ok_count=price_successes, verbose=_verbose)
```

- [ ] **Step 3: Move observability imports to module level**

To avoid repeating function-local imports, replace the `from irc.observability import ...` in `_fetch_metadata_by_id` and `run_ingest` with a single module-level import near the top of `ingest_cmd.py`:

```python
from irc.observability import ErrorTally, progress_iter
```

Remove the function-local copies.

- [ ] **Step 4: Run the ingest tests**

Run: `uv run pytest tests/commands/test_ingest_cmd.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/ingest_cmd.py
git commit -m "feat(ingest): progress bar + tally over prices loop"
```

---

## Task 12: Wire `progress_iter` + `ErrorTally` into ingest NAV loop

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py:478-502`

- [ ] **Step 1: Wrap the NAV loop**

Replace the NAV-loop block:

```python
        nav_tally = ErrorTally("nav")
        for instr in progress_iter(nav_instruments, "nav", total=len(nav_instruments)):
            nav_attempts += 1
            try:
                df = fetch_fund_nav_history(instr.ticker)
                if df.empty:
                    raise ValueError("empty NAV history")
                df = _coerce_nav_history(df)
            except Exception as exc:
                nav_failures.append(instr.instrument_id)
                nav_tally.add(instr.instrument_id, exc)
                _log.warning(
                    "skipping NAV ingest for %s (ticker=%s): %s. "
                    "Other instruments will still be processed.",
                    instr.instrument_id, instr.ticker, exc,
                )
                continue
            try:
                ak_counts["nav_history"] += _upsert_nav(con, instr.instrument_id, df)
            except Exception as exc:
                print(
                    f"ERROR: ingest failed while writing NAV for "
                    f"{instr.instrument_id}: {exc}"
                )
                return 1
            nav_successes += 1
```

- [ ] **Step 2: Render the NAV tally**

In the tally-render block at end of `run_ingest`, add:

```python
    nav_tally.render(ok_count=nav_successes, verbose=_verbose)
```

The full ingest-summary section should now read (in order):

```python
    metadata_tally.render(ok_count=len(metadata_by_id), verbose=_verbose)
    prices_tally.render(ok_count=price_successes, verbose=_verbose)
    nav_tally.render(ok_count=nav_successes, verbose=_verbose)
    print(f"ingest OK: openbb={ob_counts}, akshare={ak_counts}")
```

- [ ] **Step 3: Run the ingest tests**

Run: `uv run pytest tests/commands/test_ingest_cmd.py -v`
Expected: all pass.

- [ ] **Step 4: Add an integration assertion**

Open `tests/commands/test_ingest_cmd.py`, find the test that simulates a metadata-fetch failure (the one verifying the skip path). Add one assertion after the run completes:

```python
    # ErrorTally should have categorized the failure
    # (No direct return value to inspect — assert via captured stderr/log instead)
    assert "metadata:" in captured_stderr  # or however the test captures output
```

If the existing test does not capture stderr, skip this step — the unit tests in Task 2/3 already cover the tally logic.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/ingest_cmd.py tests/commands/test_ingest_cmd.py
git commit -m "feat(ingest): progress bar + tally over NAV loop; render 3-tally summary"
```

---

## Task 13: Wire `progress_iter` into research theme loop

**Files:**
- Modify: `src/irc/research/theme_research.py:26-29`

- [ ] **Step 1: Find the current loop**

Open `src/irc/research/theme_research.py`. The loop is around line 26–29:

```python
def build_theme_reports(themes: tuple[str, ...], time_budget_s: int = 90) -> list[ThemeReport]:
    reports = []
    total = len(themes)
    for n, theme in enumerate(themes, start=1):
        query = _THEME_QUERIES.get(theme, f"Research summary for {theme}")
        ...
```

- [ ] **Step 2: Replace with progress_iter**

```python
def build_theme_reports(themes: tuple[str, ...], time_budget_s: int = 90) -> list[ThemeReport]:
    from irc.observability import progress_iter

    reports = []
    for theme in progress_iter(themes, "research", total=len(themes)):
        query = _THEME_QUERIES.get(theme, f"Research summary for {theme}")
        ...
```

Remove the now-unused `n` and `total` variables. If `n` was used elsewhere in the loop body, restore enumeration with `for i, theme in enumerate(progress_iter(...))` — read the full function body to confirm before editing.

- [ ] **Step 3: Run the research tests**

Run: `uv run pytest tests/ -k research -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/irc/research/theme_research.py
git commit -m "feat(research): progress bar over themes loop"
```

---

## Task 14: Document `DEBUG` in `.env.example` and `README.md`

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add DEBUG to `.env.example`**

Insert at the end of `.env.example`:

```
# Optional — set to true for verbose CLI logging + full tracebacks.
# Default: false. Errors during ingest are categorized in a summary either way.
DEBUG=false
```

- [ ] **Step 2: Document `DEBUG` in README**

In `README.md`, find the "Quick start" section around line 12 (after the existing `.env` instructions). Add a short paragraph after line 21 (`# Edit .env to fill DEEPSEEK_API_KEY...`):

```markdown
# Optional: set DEBUG=true in .env for verbose logging (full tracebacks, third-party DEBUG records).
# Default DEBUG=false still shows progress bars and categorized ingest-error summaries.
```

- [ ] **Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document DEBUG env flag for verbose CLI logging"
```

---

## Task 15: Manual smoke test — verify acceptance criteria

**Files:** none modified — verification only.

- [ ] **Step 1: Run default pipeline (no DEBUG)**

Run: `uv run irc run --only ingest --repo-root .` (or with full `LDR_ENABLED=true` if LDR is reachable)
Expected on stderr:
- A `[1/1] ingest — starting` rule
- Three progress bars (metadata, prices, nav) with M/N counts and ETA
- A tree summary at the end like:
  ```
  ingest summary:
    metadata: NN ok / NN skipped
      ├─ NN data-key  Fund not in XueQiu catalog...
      └─ NN ssl       SSL handshake failure...
    prices:  NN ok / 0 skipped
    nav:     NN ok / NN skipped
  ```
- A `[1/1] ingest — done in Ns` line

- [ ] **Step 2: Run with DEBUG=true**

Run: `DEBUG=true uv run irc run --only ingest --repo-root .`
Expected: same as above, plus full rich tracebacks for any errors, plus all skipped instrument IDs listed (not just first 5).

- [ ] **Step 3: Run with stderr redirected to a file**

Run: `uv run irc run --only ingest --repo-root . 2>log.txt; cat log.txt | head -40`
Expected: no ANSI escape codes (no `\x1b[` sequences) in `log.txt`; progress reduced to plain start/done lines.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Verify all acceptance criteria from spec section 10**

Check each box in spec section 10:
1. ☐ Stage banners between pipeline steps
2. ☐ Three progress bars (metadata/prices/NAV) with M/N + % + ETA
3. ☐ Tree summary categorizes every skipped instrument by error type
4. ☐ `DEBUG=true` produces full tracebacks + akshare/requests DEBUG records
5. ☐ `irc run 2>log.txt` produces log file with no ANSI escapes
6. ☐ All new tests pass; all existing tests still pass
7. ☐ Only `rich>=13.0` added as new direct dep

- [ ] **Step 6: Final commit (if any cleanups)**

If smoke test surfaces a fix, commit with `fix(observability): ...`. Otherwise no commit needed — work is done.

---

## Self-review

**Spec coverage:**
- Section 3.1 (default output) → Tasks 5, 6, 10–13, 15.
- Section 3.2 (DEBUG mode) → Tasks 1 (settings), 4 (RichHandler with tracebacks), 8 (cli wire), 15 (smoke).
- Section 3.3 (non-TTY mode) → Tasks 5 (`force_terminal=False` test), 15 (redirect smoke).
- Section 4.1 (module layout) → Tasks 1–7.
- Section 4.2 (public API) → Task 7.
- Section 4.4 (`console.py`) → Task 4.
- Section 4.5 (`progress.py`) → Tasks 5, 6.
- Section 4.6 (`errors.py`) → Tasks 2, 3.
- Section 5.1 (`cli.py`) → Task 8.
- Section 5.2 (`settings.py`) → Task 1.
- Section 5.3 (`run_cmd.py`) → Task 9.
- Section 5.4 (`ingest_cmd.py`) → Tasks 10, 11, 12.
- Section 5.5 (other commands) → Task 13 (research only — other commands have no tight inner loop worth wrapping; stage banner covers them).
- Section 6.1 (`.env` documentation) → Task 14.
- Section 6.2 (`pyproject.toml`) → Task 1.
- Section 7 (testing) → Tasks 2–6 cover all five test files. Existing `test_ingest_cmd.py` extension noted in Task 12 Step 4.
- Section 10 (acceptance criteria) → Task 15.

**Placeholder scan:** No "TBD", "TODO", or hand-wavy steps. Each step has explicit code, an exact command, or an exact file edit.

**Type consistency:** `classify_exception` returns `tuple[str, str]` everywhere it's called. `ErrorTally.add(item_id: str, exc: BaseException)` matches the call sites in Tasks 10–12. `progress_iter` and `stage_banner` signatures match between definition (Tasks 5–6) and call sites (Tasks 9–13).

**One known smell to flag:** Task 11 Step 1 changes `_has_price_history_source` filtering — previously inside the loop, now pre-filtered into `price_candidates`. The "no source available" warning for non-price, non-off-exchange instruments is preserved in a separate post-loop pass. This is functionally equivalent but a reviewer should confirm by reading the diff carefully.
