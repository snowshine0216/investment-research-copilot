"""Live verification of legulegu index PE/PB endpoints (item 001 / Phase A).

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

from irc.fundamentals.akshare_index_valuation import (  # noqa: E402
    _LEGULEGU_INDEX_SYMBOL,
    _SPECULATIVE_LEGULEGU_SYMBOL,
    fetch_cn_index_valuation,
)
from irc.fundamentals.index_valuation_types import IndexValuation

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]


@pytest.mark.parametrize("slug", sorted(_LEGULEGU_INDEX_SYMBOL))
def test_production_symbol_returns_rolling_pe_and_pb_live(slug) -> None:
    """HARD ASSERT: every production allowlist symbol returns numeric rolling PE
    AND PB. If a slug returns None, the rolling-PE column (滚动市盈率) or PB column
    (市净率) is not present under that legulegu symbol — inspect the live frame.
    """
    out = fetch_cn_index_valuation(slug)
    assert isinstance(out, IndexValuation)
    assert out.pe_ttm is not None, (
        f"{slug} ({_LEGULEGU_INDEX_SYMBOL[slug]}): rolling PE (滚动市盈率) not matched — "
        "inspect the live stock_index_pe_lg frame."
    )
    assert out.pb is not None, (
        f"{slug} ({_LEGULEGU_INDEX_SYMBOL[slug]}): PB (市净率) not matched — "
        "inspect the live stock_index_pb_lg frame."
    )
    assert out.pe_ttm > 0 and out.pb > 0
    print(f"\n  ✓ {slug} ({_LEGULEGU_INDEX_SYMBOL[slug]}) live: pe={out.pe_ttm} pb={out.pb}")


def test_speculative_symbol_landing_sweep_informational() -> None:
    """INFORMATIONAL only — never fails. Probes each speculative symbol and prints
    a landing table. When a symbol lands (numeric pe AND pb), graduate it into
    _LEGULEGU_INDEX_SYMBOL + the hard-assert set in a follow-up PR (D2 graduation).
    """
    print("\n  speculative legulegu sweep (informational):")
    for slug, symbol in sorted(_SPECULATIVE_LEGULEGU_SYMBOL.items()):
        out = fetch_cn_index_valuation(slug)
        pe = out.pe_ttm if out is not None else None
        pb = out.pb if out is not None else None
        landed = "LANDED" if (pe is not None and pb is not None) else "—"
        print(f"    {slug:14s} {symbol:10s} pe={pe} pb={pb}  [{landed}]")
