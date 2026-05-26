from __future__ import annotations

import re

from irc.memo.footnote_renderer import render_footnotes


def test_empty_input_returns_empty() -> None:
    assert render_footnotes("", []) == ""


def test_single_ref_inline_numbered_and_appendix_rewritten() -> None:
    """A single `[ref:HEXID]` inline becomes `[1]`; appendix line gets
    `**[1]**` prefix and `[ref:HEXID]` preserved at the tail in backticks."""
    memo = (
        "# Memo\n\n"
        "Some prose with [ref:aaaaaaaaaaaaaaaa].\n\n"
        "## 附录·原始证据 (Raw Evidence)\n\n"
        "- [ref:aaaaaaaaaaaaaaaa] snapshot · X · 2026-05-22: NAV=1.0\n"
    )
    out = render_footnotes(memo, ["[ref:aaaaaaaaaaaaaaaa] snapshot · X · 2026-05-22: NAV=1.0"])
    assert "[ref:aaaaaaaaaaaaaaaa]" not in out.split("## 附录")[0], \
        "inline hex marker must be replaced with [N]"
    assert "[1]" in out.split("## 附录")[0]
    appendix = out.split("## 附录")[1]
    assert "**[1]**" in appendix
    # Hex preserved at line tail for grep/audit, wrapped in backticks.
    assert "`[ref:aaaaaaaaaaaaaaaa]`" in appendix


def test_duplicate_hexid_reuses_same_number() -> None:
    memo = (
        "Line one [ref:aaaaaaaaaaaaaaaa] and again [ref:aaaaaaaaaaaaaaaa].\n\n"
        "## 附录·原始证据 (Raw Evidence)\n\n"
        "- [ref:aaaaaaaaaaaaaaaa] snapshot · X · 2026-05-22\n"
    )
    out = render_footnotes(memo, ["[ref:aaaaaaaaaaaaaaaa] snapshot · X · 2026-05-22"])
    body = out.split("## 附录")[0]
    # Both inline mentions should render as [1].
    assert body.count("[1]") == 2
    # No other footnote number assigned.
    assert "[2]" not in body


def test_multiple_distinct_refs_get_sequential_numbers() -> None:
    refs = [
        "[ref:aaaaaaaaaaaaaaaa] snapshot · A · 2026-05-22",
        "[ref:bbbbbbbbbbbbbbbb] snapshot · B · 2026-05-22",
        "[ref:cccccccccccccccc] snapshot · C · 2026-05-22",
    ]
    memo = (
        "Intro [ref:aaaaaaaaaaaaaaaa] then [ref:bbbbbbbbbbbbbbbb] and finally "
        "[ref:cccccccccccccccc].\n\n"
        "## 附录·原始证据 (Raw Evidence)\n\n"
        + "".join(f"- {r}\n" for r in refs)
    )
    out = render_footnotes(memo, refs)
    body = out.split("## 附录")[0]
    assert "[1]" in body and "[2]" in body and "[3]" in body
    # Numbers must be assigned in document order — [1] before [2] before [3].
    assert body.index("[1]") < body.index("[2]") < body.index("[3]")


def test_fifty_refs_all_numbered_and_in_appendix() -> None:
    """Stress: 50 distinct refs (above the old _MAX_REFS=40 cap) all render."""
    refs = [f"[ref:{i:016x}] snapshot · X · 2026-05-22" for i in range(50)]
    inline = " ".join(f"[ref:{i:016x}]" for i in range(50))
    memo = (
        f"Body: {inline}\n\n"
        "## 附录·原始证据 (Raw Evidence)\n\n"
        + "".join(f"- {r}\n" for r in refs)
    )
    out = render_footnotes(memo, refs)
    body, _, appendix = out.partition("## 附录")
    # All 50 numbers appear inline.
    for n in range(1, 51):
        assert f"[{n}]" in body
    # Appendix has all 50 numbered entries.
    for n in range(1, 51):
        assert f"**[{n}]**" in appendix


def test_refs_only_in_appendix_get_trailing_numbers() -> None:
    """Refs present in `refs` but never appearing inline still get numbered
    in the appendix using positions after the inline-derived numbers."""
    refs = [
        "[ref:aaaaaaaaaaaaaaaa] snapshot · A · 2026-05-22",
        "[ref:bbbbbbbbbbbbbbbb] snapshot · B · 2026-05-22",  # never inline
    ]
    memo = (
        "Body cites only [ref:aaaaaaaaaaaaaaaa].\n\n"
        "## 附录·原始证据 (Raw Evidence)\n\n"
        + "".join(f"- {r}\n" for r in refs)
    )
    out = render_footnotes(memo, refs)
    body, _, appendix = out.partition("## 附录")
    assert "[1]" in body
    assert "[2]" not in body
    # Both refs numbered in appendix.
    assert "**[1]**" in appendix
    assert "**[2]**" in appendix


def test_published_memo_has_zero_hex_markers_in_body() -> None:
    """Acceptance: no `[ref:HEXID]` markers leak into the user-visible body."""
    refs = ["[ref:aaaaaaaaaaaaaaaa] snapshot · X · 2026-05-22"]
    memo = (
        "Cite [ref:aaaaaaaaaaaaaaaa] inline.\n\n"
        "## 附录·原始证据 (Raw Evidence)\n\n- [ref:aaaaaaaaaaaaaaaa] x\n"
    )
    out = render_footnotes(memo, refs)
    body, _, _ = out.partition("## 附录")
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", body)
