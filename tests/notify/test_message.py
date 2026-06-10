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
