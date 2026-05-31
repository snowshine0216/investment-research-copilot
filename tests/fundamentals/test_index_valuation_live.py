"""Live verification of legulegu index PE/PB endpoints (item 001).

Double-gated: requires BOTH the `live_akshare` marker AND
`IRC_RUN_LIVE_AKSHARE=1`. Default `pytest` skips it. This is the single point
that pins the real `stock_index_pe_lg` / `stock_index_pb_lg` column names; the
offline tests use fixtures.

Run::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare \\
        tests/fundamentals/test_index_valuation_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.index_valuation_types import IndexValuation

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]


def test_fetch_cn_index_valuation_csi300_live() -> None:
    """csi300 (沪深300) returns a real IndexValuation with a numeric PE and PB.

    If this fails with pe_ttm/pb None, the legulegu column labels differ from
    the candidate sets in akshare_index_valuation._PE_COLS / _PB_COLS — widen
    them and re-run. This is the designed pin point (spec §Open Q4).
    """
    out = fetch_cn_index_valuation("csi300")
    assert isinstance(out, IndexValuation)
    assert out.pe_ttm is not None, (
        "legulegu stock_index_pe_lg PE column not matched by _PE_COLS — "
        "inspect the live frame and widen the candidate set."
    )
    assert out.pb is not None, (
        "legulegu stock_index_pb_lg PB column not matched by _PB_COLS — "
        "inspect the live frame and widen the candidate set."
    )
    assert out.pe_ttm > 0 and out.pb > 0
    print(f"\n  ✓ csi300 live: pe={out.pe_ttm} pb={out.pb} div={out.dividend_yield}")
