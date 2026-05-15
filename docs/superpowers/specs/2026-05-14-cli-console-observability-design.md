# CLI Console Observability — Design

**Date:** 2026-05-14
**Status:** Approved for implementation
**Owner:** Harry
**Scope:** Add progress visibility and categorized error reporting to the `irc` CLI; introduce a `DEBUG=true` flag in `.env` for verbose output.

---

## 1. Problem

`LDR_ENABLED=true uv run irc run` produces output like:

```
skipping 002601: metadata fetch error: HTTPSConnectionPool(host='fundf10.eastmoney.com', port=443): Max retries exceeded with url: /jjfl_002601.html (Caused by SSLError(...))
skipping 006369: metadata fetch error: 'data'
skipping 012751: metadata fetch error: 'data'
... 30+ more lines ...
skipping macro series DXY: HTTPSConnectionPool(...) ProxyError(...)
```

Three pain points:

1. **No progress** — the user cannot tell whether the run is 5% or 95% through, or which stage of the 8-stage pipeline is currently executing.
2. **Undifferentiated errors** — every line says "skipping X: error: ...". The user cannot tell which errors are transient (rerun fixes), which are expected (fund not in upstream catalog), and which need action (proxy misconfiguration).
3. **No verbosity control** — no way to ask for full tracebacks when debugging, and no way to silence the chatter for normal runs.

## 2. Non-goals

- **No retry behavior changes.** SSL/timeout retries stay where they are. (Categorization may surface that retry needs tuning later, but that is a separate piece of work.)
- **No fixes to upstream data-source coverage.** The XueQiu coverage gap producing 27 `'data'` KeyErrors is real but out of scope. The summary will surface it clearly so the user can decide later.
- **No per-item success lines in DEBUG.** Bars cover progress. DEBUG only unlocks tracebacks and SDK-level logging chatter.
- **No new dependency installs beyond what is already locked.** `rich` and `tqdm` are already transitive deps of `openbb`; we add `rich` explicitly to `pyproject.toml`.

## 3. User-visible behavior

### 3.1 Default mode (`DEBUG=false` or unset)

Stage banners between pipeline steps:

```
──────────── [1/8] ingest — starting ────────────
Fetching metadata  ████████████░░░░░░░░  45/120 [37%] ETA 0:01:12  cn_fund_012345
... bars for prices and NAV loops as well ...
ingest summary:
  metadata: 89 ok / 31 skipped
    ├─ 27 data-key       fund not in XueQiu catalog (expected for new/obscure funds)
    ├─  2 schema         upstream response missing expected column
    ├─  1 ssl            SSL handshake failure (transient — rerun usually fixes)
    └─  1 other          AttributeError: 'NoneType' has no attribute 'strip'
  prices:   42 ok / 0 skipped
  nav:     115 ok / 3 skipped
    └─  3 timeout        upstream timeout (transient)
[1/8] ingest — done in 42s
──────────── [2/8] research — starting ────────────
...
```

### 3.2 Debug mode (`DEBUG=true` in `.env`)

Same as above, plus:

- Full rich-formatted tracebacks for every error (not just the one-line `repr`)
- Akshare / requests / urllib3 `INFO` and `DEBUG` log records become visible
- Category summary expands to list **all** skipped instrument IDs (not just first 5)
- Stage banners include current process PID and total elapsed time so far

### 3.3 Non-TTY mode (CI / log file)

When stderr is not a terminal (e.g. `irc run 2>log.txt`):

- Progress bars collapse to a single `metadata: 1/120 starting ... 120/120 done (89 ok, 31 skipped)` line
- No ANSI escape codes
- Stage banners use plain `=====` rules instead of rich box-drawing
- Everything else is unchanged

## 4. Architecture

### 4.1 Module layout

```
src/irc/observability/
├── __init__.py         # re-exports public API
├── console.py          # shared Console + setup_logging(debug)
├── progress.py         # progress_iter, stage_banner
└── errors.py           # ErrorTally + classify_exception (pure)
```

### 4.2 Public API

```python
from irc.observability import (
    console,              # rich.console.Console singleton, writes to stderr
    setup_logging,        # setup_logging(debug: bool) -> None
    stage_banner,         # @contextmanager (stage_name, index, total)
    progress_iter,        # progress_iter(items, desc, total=None) -> Iterator
    ErrorTally,           # ErrorTally(label).add(item_id, exc).render(ok_count)
    classify_exception,   # pure: classify_exception(exc) -> (category, description)
)
```

Nothing else from the package is exported. Internal modules can be refactored without breaking callers.

### 4.3 Data flow

