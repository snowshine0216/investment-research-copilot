"""Backward-compat re-export shim.

The canonical implementation moved to `irc.opportunity.citation_selector` to
break an `opportunity → memo` import cycle introduced when item 007 wired the
SAME-3 selector into `opportunity.report._render_section`. The
`memo → opportunity` direction already exists (via `picks_table`, `aliases`,
etc.), so importing through this shim is acyclic.

Prefer the canonical path in new code:

    from irc.opportunity.citation_selector import select_citations
"""
from __future__ import annotations

from irc.opportunity.citation_selector import select_citations  # noqa: F401

__all__ = ["select_citations"]
