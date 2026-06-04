from __future__ import annotations
import os
import pytest
from irc.fundamentals.akshare_index_valuation import (
    _SECTOR_INDEX_CODE,
    fetch_cn_sector_index_valuation_history,
)

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests"),
]


@pytest.mark.parametrize("slug", sorted(_SECTOR_INDEX_CODE))
def test_sector_index_pe_ttm_live(slug):
    out = fetch_cn_sector_index_valuation_history(slug)
    assert out is not None, f"{slug} ({_SECTOR_INDEX_CODE[slug]}) returned no history"
    pes = [r.pe_ttm for r in out.rows if r.pe_ttm is not None]
    assert pes, f"{slug}: no numeric 市盈率1 PE — confirm the CSI code/column"
    assert all(p > 0 for p in pes)
    print(f"\n  {slug} ({_SECTOR_INDEX_CODE[slug]}) live: latest PE-TTM={pes[-1]}")
