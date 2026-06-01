"""Live verification of the Tushare provider (item 003, ADR 0010 §4).

TRIPLE-gated: requires the `live_tushare` marker, `IRC_RUN_LIVE_TUSHARE=1`, AND
a non-empty `TUSHARE_TOKEN`. Default `pytest` skips it. This is the single point
that pins the real Tushare endpoint shapes; the offline tests use fixtures.

Mandatory assertion is scoped to filing-digest only (grill G1) — `report_rc`
(target_price) is points/paid-tier gated and may be unreachable on a free token,
so the broker smoke is skip-tolerant.

Run::

    IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \\
        tests/fundamentals/test_tushare_provider_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.tushare_provider import TushareProvider
from irc.fundamentals.types import FilingDigest

_TOKEN = os.environ.get("TUSHARE_TOKEN", "").strip()
_RUN = os.environ.get("IRC_RUN_LIVE_TUSHARE") == "1" and bool(_TOKEN)

pytestmark = [
    pytest.mark.live_tushare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_TUSHARE=1 AND a non-empty TUSHARE_TOKEN to run",
    ),
]


def test_fetch_cn_filing_digest_live() -> None:
    """600519 (贵州茅台) returns a real FilingDigest with ≥1 YoY metric.

    If both YoY fields are None, the fina_indicator column labels differ from
    the candidate sets in tushare_provider._REV_YOY_COLS / _NI_YOY_COLS — inspect
    the live frame and widen them. This is the designed pin point (ADR 0010 §4).
    """
    out = TushareProvider(_TOKEN).fetch_filing_digest("600519")
    assert isinstance(out, FilingDigest)
    assert (out.revenue_yoy is not None) or (out.net_income_yoy is not None), (
        "fina_indicator YoY columns not matched — widen _REV_YOY_COLS/_NI_YOY_COLS."
    )
    print(
        f"\n  ✓ 600519 live: rev_yoy={out.revenue_yoy} ni_yoy={out.net_income_yoy} "
        f"roe={out.roe} period={out.fiscal_period}"
    )


def test_fetch_broker_reports_live_smoke() -> None:
    """OPTIONAL: report_rc may be paid-tier gated; tolerate () but assert shape.

    Does NOT fail when the tier can't reach report_rc (returns ()). When reports
    are returned, asserts the field shape (target_price is float | None).
    """
    out = TushareProvider(_TOKEN).fetch_broker_reports("600519")
    for r in out:
        assert r.symbol == "600519.SH"
        assert r.target_price is None or isinstance(r.target_price, float)
    print(f"\n  ✓ 600519 broker reports: {len(out)} (target_price tier permitting)")
