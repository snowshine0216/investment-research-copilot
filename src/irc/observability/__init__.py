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
