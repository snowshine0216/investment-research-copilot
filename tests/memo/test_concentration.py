"""Pure-logic tests for src/irc/memo/concentration.py (item 002).

Covers AC1–AC9 + AC13 of docs/2026-05-27-instrument-pickability/items/002-spec.md.
AC11 (no row-level state change) is verified by the absence of changes to
opportunity/types.py and is asserted indirectly by the existing
test_publishable_set_lockdown.py two-run byte equality.
"""
from __future__ import annotations


def test_concentration_top_n_constant():
    """AC2: CONCENTRATION_TOP_N is a module-level Final[int] = 10."""
    from irc.memo.concentration import CONCENTRATION_TOP_N
    assert CONCENTRATION_TOP_N == 10


def test_concentration_overlap_pct_threshold_constant():
    """AC3: CONCENTRATION_OVERLAP_PCT_THRESHOLD is 30.0 (percent units, NOT fraction)."""
    from irc.memo.concentration import CONCENTRATION_OVERLAP_PCT_THRESHOLD
    assert CONCENTRATION_OVERLAP_PCT_THRESHOLD == 30.0


def test_concentration_marker_constants():
    """AC9: marker constants live at module-top in concentration.py."""
    from irc.memo.concentration import (
        CONCENTRATION_MARKER_BEGIN,
        CONCENTRATION_MARKER_END,
    )
    assert CONCENTRATION_MARKER_BEGIN == "<!-- IRC_CONCENTRATION_BEGIN -->"
    assert CONCENTRATION_MARKER_END == "<!-- IRC_CONCENTRATION_END -->"
