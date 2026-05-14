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
