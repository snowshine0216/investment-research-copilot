"""Robust JSON extraction from LLM responses (reasoning models emit <think>…;
some wrap JSON in ```json fences). Spec §6: 'extract JSON → Pydantic validate'."""
import json

import pytest

from irc.monitor.json_extract import extract_json


def test_plain_json_object():
    assert extract_json('{"impacts": []}') == {"impacts": []}


def test_strips_reasoning_think_block():
    text = '<think>\nReal yields drive gold; impact is negative.\n</think>\n{"impacts": [{"key": "gold_drivers"}]}'
    assert extract_json(text) == {"impacts": [{"key": "gold_drivers"}]}


def test_extracts_from_markdown_json_fence():
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_think_then_fence_with_nested_object():
    text = '<think>reasoning</think>\n```json\n{"a": {"b": 2}, "c": [1, 2]}\n```'
    assert extract_json(text) == {"a": {"b": 2}, "c": [1, 2]}


def test_json_surrounded_by_prose():
    text = 'Here is the result: {"a": 1} — hope that helps.'
    assert extract_json(text) == {"a": 1}


def test_braces_inside_strings_do_not_break_matching():
    text = '<think>x</think>{"s": "a{b}c", "n": 1}'
    assert extract_json(text) == {"s": "a{b}c", "n": 1}


def test_no_json_raises_json_decode_error():
    # so the gather functions' existing `except json.JSONDecodeError` still triggers schema-retry
    with pytest.raises(json.JSONDecodeError):
        extract_json('<think>only reasoning, no JSON here</think>')


def test_empty_string_raises():
    with pytest.raises(json.JSONDecodeError):
        extract_json('')
