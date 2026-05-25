"""Post-pass that rewrites `[ref:HEXID]` markers into footnote numbers.

This pass runs AFTER memo audit gates (which still operate on the canonical
`[ref:HEXID]` form). Only the published memo.md gets the friendly numbering.

Numbering rules:
  - Global single sequence (no per-section reset).
  - First inline appearance of a HEXID assigns its number.
  - Subsequent inline mentions of the same HEXID reuse that number.
  - Refs present in `raw_refs` but never appearing inline are numbered last,
    in `raw_refs` list order, so the appendix carries every supplied ref.

Appendix rewrite:
  Input  line `- [ref:HEXID] type · source · date: summary` becomes
  output line `- **[N]** type · source · date: summary  (`[ref:HEXID]`)` —
  the hex is preserved at the line tail (backticked) for grep / audit.
"""
from __future__ import annotations

import re

_REF_RE = re.compile(r"\[ref:([0-9a-f]{16})\]")
_APPENDIX_HEADING = "## 附录·原始证据 (Raw Evidence)"


def _hexids_in_inline_order(body: str) -> list[str]:
    """Return distinct HEXIDs in their first-appearance order across `body`."""
    seen: dict[str, None] = {}
    for match in _REF_RE.finditer(body):
        seen.setdefault(match.group(1), None)
    return list(seen.keys())


def _hexid_from_ref_string(ref: str) -> str | None:
    match = _REF_RE.search(ref)
    return match.group(1) if match else None


def _rewrite_appendix_line(line: str, numbers_by_hexid: dict[str, int]) -> str:
    """Insert `**[N]** ` prefix and a trailing `` (`[ref:HEXID]`) ``.

    Skips lines that don't carry a `[ref:HEXID]` marker (caveat banners,
    `[gold]` lines, the warning prefix, etc.) — those pass through unchanged.
    """
    match = _REF_RE.search(line)
    if match is None:
        return line
    hexid = match.group(1)
    number = numbers_by_hexid.get(hexid)
    if number is None:
        return line
    # Strip the leading `- ` if present; we rebuild it.
    if line.startswith("- "):
        head, content = "- ", line[2:]
    else:
        head, content = "", line
    content_no_marker = _REF_RE.sub("", content, count=1).strip()
    # Tidy leftover " · " or doubled spaces at the start.
    content_no_marker = content_no_marker.lstrip(" ·")
    return f"{head}**[{number}]** {content_no_marker}  (`[ref:{hexid}]`)"


def render_footnotes(memo_md: str, raw_refs: list[str] | tuple[str, ...]) -> str:
    """Rewrite inline `[ref:HEXID]` markers to `[N]` and renumber appendix.

    See module docstring for numbering rules and appendix shape.
    """
    if not memo_md:
        return ""
    body, sep, appendix = memo_md.partition(_APPENDIX_HEADING)

    inline_hexids = _hexids_in_inline_order(body)
    numbers_by_hexid: dict[str, int] = {}
    for hexid in inline_hexids:
        numbers_by_hexid[hexid] = len(numbers_by_hexid) + 1
    # Append refs that never appeared inline so the appendix still numbers them.
    for ref in raw_refs:
        hexid = _hexid_from_ref_string(ref)
        if hexid and hexid not in numbers_by_hexid:
            numbers_by_hexid[hexid] = len(numbers_by_hexid) + 1

    rewritten_body = _REF_RE.sub(
        lambda m: f"[{numbers_by_hexid.get(m.group(1), 0)}]",
        body,
    )

    if not sep:
        return rewritten_body
    rewritten_appendix_lines = [
        _rewrite_appendix_line(line, numbers_by_hexid)
        for line in appendix.splitlines()
    ]
    rewritten_appendix = "\n".join(rewritten_appendix_lines)
    return rewritten_body + sep + rewritten_appendix
