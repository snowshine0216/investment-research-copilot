from __future__ import annotations


def check_traceability(
    memo_text: str, raw_refs: tuple[str, ...] | list[str],
) -> dict[str, int]:
    """Count refs that the memo quotes verbatim.

    Reports:
      - n_refs_provided: how many evidence strings the synthesizer was given.
      - n_refs_quoted_verbatim: how many of those strings appear as an exact
        substring of the memo text (case-sensitive — refs are typically
        identifiers / quoted snippets, not free prose).
      - n_refs: back-compat alias for n_refs_provided (some downstream tools
        still read this key).

    We do NOT compute a coverage_ratio. Paraphrased citations were silently
    scored 0 by the previous token-overlap heuristic, especially for Chinese
    text, which made the ratio actively misleading. Reporting raw counts
    lets the reader judge for themselves.
    """
    refs_tuple = tuple(raw_refs)
    n_provided = len(refs_tuple)
    n_quoted = sum(1 for ref in refs_tuple if ref and ref in memo_text)
    return {
        "n_refs_provided": n_provided,
        "n_refs_quoted_verbatim": n_quoted,
        "n_refs": n_provided,
    }
