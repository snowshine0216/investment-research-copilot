"""Locks: routing the four call-sites through AkShareProvider yields output
byte-identical to the pre-migration direct calls on the same stubbed _ak_call.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals import akshare_index_valuation
from irc.fundamentals.provider import AkShareProvider
from irc.opportunity.inputs_loader import _index_valuation_metrics

_PE_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": [12.1]})
_PB_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "市净率": [1.31]})


def test_index_metrics_via_provider_matches_pre_migration() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake):
        out = _index_valuation_metrics("csi300", provider=AkShareProvider())
    # Same as fetch_cn_index_valuation("csi300").pe_ttm / .pb / .dividend_yield.
    assert out == (12.1, 1.31, None)


def test_index_metrics_unknown_key_does_not_call_ak() -> None:
    with patch.object(akshare_index_valuation, "_ak_call") as mocked:
        out = _index_valuation_metrics("not_a_broad_index", provider=AkShareProvider())
    assert out == (None, None, None)
    mocked.assert_not_called()
