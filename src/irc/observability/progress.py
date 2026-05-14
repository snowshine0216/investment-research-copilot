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