```
.env (DEBUG=true)
   │
   ▼
Settings(debug=True)  ──► cli.main() ──► setup_logging(debug=True)
                                              │
                                              ▼
                              logging.root has RichHandler(level=DEBUG)
                                              │
                                              ▼
            ┌─────────────── stage_banner("ingest", 1, 8) ────────────────┐
            │                                                              │
            │   for item in progress_iter(instruments, "metadata"):        │
            │       try:    fetch_metadata(item)                            │
            │       except: tally.add(item.id, exc)  ──► classify_exception │
            │                                                              │
            │   tally.render(ok_count)  ──► console.print(tree)             │
            └──────────────────────────────────────────────────────────────┘
```

### 4.4 `console.py`

Single rich `Console` instance writing to stderr. Used by progress bars, banners, and the rich `RichHandler` for logging. Stdout is reserved for results (final `ingest OK: ...`, decision reports, etc.) so users can pipe results without losing the summary.

```python
from rich.console import Console
from rich.logging import RichHandler
import logging

console = Console(stderr=True)

def setup_logging(debug: bool) -> None:
    """Install a single RichHandler at root level. Idempotent (force=True)."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(
            console=console,
            show_path=debug,
            rich_tracebacks=debug,
            tracebacks_show_locals=False,
        )],
        force=True,
    )
```

### 4.5 `progress.py`

```python
from contextlib import contextmanager
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, MofNCompleteColumn
import time

@contextmanager
def stage_banner(stage: str, index: int, total: int) -> Iterator[None]:
    console.rule(f"[{index}/{total}] {stage} — starting")
    start = time.monotonic()
    try:
        yield
    except Exception:
        console.print(f"[{index}/{total}] {stage} — FAILED after {int(time.monotonic() - start)}s")
        raise
    else:
        console.print(f"[{index}/{total}] {stage} — done in {int(time.monotonic() - start)}s")


def progress_iter(items, desc: str, total: int | None = None):
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

When `console.is_terminal` is `False`, rich automatically uses a non-animated fallback — no escape codes, single update line.

### 4.6 `errors.py`

```python
import ssl
from dataclasses import dataclass, field
from typing import Callable

@dataclass(frozen=True)
class _Rule:
    category: str
    matches: Callable[[BaseException], bool]
    description: str

_RULES: tuple[_Rule, ...] = (
    _Rule("ssl",       lambda e: isinstance(e, ssl.SSLError) or "SSL" in repr(e),
                       "SSL handshake failure (transient — rerun usually fixes)"),
    _Rule("proxy",     lambda e: "ProxyError" in repr(e),
                       "Proxy unreachable (check HTTP_PROXY env)"),
    _Rule("timeout",   lambda e: isinstance(e, TimeoutError) or "Timeout" in type(e).__name__,
                       "Upstream timeout (transient)"),
    _Rule("data-key",  lambda e: isinstance(e, KeyError) and str(e) == "'data'",
                       "Fund not in XueQiu catalog (expected for new/obscure funds)"),
    _Rule("schema",    lambda e: isinstance(e, KeyError) and "not in index" in str(e),
                       "Upstream response missing expected column"),
    _Rule("not-found", lambda e: type(e).__name__ == "FundNotFound",
                       "Fund code not in akshare catalog"),
    _Rule("empty",     lambda e: isinstance(e, ValueError) and "empty" in str(e),
                       "Upstream returned no rows"),
)

def classify_exception(exc: BaseException) -> tuple[str, str]:
    """Pure. Returns (category, human_description). Always succeeds.
    First-match wins; falls back to ('other', repr(exc))."""
    for rule in _RULES:
        if rule.matches(exc):
            return rule.category, rule.description
    return "other", repr(exc)[:120]


@dataclass
class ErrorTally:
    label: str
    _by_category: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def add(self, item_id: str, exc: BaseException) -> None:
        category, _ = classify_exception(exc)
        self._by_category.setdefault(category, []).append((item_id, str(exc)[:120]))

    def total_skipped(self) -> int:
        return sum(len(v) for v in self._by_category.values())

    def render(self, ok_count: int, *, verbose: bool = False) -> None:
        """Prints the tree summary to console. verbose=True (DEBUG mode) lists all
        instrument IDs per category instead of capping at 5."""
        # ... implementation: console.print() the tree shown in section 3.1
```

`classify_exception` and the rule table are pure — easy to test exhaustively. `ErrorTally` is a tiny state collector with one observable side effect (`render`).

## 5. Call-site integration

### 5.1 `cli.py`

One change: `main()` calls `setup_logging` after `load_dotenv`.

```python
@click.group(help="Investment Research Copilot")
def main() -> None:
    load_dotenv()
    from irc.observability import setup_logging
    from irc.settings import Settings
    try:
        debug = Settings().debug
    except Exception:
        # Settings() requires DEEPSEEK_API_KEY for full validation; fall back to
        # raw env so `irc init` and `irc config validate` still work without secrets.
        debug = os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}
    setup_logging(debug=debug)
