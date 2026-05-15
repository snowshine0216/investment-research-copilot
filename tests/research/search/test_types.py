"""Shape tests for research.search.types — confirm dataclasses are frozen,
defaults are correct, and Locale values stringify as expected."""
from __future__ import annotations
import dataclasses
import pytest

from irc.research.search.types import (
    ExtractedPage,
    Locale,
    SearchHit,
    SearchResult,
)


def test_locale_values_are_lowercase_strings():
    assert Locale.EN.value == "en"
    assert Locale.ZH.value == "zh"


def test_search_hit_is_frozen_with_optional_fields_defaulting_to_empty():
    hit = SearchHit(title="t", url="https://x", snippet="s")
    assert hit.published_iso == ""
    assert hit.source_domain == ""
    with pytest.raises(dataclasses.FrozenInstanceError):
        hit.title = "other"  # type: ignore[misc]


def test_search_result_defaults_to_empty_hits_and_success():
    res = SearchResult(query="q", locale=Locale.EN)
    assert res.hits == ()
    assert res.provider == ""
    assert res.failure_reason == ""


def test_extracted_page_is_frozen():
    page = ExtractedPage(
        url="https://x",
        title="t",
        markdown="# hi",
        fetched_at_iso="2026-05-15T00:00:00Z",
    )
    assert page.failure_reason == ""
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.title = "other"  # type: ignore[misc]
