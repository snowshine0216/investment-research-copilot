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
