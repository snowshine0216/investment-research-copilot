from __future__ import annotations

import os

import pytest

from irc.fundamentals.akshare_index_valuation import (
    _ak_call,
    _SECTOR_INDEX_CODE,
    fetch_cn_sector_index_valuation_history,
)
from irc.opportunity.sector_indices import SECTOR_INDICES

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests"
    ),
]

# index_csindex_all has no entry for SSE-listed codes (科创板). Cross-check that
# one via the SSE source / manual confirmation, not the CSI catalog identity.
_CSI_CATALOG_ABSENT = {"000685"}


@pytest.mark.parametrize("slug", sorted(_SECTOR_INDEX_CODE))
def test_sector_index_pe_ttm_numeric_live(slug):
    """Every sector code returns a numeric 市盈率1 PE-TTM series."""
    out = fetch_cn_sector_index_valuation_history(slug)
    assert out is not None, f"{slug} ({_SECTOR_INDEX_CODE[slug]}) returned no history"
    pes = [r.pe_ttm for r in out.rows if r.pe_ttm is not None]
    assert pes, f"{slug}: no numeric 市盈率1 PE — confirm the CSI code/column"
    assert all(p > 0 for p in pes)


def test_sector_codes_identity_in_csindex_all_live():
    """Load index_csindex_all ONCE; assert each committed code resolves to its
    committed official_cn (catches valid-but-WRONG codes). SSE-only codes are
    cross-checked separately (flagged for gate #4)."""
    catalog = _ak_call("index_csindex_all")
    # index_csindex_all columns: 指数代码 / 指数全称 (verify live; adjust if AkShare renames).
    code_col = next(c for c in ("指数代码", "code", "指数编号") if c in catalog.columns)
    name_col = next(c for c in ("指数全称", "指数简称", "name") if c in catalog.columns)
    by_code = {str(r[code_col]).strip(): str(r[name_col]).strip() for _, r in catalog.iterrows()}
    mismatches = []
    for row in SECTOR_INDICES:
        if row.code in _CSI_CATALOG_ABSENT:
            continue
        official = by_code.get(row.code)
        if official != row.official_cn:
            mismatches.append((row.slug, row.code, row.official_cn, official))
    assert not mismatches, f"code<->official-name identity mismatches: {mismatches}"
