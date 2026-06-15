"""Pure: extract a JSON object from an LLM response.

The monitor sends no provider JSON mode (spec §6), so responses may carry a
reasoning `<think>…</think>` preamble (e.g. MiniMax-M3), a ```json fence, or
surrounding prose. `extract_json` recovers the first balanced JSON object and
raises `json.JSONDecodeError` when none is present — so the gather functions'
existing `except json.JSONDecodeError` still drives the schema-retry policy.
"""
from __future__ import annotations

import json
import re

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Return the first balanced JSON object in `text`, ignoring reasoning
    blocks, code fences, and surrounding prose. Raises json.JSONDecodeError
    if no parseable object is found."""
    cleaned = _THINK.sub("", text)
    fence = _FENCE.search(cleaned)
    region = fence.group(1) if fence else cleaned
    return json.loads(_first_balanced_object(region))


def _first_balanced_object(s: str) -> str:
    """Return the first brace-balanced `{…}` substring (string-aware), or ""."""
    start = s.find("{")
    if start == -1:
        return ""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return ""