```

### 5.2 `settings.py`

One field added:

```python
debug: bool = False  # DEBUG=true in .env enables verbose logging
```

### 5.3 `run_cmd.py`

The `for stage in stages:` loop wraps each call in `stage_banner`:

```python
for index, stage in enumerate(stages, start=1):
    with stage_banner(stage, index, len(stages)):
        rc = _runners_map()[stage](repo_root)
        if rc != 0:
            # existing halt-marker logic stays
            ...
            return rc
```

### 5.4 `ingest_cmd.py`

Three loops gain `progress_iter` + a shared `ErrorTally` per loop label. The existing `try/except Exception as exc:` blocks each gain one new line:

```python
metadata_tally = ErrorTally("metadata")
for instrument in progress_iter(all_instruments, "metadata", total=len(all_instruments)):
    if not _is_fund_like_ticker(instrument.ticker):
        continue
    try:
        ...
    except Exception as exc:
        metadata_tally.add(instrument.instrument_id, exc)
        _log.warning("skipping %s: metadata fetch error: %s", instrument.instrument_id, exc)
        continue
    ...

metadata_tally.render(ok_count=len(metadata_by_id))
```

Same pattern for prices and NAV loops.

### 5.5 Other command files (`discover_cmd.py`, `score_cmd.py`, `allocate_cmd.py`, `memo_cmd.py`, `research_cmd.py`)

Each gets one `progress_iter` wrapping its main loop. If a command has no inner loop (just sequential calls), it stays unchanged — the stage banner from `run_cmd.py` is enough.

For `research_cmd.py` specifically: wrap the per-theme loop with `progress_iter(themes, "research", total=7)`. LDR calls themselves are slow (minutes each), so a bar plus the current theme label is the right granularity.

## 6. Configuration

### 6.1 `.env` additions

```
# Optional — set DEBUG=true to enable verbose logging and full tracebacks.
DEBUG=false
```

Documented in `README.md` under the existing environment-variables section.

### 6.2 `pyproject.toml`

`rich` is currently transitive only. Add explicit:

```toml
dependencies = [
    ...
    "rich>=13.0",
]
```

No version bump required for any other dependency.

## 7. Testing

Six small test files under `tests/observability/`. All fast, all deterministic.

| File | What it covers | Approach |
|---|---|---|
| `test_classify_exception.py` | Every category rule + fallback + order-sensitivity | Pure parametrized table |
| `test_error_tally.py` | add(), total_skipped(), render() output | StringIO capture + golden string |
| `test_console_setup.py` | setup_logging is idempotent; level matches debug flag | `caplog` + handler inspection |
| `test_progress_iter.py` | Yields all items in order; non-TTY produces no ANSI | Force `console.is_terminal=False` |
| `test_stage_banner.py` | Success path prints "done in Ns"; failure path prints "FAILED" and re-raises | `monkeypatch` of `time.monotonic` |
| (existing) `test_ingest_cmd.py` | ErrorTally is populated correctly during a real ingest run | One new assertion |

### 7.1 What we deliberately don't test

- **Rich's internal rendering.** That's their test suite.
- **Byte-for-byte progress bar output.** Flaky across terminal widths and rich versions.
- **Real timing values.** Stub `time.monotonic` to return a fixed sequence.

### 7.2 Coverage targets

- `classify_exception`: 100% line + branch (one row in the parametrize table per rule)
- `ErrorTally`: 100% line
- `progress_iter` / `stage_banner`: happy path + one error path each
- `setup_logging`: idempotency check (call twice, only one handler installed)

## 8. Migration / rollout

Single PR. No feature flag — the existing behavior was strictly worse (silent `_log.warning` going only to Python's last-resort stderr handler), so we want the new behavior on by default for every user.

Backwards-compatibility: existing print statements (`ingest OK: ...`, `ERROR: ...`) stay on stdout exactly as today. Anyone parsing those lines downstream is unaffected.

## 9. Open questions

None at design time. The "Categorize + report only" scope choice means we don't need to make decisions about retry tuning or upstream-source replacement in this work.

## 10. Acceptance criteria

A reviewer should be able to verify, after merging:

1. `LDR_ENABLED=true uv run irc run` shows stage banners between each pipeline step.
2. Ingest displays three progress bars (metadata / prices / NAV) with `M/N` counts, %, and ETA.
3. At end of ingest, a tree summary categorizes every skipped instrument by error type.
4. Setting `DEBUG=true` in `.env` produces full rich tracebacks for every error and exposes akshare/requests DEBUG-level logs.
5. `irc run 2>log.txt` produces a log file with no ANSI escape codes.
6. All new tests pass; existing tests still pass.
7. No new direct dependencies beyond `rich` in `pyproject.toml`.
