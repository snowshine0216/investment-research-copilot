"""Progress bars and stage banners.

Both `progress_iter` and `stage_banner` write to the shared stderr Console;
they auto-degrade to non-animated output when stderr is not a terminal.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
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
