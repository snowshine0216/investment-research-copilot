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
