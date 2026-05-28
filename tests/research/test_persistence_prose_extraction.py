"""Unit tests for extract_prose_from_report_md — precise stop-marker behaviour.

Finding 2 (round 2 PR review): the helper must stop ONLY at the '## Citations'
or '## References' footer, not at any '## ' heading inside the prose body.

These tests were written RED before the implementation change, following
TDD red-green-refactor.
"""
from __future__ import annotations

from irc.research.persistence import extract_prose_from_report_md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(prose: str, *, citations: str = "[1] Some Source — https://example.com") -> str:
    """Assemble a minimal persisted report string matching format_report_markdown output."""
    return f"# test_theme\n\n{prose}\n\n## Citations\n{citations}\n"


# ---------------------------------------------------------------------------
# Stop at explicit footer headings only
# ---------------------------------------------------------------------------

def test_stops_at_citations_footer():
    """## Citations marks the end of prose — nothing after it is returned."""
    md = _make_report("Good prose here.")
    result = extract_prose_from_report_md(md)
    assert "Good prose here." in result
    assert "Citations" not in result
    assert "Some Source" not in result


def test_stops_at_references_footer():
    """## References is an acceptable alternative footer — must also stop."""
    md = (
        "# test_theme\n\n"
        "Prose body.\n\n"
        "## References\n"
        "[1] Other Source — https://other.com\n"
    )
    result = extract_prose_from_report_md(md)
    assert "Prose body." in result
    assert "References" not in result
    assert "Other Source" not in result


def test_does_not_stop_at_internal_subheading():
    """A '## Key Risks' heading inside the prose body must NOT truncate the result."""
    md = (
        "# test_theme\n\n"
        "Overview paragraph.\n\n"
        "## Key Risks\n\n"
        "Risk paragraph.\n\n"
        "## Citations\n"
        "[1] Source — https://x.com\n"
    )
    result = extract_prose_from_report_md(md)
    assert "Overview paragraph." in result
    assert "Key Risks" in result
    assert "Risk paragraph." in result
    # Citation footer must still be stripped
    assert "Source — https://x.com" not in result


def test_does_not_stop_at_drivers_subheading():
    """Another common internal subheading — '## Key Drivers' must not truncate."""
    md = (
        "# test_theme\n\n"
        "Intro.\n\n"
        "## Key Drivers\n\n"
        "Drivers detail.\n\n"
        "## Citations\n"
        "[1] Src — https://s.com\n"
    )
    result = extract_prose_from_report_md(md)
    assert "Intro." in result
    assert "Key Drivers" in result
    assert "Drivers detail." in result
    assert "Src — https://s.com" not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_prose_paragraph_returns_empty_string():
    """When there is no text between the title heading and the Citations footer,
    the result should be an empty string (after strip)."""
    md = "# test_theme\n\n## Citations\n[1] Source — https://x.com\n"
    result = extract_prose_from_report_md(md)
    assert result == ""


def test_multi_paragraph_prose_preserved():
    """Multi-paragraph prose is joined and returned intact."""
    md = (
        "# test_theme\n\n"
        "First paragraph about macro.\n\n"
        "Second paragraph about rates.\n\n"
        "Third paragraph about yields.\n\n"
        "## Citations\n"
        "[1] Source — https://x.com\n"
    )
    result = extract_prose_from_report_md(md)
    assert "First paragraph about macro." in result
    assert "Second paragraph about rates." in result
    assert "Third paragraph about yields." in result
    assert "Source" not in result


def test_citations_nospace_heading_stops_extraction():
    """##Citations (no space after ##) — synth output is deterministic so this
    won't appear in practice, but we make an explicit choice: treat it as a
    stop marker as well, since it can only be a footer artifact.

    Chosen behaviour: stop — do NOT include citation content in prose even if
    the heading is malformed. This is safer (never leak citation text) and
    consistent with the spirit of ADR 0007 §3a.
    """
    md = (
        "# test_theme\n\n"
        "Prose line.\n\n"
        "##Citations\n"
        "[1] Source — https://x.com\n"
    )
    result = extract_prose_from_report_md(md)
    assert "Prose line." in result
    assert "Source" not in result
    assert "https://x.com" not in result


def test_no_citations_section_returns_all_prose():
    """Report with no ## Citations footer — all body text is returned."""
    md = "# test_theme\n\nFull prose without a footer.\n"
    result = extract_prose_from_report_md(md)
    assert "Full prose without a footer." in result


def test_top_level_heading_stripped():
    """The # <theme> heading itself must not appear in the result."""
    md = _make_report("Body text.")
    result = extract_prose_from_report_md(md)
    assert "# test_theme" not in result
    assert "test_theme" not in result


def test_stress_keywords_in_citation_titles_do_not_reach_prose():
    """Integration-style: keywords like 'war', 'sanction' in citation titles
    must not be present in the extracted prose string.

    This mirrors the original citation-contamination concern that motivated
    ADR 0007 §3a, extended to internal subheadings.
    """
    md = (
        "# test_theme\n\n"
        "Markets remain calm. No escalation reported.\n\n"
        "## Citations\n"
        "[1] Russia-Ukraine war sanction tariff — https://news.com\n"
        "[2] Strike attack conflict — https://other.com\n"
    )
    result = extract_prose_from_report_md(md)
    assert "war" not in result
    assert "sanction" not in result
    assert "tariff" not in result
    assert "strike" not in result.lower()
    assert "attack" not in result
